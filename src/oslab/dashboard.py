from __future__ import annotations

import json
import csv
import gzip
import html
import math
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlparse
import urllib.request
import urllib.error
import re

from rdkit import Chem
from rdkit.Chem import rdDepictor, rdFMCS, rdMolAlign
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Geometry import Point3D

from .binding_sites import box_from_fpocket, box_from_ligand, box_from_residues, find_ligand_residue_names, run_fpocket
from .docking import prepare_receptor_for_vina
from .hit_refinement import recent_docking_runs
from .hpc import export_slurm_small_screen
from .interactions import plip_interaction_rows
from .jobs import (
    DEFAULT_RDKIT_SEED,
    atomic_write_json,
    campaign_context,
    file_lock,
    job_progress_path,
    new_job_id,
    runtime_provenance,
    screen_session_name,
    set_rdkit_seed,
)
from .ligand_filtering import filter_ligands, load_ligands
from .ligand_prep import prepare_ligands_for_vina
from .ligand_sources import ligand_source_rows
from .openfe_backend import _add_ligand_similarity_to_network
from .orchestration import WorkflowInputState, guide_workflow
from .presets.registry import list_ligand_filter_presets, load_ligand_filter_preset
from .protein import prepare_protein
from .project import ensure_project_layout, ensure_user_project_layout, safe_user_name
from .schemas import LigandPrepOptions, ProteinPrepOptions, VinaRunOptions
from .screening import run_small_screen
from .structures import fetch_alphafold_structure, fetch_pdb_structure, list_structure_records, register_local_structure
from .tools import check_cli_tools, check_python_imports
from .visualization import render_binding_site_html, render_pockets_html, render_structure_html


STRUCTURE_SOURCES = [
    {
        "key": "pdb",
        "name": "RCSB PDB",
        "structure_type": "experimental",
        "identifier_label": "PDB ID",
        "example": "1HCK",
        "formats": ["cif", "pdb"],
        "best_for": "experimental structures, redocking validation, known protein-ligand complexes",
        "caveats": "may contain missing loops, alternate locations, cofactors, salts, and crystallographic waters",
    },
    {
        "key": "alphafold",
        "name": "AlphaFold DB",
        "structure_type": "predicted",
        "identifier_label": "UniProt accession",
        "example": "P24941",
        "formats": ["pdb"],
        "best_for": "targets without a suitable experimental structure",
        "caveats": "does not include bound ligands; pocket shape and side chains may need more review before docking",
    },
    {
        "key": "local",
        "name": "Local structure file",
        "structure_type": "user-provided",
        "identifier_label": "File path",
        "example": "/path/to/protein.pdb",
        "formats": ["pdb", "cif"],
        "best_for": "curated structures, private models, or structures prepared outside OSLabLambda",
        "caveats": "user is responsible for provenance and licensing",
    },
]

_GENE_CACHE: dict[str, str] = {}


_SESSION_COOKIE_NAME = "oslab_session"
_SESSION_COOKIE_RE = re.compile(r"^[a-z0-9]{8,64}$")


def _session_id_for_request(handler: BaseHTTPRequestHandler | None) -> str:
    """Get-or-mint an anonymous session ID for this request.

    Returns the session ID (a short hex token) and caches it on the handler
    so the same token is reused across get_request_user calls within one
    request and so the response code can emit Set-Cookie when minted.

    Session-cookie mode is OPT-IN via the OSLAB_SESSION_COOKIES env var so we
    do not disturb the existing single-user / multi-user-by-header deployments.
    """
    if handler is None:
        return ""
    if not _env_truthy(os.environ.get("OSLAB_SESSION_COOKIES")):
        return ""
    cached = getattr(handler, "_oslab_session_id", None)
    if cached is not None:
        return cached
    cookie_header = handler.headers.get("Cookie", "") or ""
    sid = ""
    for part in cookie_header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == _SESSION_COOKIE_NAME and v:
            candidate = v.strip()
            if _SESSION_COOKIE_RE.fullmatch(candidate):
                sid = candidate
                break
    if sid:
        handler._oslab_session_id = sid
        handler._oslab_session_new = False
        return sid
    sid = secrets.token_hex(12)
    handler._oslab_session_id = sid
    handler._oslab_session_new = True
    return sid


def _env_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def get_request_user(handler: BaseHTTPRequestHandler | None = None) -> str:
    """Identify the dashboard user for path scoping, not authentication."""

    # Anonymous-session mode (public reviewer instance): each browser gets a
    # unique session ID via cookie, which becomes its workspace identifier.
    sid = _session_id_for_request(handler)
    if sid:
        return safe_user_name(f"anon-{sid}") or f"anon{sid}"

    candidates: list[str] = []
    if handler is not None:
        candidates.extend(
            [
                handler.headers.get("X-Remote-User", ""),
                handler.headers.get("X-Forwarded-User", ""),
            ]
        )
    candidates.extend(
        [
            os.environ.get("OSLAB_USER", ""),
            os.environ.get("USER", ""),
            os.environ.get("LOGNAME", ""),
            "default-user",
        ]
    )
    for candidate in candidates:
        if not str(candidate or "").strip():
            continue
        user = safe_user_name(candidate)
        if user:
            return user
    return "default-user"


def _dashboard_user_layout(root: Path, username: str | None) -> dict[str, str]:
    return ensure_user_project_layout(root, username or get_request_user())


def _dashboard_user_root(root: Path, username: str | None) -> Path:
    return Path(_dashboard_user_layout(root, username)["root"]).resolve()


def _dashboard_workspace_roots(root: Path, username: str | None, *, include_legacy: bool = True) -> list[Path]:
    roots: list[Path] = []
    for candidate in [_dashboard_user_root(root, username), root.resolve() if include_legacy else None]:
        if not candidate:
            continue
        try:
            resolved = Path(candidate).resolve()
        except OSError:
            continue
        if resolved not in roots and resolved.exists():
            roots.append(resolved)
    return roots


@dataclass
class DashboardJob:
    id: str
    kind: str
    username: str = "default-user"
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "username": self.username,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "request": self.request,
            "result": self.result,
            "error": self.error,
        }


class DashboardState:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.dashboard_port: int | None = None
        ensure_project_layout(self.root)
        self.jobs: dict[str, DashboardJob] = {}
        self.lock = threading.Lock()
        self.snapshot_lock = threading.Lock()
        self._snapshot_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._load_persisted_jobs(get_request_user())

    def snapshot(self, username: str | None = None) -> dict[str, Any]:
        username = safe_user_name(username or get_request_user())
        now = time.monotonic()
        with self.snapshot_lock:
            cached = self._snapshot_cache.get(username)
            if cached is not None and now - cached[0] < 1.0:
                return cached[1]
            snapshot = self._build_snapshot(username)
            self._snapshot_cache[username] = (time.monotonic(), snapshot)
            return snapshot

    def _build_snapshot(self, username: str) -> dict[str, Any]:
        layout = ensure_project_layout(self.root)
        user_layout = _dashboard_user_layout(self.root, username)
        user_root = Path(user_layout["root"])
        return {
            "root": str(self.root),
            "layout": layout.model_dump(),
            "user": username,
            "user_root": str(user_root),
            "bundled_demo_dir": str(Path(__file__).resolve().parent / "bundled_demo"),
            "user_layout": user_layout,
            "connection": _dashboard_connection_info(self.root, dashboard_port=self.dashboard_port),
            "run_environment": _run_environment_metadata(self.root),
            "structure_sources": STRUCTURE_SOURCES,
            "cached_structures": _dashboard_structure_records(self.root),
            "target_preparation": self._target_preparation(username),
            "binding_sites": self._binding_sites(username),
            "ligand_sources": _dashboard_ligand_sources(),
            "ligand_libraries": _dashboard_ligand_libraries(user_root),
            "ligand_starter_libraries": _dashboard_ligand_starter_libraries(),
            "filter_presets": [load_ligand_filter_preset(key).model_dump() for key in list_ligand_filter_presets()],
            "runs": self._runs(username),
            "jobs": self._jobs_snapshot(username),
            "orchestration_progress": self._orchestration_progress(username),
            "hit_refinement_runs": recent_docking_runs(user_root, limit=3),
            "hit_refinement_progress": self._hit_refinement_progress(username),
            "md_optimization_progress": self._md_optimization_progress(username),
            "fep_progress": self._fep_progress(username),
            "permissions": _dashboard_permissions(self.root),
        }

    def add_job(self, job: DashboardJob) -> DashboardJob:
        with self.lock:
            self.jobs[job.id] = job
            self._write_job(job)
        return job

    def update_job(self, job_id: str, **updates: Any) -> None:
        with self.lock:
            job = self.jobs[job_id]
            for key, value in updates.items():
                setattr(job, key, value)
            job.updated_at = datetime.now(timezone.utc).isoformat()
            self._write_job(job)

    def get_job(self, job_id: str) -> DashboardJob | None:
        with self.lock:
            return self.jobs.get(job_id)

    def get_job_snapshot(self, job_id: str, username: str | None = None) -> dict[str, Any] | None:
        for job in self._jobs_snapshot(username):
            if job["id"] == job_id:
                return job
        return None

    def _jobs_snapshot(self, username: str | None = None) -> list[dict[str, Any]]:
        username = safe_user_name(username or get_request_user())
        self._load_persisted_jobs(username)
        with self.lock:
            jobs = [
                job.to_dict()
                for job in self.jobs.values()
                if job.username in {username, "legacy", "default-user"}
            ]
        refreshed_jobs: list[dict[str, Any]] = []
        for job in jobs:
            if job["status"] in {"queued", "running"} and job["kind"] == "ligand-prep":
                job["result"] = _ligand_prep_progress_from_files(self.root, job["request"], job.get("result") or {})
            elif job["status"] in {"queued", "running"} and job["kind"] == "small-screen":
                job["result"] = _small_screen_progress_from_files(job["request"], job.get("result") or {})
                job = self._refresh_process_backed_job(job)
            elif job["kind"] in {"terminal-orchestration", "hit-refinement", "md-optimization", "fep"}:
                result = dict(job.get("result") or {})
                progress_value = str(result.get("progress_json") or "")
                progress_path = Path(progress_value) if progress_value else None
                if progress_path and progress_path.exists():
                    result["progress"] = _read_json_file(progress_path)
                    result["log_tail"] = _tail_text(Path(str(result.get("log_path") or "")), max_chars=2000)
                    job["result"] = result
                job = self._refresh_process_backed_job(job)
            elif job["kind"] == "orchestrate":
                # Orchestrate jobs run in a detached screen session; we cannot
                # update DashboardJob.status from within that subprocess, so
                # reflect the latest progress.json + log tail here so polling
                # clients (and the dashboard monitor) see real-time status.
                result = dict(job.get("result") or {})
                progress_path = Path(str(result.get("progress_path") or "")) if result.get("progress_path") else None
                if progress_path and progress_path.exists():
                    prog = _read_json_file(progress_path) or {}
                    result["progress"] = prog
                    log_path = Path(str(result.get("log_path") or ""))
                    if log_path.exists():
                        result["log_tail"] = _tail_text(log_path, max_chars=4000)
                    final_status = str(prog.get("status") or "")
                    if final_status in {"completed", "failed"}:
                        job["status"] = final_status
                    job["result"] = result
            if job is not None:
                refreshed_jobs.append(job)
        known_outputs = {str((job.get("result") or {}).get("output_dir") or "") for job in refreshed_jobs}
        for workspace_root in _dashboard_workspace_roots(self.root, username):
            refreshed_jobs.extend(_discover_ligand_prep_jobs(workspace_root, known_outputs))
        return refreshed_jobs

    def _jobs_dir(self, username: str | None = None) -> Path:
        username = safe_user_name(username or get_request_user())
        path = _dashboard_user_root(self.root, username) / "runs" / "dashboard-jobs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _job_path(self, job_id: str, username: str | None = None) -> Path:
        return self._jobs_dir(username) / f"{job_id}.json"

    def _write_job(self, job: DashboardJob) -> None:
        self._job_path(job.id, job.username).write_text(json.dumps(job.to_dict(), indent=2) + "\n")
        if job.username == "default-user":
            legacy_dir = self.root / "runs" / "dashboard-jobs"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            (legacy_dir / f"{job.id}.json").write_text(json.dumps(job.to_dict(), indent=2) + "\n")

    def _load_persisted_jobs(self, username: str | None = None) -> None:
        username = safe_user_name(username or get_request_user())
        jobs_dirs = [
            (_dashboard_user_root(self.root, username) / "runs" / "dashboard-jobs", username),
            (self.root / "runs" / "dashboard-jobs", "legacy"),
        ]
        with self.lock:
            for jobs_dir, directory_user in jobs_dirs:
                if not jobs_dir.exists():
                    continue
                for path in sorted(jobs_dir.glob("*.json")):
                    try:
                        data = json.loads(path.read_text())
                        job = DashboardJob(
                            id=str(data["id"]),
                            kind=str(data["kind"]),
                            username=safe_user_name(data.get("username") or directory_user),
                            status=str(data.get("status") or "queued"),
                            created_at=str(data.get("created_at") or ""),
                            updated_at=str(data.get("updated_at") or ""),
                            request=dict(data.get("request") or {}),
                            result=data.get("result") if isinstance(data.get("result"), dict) else None,
                            error=str(data.get("error") or ""),
                        )
                    except Exception:
                        continue
                    if _is_foreign_dashboard_job(self.root, job):
                        try:
                            path.unlink()
                        except FileNotFoundError:
                            pass
                        continue
                    if job.id not in self.jobs or job.updated_at > self.jobs[job.id].updated_at:
                        self.jobs[job.id] = job

    def _refresh_process_backed_job(self, data: dict[str, Any]) -> dict[str, Any] | None:
        result = dict(data.get("result") or {})
        session = str(result.get("session_name") or "")
        if data["kind"] in {"terminal-orchestration", "hit-refinement", "md-optimization"} and _terminal_progress_completed(result):
            if session and _screen_session_running(session):
                _quit_screen_session(session)
            if data["kind"] == "terminal-orchestration":
                self._remove_job(data["id"])
                return None
            data["status"] = "completed"
            self._persist_snapshot_status(data)
            return data
        if data["kind"] == "small-screen":
            output_dir = Path(str(result.get("output_dir") or data["request"].get("out"))).resolve()
            summary_path = output_dir / "small_screen_summary.json"
            if summary_path.exists():
                summary = _read_json_file(summary_path) or {}
                data["status"] = "completed"
                data["result"] = {
                    **result,
                    **summary,
                    **_small_screen_progress_from_files(data["request"], result),
                    "phase": "completed",
                    "progress_percent": 100,
                }
                self._persist_snapshot_status(data)
                return data
        if session and not _screen_session_running(session):
            if data["kind"] == "terminal-orchestration":
                self._remove_job(data["id"])
                return None
            if data["kind"] in {"hit-refinement", "md-optimization", "fep"}:
                progress = result.get("progress") if isinstance(result.get("progress"), dict) else {}
                if progress.get("status") == "completed":
                    data["status"] = "completed"
                    self._persist_snapshot_status(data)
                    return data
            data["status"] = "failed"
            log_tail = _tail_text(Path(str(result.get("log_path") or "")))
            data["error"] = data.get("error") or "Detached job is no longer running and no completed summary was found."
            if log_tail:
                data["result"] = {**result, "log_tail": log_tail}
            self._persist_snapshot_status(data)
        return data

    def _remove_job(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs.pop(job_id, None)
        candidate_users = [job.username] if job else []
        candidate_users.extend(["legacy", get_request_user()])
        for username in candidate_users:
            if username == "legacy":
                path = self.root / "runs" / "dashboard-jobs" / f"{job_id}.json"
            else:
                path = self._job_path(job_id, username)
            try:
                path.unlink()
            except FileNotFoundError:
                pass

    def _persist_snapshot_status(self, data: dict[str, Any]) -> None:
        with self.lock:
            job = self.jobs.get(data["id"])
            if not job:
                return
            job.status = data["status"]
            job.result = data.get("result")
            job.error = data.get("error") or ""
            job.updated_at = datetime.now(timezone.utc).isoformat()
            self._write_job(job)

    def _runs(self, username: str | None = None) -> list[dict[str, Any]]:
        workspace_roots = _dashboard_workspace_roots(self.root, username)
        report_roots = [workspace_root / "reports" for workspace_root in workspace_roots]
        run_roots = [workspace_root / "runs" for workspace_root in workspace_roots]
        rows: list[dict[str, Any]] = []
        summary_names = {
            "small_screen_summary.json",
            "docking_results_summary.json",
            "validation_results_summary.json",
            "hit_refinement_summary.json",
        }
        summary_roots = [path for pair in zip(report_roots, run_roots) for path in pair]
        summary_paths: list[Path] = []
        for root in summary_roots:
            for name in summary_names:
                summary_paths.extend(root.glob(f"*/{name}"))
                summary_paths.extend(root.glob(f"*/report/{name}"))
                summary_paths.extend(root.glob(f"*/*/{name}"))
        for summary_path in sorted(set(summary_paths)):
            try:
                data = json.loads(summary_path.read_text())
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            display_name = summary_path.parent.name
            parent_root = next((root for root in summary_roots if root in [summary_path, *summary_path.parents]), summary_path.parent)
            if display_name == "report" and summary_path.parent.parent != parent_root:
                display_name = summary_path.parent.parent.name
            try:
                delete_path_str = str(_report_delete_dir(self.root, summary_path))
            except ValueError:
                # Summary path is outside the project root (e.g. symlinked from
                # a shared read-only demo workspace). Delete isn't allowed there
                # — leave the path empty so the UI hides the delete control.
                delete_path_str = ""
            rows.append(
                {
                    "key": f"{_summary_kind(summary_path.name)}:{display_name}",
                    "name": display_name,
                    "summary_path": str(summary_path),
                    "delete_path": delete_path_str,
                    "kind": _summary_kind(summary_path.name),
                    "best_ligand": data.get("best_ligand"),
                    "best_score": data.get("best_score"),
                    "best_rmsd_heavy_atom": data.get("best_rmsd_heavy_atom"),
                    "run_count": data.get("run_count") or data.get("docked_ligands"),
                    "report_markdown": data.get("report_markdown") or data.get("docking_report"),
                    "results_json": data.get("results_json"),
                    "results_json_exists": bool(data.get("results_json") and Path(str(data.get("results_json"))).exists()),
                    "results_csv": data.get("results_csv"),
                    "visualization_html": data.get("visualization_html"),
                    "created_at": data.get("created_at"),
                }
            )
        _md_opt_paths: set[Path] = set()
        for runs in run_roots:
            _md_opt_paths.update(runs.glob("md-optimization-*/progress.json"))
            _md_opt_paths.update(runs.glob("*-md-optimization/progress.json"))
            _md_opt_paths.update(runs.glob("*-md-optimization-*/progress.json"))
        for progress_path in sorted(_md_opt_paths):
            data = _read_json_file(progress_path)
            if not isinstance(data, dict):
                continue
            selections = data.get("selections") if isinstance(data.get("selections"), dict) else {}
            ligand_results = data.get("ligand_results") if isinstance(data.get("ligand_results"), dict) else {}
            report_path = str(selections.get("md_report") or "")
            output_dir = str(selections.get("output_dir") or progress_path.parent)
            best_ligand = None
            best_score = None
            for ligand, result in ligand_results.items():
                if not isinstance(result, dict) or result.get("mean_ddg_kcal") is None:
                    continue
                value = float(result.get("mean_ddg_kcal"))
                if best_score is None or value < best_score:
                    best_score = value
                    best_ligand = ligand
            if report_path or ligand_results:
                rows.append(
                    {
                        "key": f"md-optimization:{progress_path.parent.name}",
                        "name": Path(output_dir).name,
                        "summary_path": str(progress_path),
                        "delete_path": str(Path(output_dir).resolve()) if output_dir else str(progress_path.parent.resolve()),
                        "kind": "md-optimization",
                        "best_ligand": best_ligand,
                        "best_score": best_score,
                        "best_rmsd_heavy_atom": None,
                        "run_count": len(ligand_results),
                        "report_markdown": report_path,
                        "progress_json": str(progress_path),
                        "results_json": None,
                        "results_json_exists": False,
                        "results_csv": None,
                        "visualization_html": None,
                        "created_at": data.get("finished_at") or data.get("updated_at") or data.get("started_at"),
                    }
                )
        known_md_reports = {str(row.get("report_markdown") or "") for row in rows if row.get("kind") == "md-optimization"}
        md_report_paths: set[Path] = set()
        for reports in report_roots:
            md_report_paths.update(reports.glob("*/report/md_optimization_report.md"))
        for report_path in sorted(md_report_paths):
            report_value = str(report_path.resolve())
            if report_value in known_md_reports:
                continue
            output_dir = report_path.parent.parent
            progress_path = next((runs / output_dir.name / "progress.json" for runs in run_roots if (runs / output_dir.name / "progress.json").exists()), run_roots[0] / output_dir.name / "progress.json")
            data = _read_json_file(progress_path) if progress_path.exists() else {}
            ligand_results = data.get("ligand_results") if isinstance(data.get("ligand_results"), dict) else {}
            best_ligand = None
            best_score = None
            for ligand, result in ligand_results.items():
                if not isinstance(result, dict) or result.get("mean_ddg_kcal") is None:
                    continue
                value = float(result.get("mean_ddg_kcal"))
                if best_score is None or value < best_score:
                    best_score = value
                    best_ligand = ligand
            rows.append(
                {
                    "key": f"md-optimization:{output_dir.name}",
                    "name": output_dir.name,
                    "summary_path": str(progress_path) if progress_path.exists() else report_value,
                    "delete_path": str(output_dir.resolve()),
                    "kind": "md-optimization",
                    "best_ligand": best_ligand,
                    "best_score": best_score,
                    "best_rmsd_heavy_atom": None,
                    "run_count": len(ligand_results) if ligand_results else None,
                    "report_markdown": report_value,
                    "progress_json": str(progress_path) if progress_path.exists() else "",
                    "results_json": None,
                    "results_json_exists": False,
                    "results_csv": None,
                    "visualization_html": None,
                    "created_at": data.get("finished_at") or data.get("updated_at") or data.get("started_at") or datetime.fromtimestamp(report_path.stat().st_mtime, timezone.utc).isoformat(),
                }
            )
        _fep_paths: set[Path] = set()
        for runs in run_roots:
            _fep_paths.update(runs.glob("fep-*/progress.json"))
            _fep_paths.update(runs.glob("*-fep/progress.json"))
            _fep_paths.update(runs.glob("*-fep-*/progress.json"))
        for progress_path in sorted(_fep_paths):
            data = _read_json_file(progress_path)
            if not isinstance(data, dict):
                continue
            selections = data.get("selections") if isinstance(data.get("selections"), dict) else {}
            network_plan = data.get("network_plan") if isinstance(data.get("network_plan"), dict) else {}
            edge_results = data.get("edge_results") if isinstance(data.get("edge_results"), dict) else {}
            ranking = data.get("ligand_ranking") if isinstance(data.get("ligand_ranking"), list) else []
            report_path = str(selections.get("fep_report") or "")
            results_json = str(selections.get("fep_results_json") or "")
            default_report_root = _dashboard_user_root(self.root, username) / "reports"
            output_dir = str(selections.get("output_dir") or (default_report_root / progress_path.parent.name))
            best_ligand = None
            best_score = None
            for row in ranking:
                if not isinstance(row, dict):
                    continue
                value = row.get("ddG_bind_kcal")
                if value is None:
                    continue
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError):
                    continue
                if best_score is None or numeric_value < best_score:
                    best_score = numeric_value
                    best_ligand = row.get("ligand")
            if not best_ligand:
                for edge_name, result in edge_results.items():
                    if not isinstance(result, dict):
                        continue
                    value = result.get("ddG_bind_kcal")
                    if value is None:
                        continue
                    try:
                        numeric_value = float(value)
                    except (TypeError, ValueError):
                        continue
                    if best_score is None or numeric_value < best_score:
                        best_score = numeric_value
                        best_ligand = str(edge_name).split("__")[-1]
            transformation_count = int(selections.get("openfe_transformation_count") or network_plan.get("n_transformations") or len(data.get("openfe_transformations") or []) or 0)
            completed_count = len([row for row in (data.get("openfe_run_records") or []) if isinstance(row, dict) and row.get("status") == "completed"])
            if not completed_count:
                completed_count = len([row for row in edge_results.values() if isinstance(row, dict) and row.get("status") == "completed"])
            if report_path or results_json:
                rows.append(
                    {
                        "key": f"fep:{progress_path.parent.name}",
                        "name": Path(output_dir).name,
                        "summary_path": str(progress_path),
                        "delete_path": str(Path(output_dir).resolve()) if output_dir else str(progress_path.parent.resolve()),
                        "kind": "fep",
                        "best_ligand": best_ligand,
                        "best_score": best_score,
                        "best_rmsd_heavy_atom": None,
                        "run_count": completed_count,
                        "total_count": transformation_count,
                        "report_markdown": report_path,
                        "progress_json": str(progress_path),
                        "results_json": results_json if results_json and Path(results_json).exists() else None,
                        "results_json_exists": bool(results_json and Path(results_json).exists()),
                        "results_csv": str(selections.get("openfe_ddg_tsv") or ""),
                        "visualization_html": None,
                        "created_at": data.get("finished_at") or data.get("updated_at") or data.get("started_at"),
                        "status": data.get("status"),
                    }
                )
        export_paths: list[Path] = []
        for runs in run_roots:
            export_paths.extend(runs.glob("**/slurm*_export.json"))
        for reports in report_roots:
            export_paths.extend(reports.glob("**/slurm*_export.json"))
        for export_path in sorted(set(export_paths)):
            if export_path.name == "slurm_docking_export.json" and (export_path.parent.parent / "slurm_small_screen_export.json").exists():
                continue
            try:
                data = json.loads(export_path.read_text())
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            submit_script = data.get("submit_script") or data.get("docking_export_json")
            rows.append(
                {
                    "key": f"{data.get('backend', 'slurm-export')}:{export_path.parent.name}",
                    "name": export_path.parent.name,
                    "summary_path": str(export_path),
                    "delete_path": str(_report_delete_dir(self.root, export_path)),
                    "kind": str(data.get("backend") or "slurm-export"),
                    "best_ligand": None,
                    "best_score": None,
                    "best_rmsd_heavy_atom": None,
                    "run_count": data.get("ligand_count") or data.get("prepared_ligands"),
                    "report_markdown": submit_script,
                    "results_json": None,
                    "results_json_exists": False,
                    "results_csv": None,
                    "visualization_html": None,
                    "created_at": data.get("created_at"),
                }
            )
        return _dedupe_run_rows(sorted(rows, key=_run_sort_key, reverse=True))

    def _orchestration_progress(self, username: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        run_roots = [workspace_root / "runs" for workspace_root in _dashboard_workspace_roots(self.root, username)]
        for progress_path in sorted({path for runs in run_roots for path in runs.glob("terminal-orchestration-*/progress.json")}):
            data = _read_json_file(progress_path)
            if not isinstance(data, dict):
                continue
            selections = data.get("selections") if isinstance(data.get("selections"), dict) else {}
            output_value = str(selections.get("output_dir") or "").strip() if selections else ""
            output_dir = Path(output_value) if output_value else None
            report_dir = output_dir / "report" if output_dir and str(output_dir) else None
            data = dict(data)
            data["progress_json"] = str(progress_path)
            data["terminal_log"] = str(progress_path.parent / "terminal.log")
            if report_dir:
                data["report_markdown"] = str(report_dir / "docking_report.md") if (report_dir / "docking_report.md").exists() else ""
                data["results_json"] = str(output_dir / "vina_results.json") if (output_dir / "vina_results.json").exists() else ""
                data["results_csv"] = str(output_dir / "vina_results.csv") if (output_dir / "vina_results.csv").exists() else ""
            if output_dir and str(output_dir) and not data.get("benchmark_child_progress"):
                data["docking_progress"] = _orchestration_docking_progress(output_dir, selections)
            inferred_ligand_pdbqt_dir = _infer_ligand_pdbqt_dir_from_output(output_dir)
            if inferred_ligand_pdbqt_dir:
                selections = dict(selections)
                selections.setdefault("ligand_pdbqt_dir", inferred_ligand_pdbqt_dir)
                data.setdefault("ligand_pdbqt_dir", inferred_ligand_pdbqt_dir)
                data["selections"] = selections
            ligand_prep_output = str(selections.get("ligand_prep_output_dir") or "").strip()
            ligand_input = str(selections.get("ligand_input") or "").strip()
            if ligand_prep_output and ligand_input:
                data["ligand_prep_progress"] = _ligand_prep_progress_from_files(
                    self.root,
                    {"ligands": ligand_input, "out": ligand_prep_output},
                    {"phase": selections.get("ligand_prep_status") or "starting"},
                )
            if str(data.get("status") or "") == "running":
                _infer_orchestration_step_from_live_outputs(data)
            data["sort_time"] = str(data.get("updated_at") or data.get("finished_at") or data.get("started_at") or "")
            rows.append(data)
        for progress_path in sorted({path for runs in run_roots for path in runs.glob("*-docking/progress.json")}):
            data = _read_json_file(progress_path)
            if not isinstance(data, dict):
                continue
            if any(str(row.get("progress_json") or "") == str(progress_path) for row in rows):
                continue
            data = dict(data)
            run_label = str(data.get("run_label") or progress_path.parent.name.removesuffix("-docking"))
            workspace_root = progress_path.parents[2]
            report_dir = Path(str(data.get("report_dir") or workspace_root / "reports" / f"{run_label}-docking"))
            report_context = _read_json_file(report_dir / "report_context.json")
            if not isinstance(report_context, dict):
                report_context = {}
            selections = data.get("selections") if isinstance(data.get("selections"), dict) else {}
            if not selections:
                selections = {
                    "target_gene": report_context.get("target") or data.get("target") or "",
                    "target_label": report_context.get("target_id") or data.get("target_id") or data.get("target") or run_label,
                    "target_structure": report_context.get("receptor_pdb") or "",
                    "receptor_pdbqt": report_context.get("receptor_pdbqt") or "",
                    "binding_site_json": report_context.get("binding_site_json") or data.get("binding_site_json") or "",
                    "binding_site_label": report_context.get("binding_site_label") or report_context.get("target_id") or "",
                    "output_dir": str(report_dir),
                    "ligand_input": data.get("ligand_pdbqt_dir") or data.get("input_ligands") or report_context.get("input_ligands") or "",
                    "ligand_pdbqt_dir": data.get("ligand_pdbqt_dir") or report_context.get("input_ligands") or "",
                    "ligand_library_label": report_context.get("ligand_library") or "",
                    "ligand_labels_csv": report_context.get("ligand_labels_csv") or "",
                    "prepared_ligands_sdf": report_context.get("prepared_ligands_sdf") or "",
                    "max_ligands": data.get("target_count") or report_context.get("requested_max_ligands") or "",
                    "docking_parameters": data.get("vina_options") or report_context.get("vina_options") or {},
                }
            inferred_ligand_pdbqt_dir = _infer_ligand_pdbqt_dir_from_output(report_dir)
            if inferred_ligand_pdbqt_dir:
                selections = dict(selections)
                selections.setdefault("ligand_pdbqt_dir", inferred_ligand_pdbqt_dir)
                data.setdefault("ligand_pdbqt_dir", inferred_ligand_pdbqt_dir)
            if selections.get("binding_site_json") and not selections.get("binding_site_visualization_html"):
                site_json = Path(str(selections["binding_site_json"]))
                site_html = site_json.with_suffix(".html")
                if site_html.exists():
                    selections["binding_site_visualization_html"] = str(site_html)
            data["selections"] = selections
            data["progress_json"] = str(progress_path)
            data["terminal_log"] = str(workspace_root / "logs" / f"{run_label}.root-run.log")
            data["report_markdown"] = str(report_dir / "report" / "docking_report.md") if (report_dir / "report" / "docking_report.md").exists() else ""
            data["results_json"] = str(report_dir / "report" / "vina_results.json") if (report_dir / "report" / "vina_results.json").exists() else str(data.get("results_json") or "")
            data["results_csv"] = str(report_dir / "report" / "vina_results.csv") if (report_dir / "report" / "vina_results.csv").exists() else ""
            data["docking_progress"] = {
                "phase": data.get("phase") or data.get("current_step") or "docking",
                "prepared_count": int(data.get("prepared_count") or data.get("target_count") or 0),
                "docked_count": int(data.get("docked_count") or data.get("attempted_count") or 0),
                "attempted_count": int(data.get("attempted_count") or data.get("docked_count") or 0),
                "target_count": int(data.get("target_count") or data.get("prepared_count") or 0),
                "progress_percent": float(data.get("percent") or 0),
                "progress_label": str(data.get("message") or "Docking progress"),
                "active_vina_processes": _active_vina_process_count(workspace_root) if str(data.get("status") or "") == "running" else 0,
                "load_average": _system_load_average(),
                "output_dir": str(report_dir),
            }
            data["sort_time"] = str(data.get("updated_at") or data.get("finished_at") or data.get("started_at") or "")
            rows.append(data)
        status_rank = {"running": 3, "completed": 2, "failed": 1, "stopped": 0}
        return sorted(rows, key=lambda row: (status_rank.get(str(row.get("status") or ""), 1), str(row.get("sort_time") or "")), reverse=True)[:12]

    def _hit_refinement_progress(self, username: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        run_roots = [workspace_root / "runs" for workspace_root in _dashboard_workspace_roots(self.root, username)]
        progress_paths = {
            path
            for runs in run_roots
            for pattern in ("hit-refinement-*/progress.json", "*-hit-refinement/progress.json")
            for path in runs.glob(pattern)
        }
        for progress_path in sorted(progress_paths):
            data = _read_json_file(progress_path)
            if not isinstance(data, dict):
                continue
            data = dict(data)
            data["progress_json"] = str(progress_path)
            data["terminal_log"] = str(progress_path.parent / "terminal.log")
            data["sort_time"] = str(data.get("updated_at") or data.get("finished_at") or data.get("started_at") or "")
            rows.append(data)
        status_rank = {"running": 3, "completed": 2, "failed": 1, "stopped": 0}
        return sorted(rows, key=lambda row: (status_rank.get(str(row.get("status") or ""), 1), str(row.get("sort_time") or "")), reverse=True)[:8]

    def _md_optimization_progress(self, username: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        run_roots = [workspace_root / "runs" for workspace_root in _dashboard_workspace_roots(self.root, username)]
        progress_paths = {
            path
            for runs in run_roots
            for pattern in ("md-optimization-*/progress.json", "*-md-optimization/progress.json")
            for path in runs.glob(pattern)
        }
        for progress_path in sorted(progress_paths):
            data = _read_json_file(progress_path)
            if not isinstance(data, dict):
                continue
            data = dict(data)
            data["progress_json"] = str(progress_path)
            data["terminal_log"] = str(progress_path.parent / "terminal.log")
            data["sort_time"] = str(data.get("updated_at") or data.get("finished_at") or data.get("started_at") or "")
            rows.append(data)
        status_rank = {"running": 3, "completed": 2, "failed": 1, "stopped": 0}
        return sorted(rows, key=lambda row: (status_rank.get(str(row.get("status") or ""), 1), str(row.get("sort_time") or "")), reverse=True)[:8]

    def _fep_progress(self, username: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        run_roots = [workspace_root / "runs" for workspace_root in _dashboard_workspace_roots(self.root, username)]
        progress_paths = {
            path
            for runs in run_roots
            for pattern in ("fep-*/progress.json", "*-fep/progress.json")
            for path in runs.glob(pattern)
        }
        for progress_path in sorted(progress_paths):
            data = _read_json_file(progress_path)
            if not isinstance(data, dict):
                continue
            data = dict(data)
            _annotate_fep_network_similarity(data)
            _annotate_fep_live_openfe_status(data, progress_path)
            _annotate_fep_active_process(data, progress_path)
            data["progress_json"] = str(progress_path)
            data["terminal_log"] = str(progress_path.parent / "terminal.log")
            data["sort_time"] = str(data.get("sort_time") or data.get("updated_at") or data.get("finished_at") or data.get("started_at") or "")
            rows.append(data)
        return sorted(rows, key=_progress_sort_tuple, reverse=True)[:8]

    def _target_preparation(self, username: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        structure_keys = {record["cached_path"]: record["key"] for record in _dashboard_structure_records(self.root)}
        run_roots = [workspace_root / "runs" for workspace_root in _dashboard_workspace_roots(self.root, username)]
        for prep_json in sorted({path for runs in run_roots for path in runs.glob("**/protein_prep.json")}):
            try:
                prep = json.loads(prep_json.read_text())
            except json.JSONDecodeError:
                continue
            receptor_json = prep_json.parent / "receptor_prep.json"
            receptor = json.loads(receptor_json.read_text()) if receptor_json.exists() else None
            rows.append(
                {
                    "key": structure_keys.get(prep.get("input_path"), f"prep:{prep_json.parent.name}"),
                    "structure_path": prep.get("input_path"),
                    "protein_prep_json": str(prep_json),
                    "prepared_path": prep.get("prepared_path"),
                    "receptor_prep_json": str(receptor_json) if receptor_json.exists() else None,
                    "receptor_pdbqt": receptor.get("receptor_pdbqt") if receptor else None,
                    "status": "docking-ready" if receptor else "protein-prepared",
                }
            )
        return rows

    def _binding_sites(self, username: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        run_roots = [workspace_root / "runs" for workspace_root in _dashboard_workspace_roots(self.root, username)]
        for site_json in sorted({path for runs in run_roots for path in runs.glob("**/binding_site.json")}):
            try:
                site = json.loads(site_json.read_text())
            except json.JSONDecodeError:
                continue
            html_path = site_json.parent / "binding_site.html"
            rows.append(
                {
                    "key": f"site:{site_json.parent.name}",
                    "binding_site_json": str(site_json),
                    "structure_path": site.get("structure_path"),
                    "method": site.get("method"),
                    "selected_residues": site.get("selected_residues", []),
                    "center": site.get("box", {}).get("center"),
                    "size": site.get("box", {}).get("size"),
                    "visualization_html": str(html_path) if html_path.exists() else None,
                }
            )
        return rows


def serve_dashboard(root: Path, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True
        allow_reuse_port = True

    state = DashboardState(root)
    handler = _make_handler(state)
    server = _ReusableThreadingHTTPServer((host, port), handler)
    state.dashboard_port = int(server.server_port)
    url = f"http://{host}:{server.server_port}"
    print(f"OSLabLambda dashboard: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _make_handler(state: DashboardState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _check_basic_auth(self) -> bool:
            """If OSLAB_BASIC_AUTH=user:pass is set, require matching Basic auth.
            Returns True if authorized (or no auth configured), False if not."""
            expected = os.environ.get("OSLAB_BASIC_AUTH", "").strip()
            if not expected or ":" not in expected:
                return True
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Basic "):
                import base64 as _b64
                try:
                    decoded = _b64.b64decode(auth_header[6:]).decode("utf-8", errors="replace")
                    if decoded == expected:
                        return True
                except Exception:
                    pass
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", 'Basic realm="OSLab Dashboard"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return False

        def do_GET(self) -> None:  # noqa: N802
            if not self._check_basic_auth():
                return
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            query = _unredact_for_demo(query)
            username = get_request_user(self)
            _dashboard_user_layout(state.root, username)
            if parsed.path.startswith("/static/"):
                self._serve_static(parsed.path[len("/static/"):])
                return
            if parsed.path == "/":
                self._send_html(_load_dashboard_html())
                return
            if parsed.path == "/api/state":
                self._send_json(state.snapshot(username))
                return
            if parsed.path == "/api/report/read":
                try:
                    self._send_json(_read_report(state.root, query))
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/report/ligands":
                try:
                    self._send_json(_read_ligand_results(state.root, query))
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/report/pose-view":
                try:
                    self._send_json(_render_ligand_pose_view(state.root, query))
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            if parsed.path == "/api/md-optimization/pose-view":
                try:
                    self._send_json(_render_md_final_frame_view(state.root, query))
                except Exception as exc:
                    self._send_json({"error": str(exc)})
                return
            if parsed.path == "/api/fep/pose-view":
                try:
                    self._send_json(_render_fep_overlay_view(state.root, query))
                except Exception as exc:
                    self._send_json({"error": str(exc)})
                return
            if parsed.path == "/api/file":
                self._send_file(state.root, query)
                return
            if parsed.path == "/api/files/browse":
                self._send_json(_browse_files(state.root, query, username))
                return
            if parsed.path == "/api/jobs":
                self._send_json(state._jobs_snapshot(username))
                return
            if parsed.path == "/api/progress-scan":
                self._send_json(_scan_progress_files(state.root, query, username=username))
                return
            if parsed.path.startswith("/api/jobs/"):
                job = state.get_job_snapshot(parsed.path.rsplit("/", 1)[-1], username)
                if not job:
                    self._send_error(HTTPStatus.NOT_FOUND, "job not found")
                    return
                self._send_json(job)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "not found")

        def do_POST(self) -> None:  # noqa: N802
            if not self._check_basic_auth():
                return
            parsed = urlparse(self.path)
            try:
                payload = self._read_json()
                username = get_request_user(self)
                _dashboard_user_layout(state.root, username)
                payload.setdefault("username", username)
                if parsed.path == "/api/targets/search":
                    self._send_json(_search_targets(payload))
                    return
                if parsed.path == "/api/structures/fetch":
                    self._send_json(_fetch_structure(state.root, payload))
                    return
                if parsed.path == "/api/structure/preview":
                    self._send_json(_preview_structure(_dashboard_user_root(state.root, username), payload))
                    return
                if parsed.path == "/api/target/prepare":
                    self._send_json(_start_target_prep_job(state, payload, username))
                    return
                if parsed.path == "/api/binding-sites/propose":
                    self._send_json(_propose_binding_sites(_dashboard_user_root(state.root, username), payload))
                    return
                if parsed.path == "/api/binding-sites/create":
                    self._send_json(_create_binding_site(_dashboard_user_root(state.root, username), payload))
                    return
                if parsed.path == "/api/binding-sites/fpocket":
                    self._send_json(_run_fpocket_dashboard(_dashboard_user_root(state.root, username), payload))
                    return
                if parsed.path == "/api/ligands/inspect":
                    self._send_json(_inspect_ligands(payload, _dashboard_user_root(state.root, username)))
                    return
                if parsed.path == "/api/ligands/subsets":
                    self._send_json(_ligand_subsets(payload))
                    return
                if parsed.path == "/api/ligands/goal-count":
                    self._send_json(_ligand_goal_count(payload, state.root))
                    return
                if parsed.path == "/api/ligands/download":
                    job = _start_ligand_download_job(state, payload, username)
                    self._send_json(job.to_dict())
                    return
                if parsed.path == "/api/ligands/libraries/refresh":
                    self._send_json({"libraries": _dashboard_ligand_libraries(_dashboard_user_root(state.root, username), scan_dir=payload.get("scan_dir"))})
                    return
                if parsed.path == "/api/ligands/scan-local":
                    user_root = _dashboard_user_root(state.root, username)
                    scan_dir = _resolve_readable_input_path(user_root, str(payload.get("scan_dir") or user_root), field_name="scan folder")
                    self._send_json({"libraries": _scan_ligand_files(scan_dir, access=_path_access(user_root, scan_dir))})
                    return
                if parsed.path == "/api/ligands/provider-feedback":
                    self._send_json(_ligand_provider_feedback(payload))
                    return
                if parsed.path == "/api/ligands/prepare":
                    job = _start_ligand_prep_job(state, payload, username)
                    self._send_json(job.to_dict())
                    return
                if parsed.path == "/api/screen/small":
                    self._send_json(_start_small_screen_job(state, payload, username))
                    return
                if parsed.path == "/api/orchestrate":
                    self._send_json(_start_orchestrate_job(state, payload, username))
                    return
                if parsed.path == "/api/screen/slurm-export":
                    self._send_json(_start_slurm_screen_export_job(state, payload, username))
                    return
                if parsed.path == "/api/system/check-tools":
                    self._send_json(_dashboard_check_tools())
                    return
                if parsed.path == "/api/system/update-tools":
                    job = _start_update_tools_job(state, payload)
                    self._send_json(job.to_dict())
                    return
                if parsed.path == "/api/validation/cdk2":
                    self._send_json(_start_cdk2_validation_job(state, payload))
                    return
                if parsed.path == "/api/orchestration/guide":
                    self._send_json(guide_workflow(WorkflowInputState(**payload)).model_dump())
                    return
                if parsed.path == "/api/orchestration/start-terminal":
                    self._send_json(_start_terminal_orchestration(state, payload, username))
                    return
                if parsed.path == "/api/orchestration/delete":
                    self._send_json(_delete_orchestration_artifact(state, payload, username))
                    return
                if parsed.path == "/api/hit-refinement/start-terminal":
                    self._send_json(_start_hit_refinement_terminal(state, payload, username))
                    return
                if parsed.path == "/api/md-optimization/start":
                    self._send_json(_start_md_optimization_terminal(state, payload, username))
                    return
                if parsed.path == "/api/fep/start":
                    self._send_json(_start_fep_terminal(state, payload, username))
                    return
                if parsed.path == "/api/report/delete":
                    self._send_json(_delete_report(state.root, payload))
                    return
                if parsed.path == "/api/reports/package-last-target":
                    self._send_json(_package_last_target_results(state, payload, username))
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
            except Exception as exc:  # pragma: no cover - exercised through integration use
                self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            return _unredact_for_demo(json.loads(raw or "{}"))

        def _maybe_set_session_cookie(self) -> None:
            """If a new session was minted for this request, emit Set-Cookie."""
            sid = getattr(self, "_oslab_session_id", "")
            if not sid or not getattr(self, "_oslab_session_new", False):
                return
            # 30 days; HttpOnly+SameSite=Lax keeps it scoped to the dashboard.
            self.send_header(
                "Set-Cookie",
                f"{_SESSION_COOKIE_NAME}={sid}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000",
            )
            self._oslab_session_new = False  # only send once per request

        def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(_json_safe(_redact_for_demo(data)), indent=2, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self._maybe_set_session_cookie()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self._maybe_set_session_cookie()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, rel: str) -> None:
            safe_rel = rel.lstrip("/")
            if ".." in safe_rel.split("/"):
                self._send_error(HTTPStatus.FORBIDDEN, "invalid static path")
                return
            fp = (_DASHBOARD_STATIC_DIR / safe_rel).resolve()
            base = _DASHBOARD_STATIC_DIR.resolve()
            try:
                fp.relative_to(base)
            except ValueError:
                self._send_error(HTTPStatus.FORBIDDEN, "static path escapes root")
                return
            if not fp.is_file():
                self._send_error(HTTPStatus.NOT_FOUND, "static file not found")
                return
            ext = fp.suffix.lower()
            ctype = {
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".png": "image/png",
                ".svg": "image/svg+xml",
                ".ico": "image/x-icon",
                ".html": "text/html; charset=utf-8",
            }.get(ext, "application/octet-stream")
            body = fp.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, root: Path, query: dict[str, list[str]]) -> None:
            raw = query.get("path", [""])[0]
            raw_abs = Path(raw) if Path(raw).is_absolute() else (Path.cwd() / raw)
            requested = raw_abs.resolve()
            allowed = _allowed_report_roots(root)
            if not any(a in [requested, *requested.parents] for a in allowed):
                self._send_error(HTTPStatus.FORBIDDEN, "file must be under the project root")
                return
            if not requested.is_file():
                self._send_error(HTTPStatus.NOT_FOUND, "file not found")
                return
            suffix = requested.suffix.lower()
            content_type = "application/zip" if suffix == ".zip" else ("text/html; charset=utf-8" if suffix == ".html" else "text/plain; charset=utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if suffix == ".zip":
                safe_name = re.sub(r'[^A-Za-z0-9_. -]+', "_", requested.name).replace('"', "_")
                self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
            self.send_header("Content-Length", str(requested.stat().st_size))
            self.end_headers()
            with requested.open("rb") as handle:
                shutil.copyfileobj(handle, self.wfile, length=1024 * 1024)

        def _send_error(self, status: HTTPStatus, message: str) -> None:
            self._send_json({"error": message}, status)

    return Handler


def _scan_progress_files(root: Path, query: dict[str, list[str]], username: str | None = None) -> dict[str, Any]:
    """Scan OSLab root for active and recent progress.json files.

    Returns a list of runs with status, current step, percent, last message,
    and the report directory if known. The dashboard's monitor bar consumes this
    to surface runs that were started outside the dashboard (e.g. by an AI agent
    over SSH), since those don't appear in the in-memory job registry.

    Multi-user layout: each user's runs live under <root>/users/<user>/runs/,
    so we scan that directory first, then fall back to the legacy <root>/runs/
    for backwards compatibility.
    """
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    scan_dirs: list[Path] = []
    if username:
        user_root = _dashboard_user_root(root, username)
        user_runs = (user_root / "runs").resolve()
        if user_runs.is_dir():
            scan_dirs.append(user_runs)
        # Block 1 docking writes its progress.json under reports/<run>-docking/
        # (not runs/), so a workflow looks empty in the monitor until Block 2
        # starts. Also walk reports/ so live progress shows up immediately.
        user_reports = (user_root / "reports").resolve()
        if user_reports.is_dir() and user_reports not in scan_dirs:
            scan_dirs.append(user_reports)
    legacy_runs = (root / "runs").resolve()
    if legacy_runs.is_dir() and legacy_runs not in scan_dirs:
        scan_dirs.append(legacy_runs)
    progress_paths: list[Path] = []
    for runs_dir in scan_dirs:
        # Walk with followlinks=True so symlinked run dirs (used by the demo
        # workspace to surface read-only reference runs) are scanned.
        for dirpath, _dirnames, filenames in os.walk(runs_dir, followlinks=True):
            if "progress.json" in filenames:
                progress_paths.append(Path(dirpath) / "progress.json")
    if progress_paths:
        for progress_path in sorted(
            progress_paths,
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )[:50]:
            try:
                data = json.loads(progress_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            run_label = progress_path.parent.name
            if run_label in seen:
                continue
            seen.add(run_label)
            steps = data.get("steps") or []
            current_step = data.get("current_step") or data.get("phase") or ""
            status = data.get("status") or ""
            percent = data.get("percent")
            if percent is None and steps:
                done = sum(1 for s in steps if s.get("status") == "completed")
                if steps:
                    percent = round(100.0 * done / len(steps), 1)
            try:
                mtime = progress_path.stat().st_mtime
            except OSError:
                mtime = 0
            items.append({
                "run_label": run_label,
                "kind": data.get("kind", ""),
                "status": status,
                "current_step": current_step,
                "percent": percent,
                "message": (data.get("message") or "")[:240],
                "started_at": data.get("started_at", ""),
                "updated_at": data.get("updated_at", ""),
                "mtime": mtime,
                "progress_path": str(progress_path),
                "report_dir": str(data.get("report_dir", "")) if data.get("report_dir") else "",
                "results_json": str(data.get("results_json", "")) if data.get("results_json") else "",
                "step_count": len(steps),
                "completed_steps": sum(1 for s in steps if s.get("status") == "completed"),
                "steps": steps,
            })
    # The AI agent writes a real Block-1 (docking) progress.json only after
    # the full ligand-prep step has finished. While the agent is still in
    # setup (target prep, binding-site, ligand-prep) or running per-ligand
    # docking, the only live source of truth is the wrapper
    # `terminal-orchestration` progress.json. Synthesise a Block-1 entry from
    # it so the user sees a Block-1 bar in the live monitor immediately, not
    # only after Block 2 starts.
    real_labels = {item["run_label"] for item in items}
    _SETUP_STEPS = {"target", "target-prep", "binding-site", "ligands", "ligand-prep"}
    for item in list(items):
        if item.get("kind") != "terminal-orchestration":
            continue
        label = item.get("run_label", "")
        if not label.startswith("terminal-orchestration-"):
            continue
        base = label[len("terminal-orchestration-"):]
        synth_label = f"{base}-docking"
        if synth_label in real_labels:
            continue
        current = (item.get("current_step") or "").strip()
        if current in _SETUP_STEPS:
            synth_current = f"setup: {current}"
        elif current == "docking":
            synth_current = "docking"
        elif current == "report":
            synth_current = "wrapping up"
        else:
            synth_current = current or "running"
        synth = dict(item)
        synth.update({
            "run_label": synth_label,
            # kind="docking" so the dashboard's BLOCK_MAP groups this as Block 1.
            "kind": "docking",
            "current_step": synth_current,
            "synthesized_from": label,
        })
        items.append(synth)
        real_labels.add(synth_label)
    return {"runs": items}



def _browse_files(root: Path, query: dict[str, list[str]], username: str | None = None) -> dict[str, Any]:
    requested_text = query.get("path", [""])[0].strip()
    mode = query.get("mode", ["path"])[0].strip().lower() or "path"
    user_root = _dashboard_user_root(root, username)
    allowed_roots = _allowed_browse_roots(user_root)

    def _safe_path(value: str) -> Path:
        if not value or "$" in value or value.startswith("__REQUIRED_"):
            return user_root.resolve()
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = user_root / candidate
        candidate = candidate.resolve()
        if not any(base in [candidate, *candidate.parents] for base in allowed_roots):
            return user_root.resolve()
        return candidate

    requested = _safe_path(requested_text)
    current = requested if requested.is_dir() else requested.parent
    if not current.exists() or not current.is_dir():
        current = user_root.resolve()
    entries: list[dict[str, Any]] = []
    try:
        children = list(current.iterdir())
    except OSError as exc:
        return {
            "path": str(current),
            "parent": str(current.parent if current.parent != current else current),
            "mode": mode,
            "entries": [],
            "error": str(exc),
            "allowed_roots": [{"path": str(path), "scope": _path_scope_label(user_root, path)} for path in allowed_roots],
        }
    for child in sorted(children, key=lambda item: (not item.is_dir(), item.name.lower()))[:500]:
        try:
            stat = child.stat()
            is_dir = child.is_dir()
            selectable = (mode == "folder" and is_dir) or (mode == "file" and child.is_file()) or mode not in {"file", "folder"}
            entries.append(
                {
                    "name": child.name,
                    "path": str(child),
                    "type": "folder" if is_dir else "file",
                    "size": 0 if is_dir else stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "selectable": selectable,
                }
            )
        except OSError:
            continue
    return {
        "path": str(current),
        "parent": str(current.parent if current.parent != current else current),
        "mode": mode,
        "entries": entries,
        "allowed_roots": [{"path": str(path), "scope": _path_scope_label(user_root, path)} for path in allowed_roots],
    }


def _shared_data_root(root: Path) -> Path | None:
    env_meta = _run_environment_metadata(root)
    configured = (
        str(env_meta.get("shared_data_root") or env_meta.get("oslab_shared_data") or "").strip()
        or os.environ.get("OSLAB_SHARED_DATA", "").strip()
    )
    if not configured:
        default_shared = Path("/data/oslab")
        if default_shared.exists() and default_shared.resolve() != root.resolve():
            return default_shared.resolve()
        return None
    try:
        shared = Path(configured).expanduser().resolve()
    except OSError:
        return None
    if shared.exists() and shared != root.resolve():
        return shared
    return None


def _project_root_from_user_root(root: Path) -> Path | None:
    """Return the shared project root for a user workspace root, if determinable."""
    metadata_path = root / ".oslab" / "project.json"
    try:
        if metadata_path.exists():
            meta = json.loads(metadata_path.read_text())
            pr = meta.get("project_root")
            if pr:
                return Path(pr).expanduser().resolve()
    except Exception:
        pass
    # Fallback: user root is always <project_root>/users/<username>
    candidate = root.parent.parent
    if candidate != root and candidate.exists():
        return candidate
    return None


def _allowed_browse_roots(root: Path) -> list[Path]:
    roots: list[Path] = []
    project_root = _project_root_from_user_root(root)
    for candidate in [root, project_root, Path.home(), _shared_data_root(root)]:
        if not candidate:
            continue
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists() and resolved not in roots:
            roots.append(resolved)
    return roots


def _allowed_input_roots(root: Path) -> list[Path]:
    return _allowed_browse_roots(root)


def _path_scope_label(root: Path, path: Path) -> str:
    resolved = path.resolve()
    root_resolved = root.resolve()
    shared = _shared_data_root(root)
    if _is_within(resolved, root_resolved):
        return "personal workspace"
    if shared and _is_within(resolved, shared):
        return "shared read-only"
    if _is_within(resolved, Path.home().resolve()):
        return "user home"
    return "external"


def _path_access(root: Path, path: Path) -> str:
    shared = _shared_data_root(root)
    if shared and _is_within(path.resolve(), shared):
        return "shared-file"
    return "local-file"


def _resolve_readable_input_path(root: Path, value: str | Path, *, field_name: str = "input path") -> Path:
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    allowed_roots = _allowed_input_roots(root)
    if not any(_is_within(resolved, base) for base in allowed_roots):
        allowed = ", ".join(str(base) for base in allowed_roots)
        raise ValueError(f"{field_name} must be under the user workspace, user home, or shared data root. Allowed roots: {allowed}")
    return resolved


def _resolve_workspace_output_dir(root: Path, value: str | Path | None, default: Path, *, field_name: str = "output directory") -> Path:
    if value is None or not str(value).strip():
        resolved = default.resolve()
    else:
        requested = Path(str(value)).expanduser()
        if not requested.is_absolute():
            requested = root / requested
        resolved = requested.resolve()
    if not _is_within(resolved, root.resolve()):
        raise ValueError(f"{field_name} must be inside this user's OSLab root: {root}")
    return resolved


def _fetch_structure(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source")
    if source == "pdb":
        pdb_id = str(payload["identifier"]).strip()
        if not re.match(r"^[0-9][A-Za-z0-9]{3}$", pdb_id):
            raise ValueError("RCSB PDB fetch requires a 4-character PDB ID, such as 1HCK. Use Search by Gene first for gene symbols.")
        record = fetch_pdb_structure(
            pdb_id=pdb_id,
            root=root,
            file_format=str(payload.get("format") or "cif"),
            overwrite=bool(payload.get("overwrite", False)),
        )
        return record.model_dump(mode="json")
    if source == "alphafold":
        version = payload.get("model_version")
        record = fetch_alphafold_structure(
            uniprot_accession=str(payload["identifier"]),
            root=root,
            model_version=int(version) if version else None,
            overwrite=bool(payload.get("overwrite", False)),
        )
        return record.model_dump(mode="json")
    if source == "local":
        record = register_local_structure(
            input_path=_resolve_readable_input_path(root, str(payload["path"]), field_name="local structure file"),
            root=root,
            identifier=payload.get("identifier"),
            file_format=payload.get("format"),
            copy=not bool(payload.get("no_copy", False)),
            overwrite=bool(payload.get("overwrite", False)),
        )
        return record.model_dump(mode="json")
    raise ValueError("source must be pdb, alphafold, or local")


def _search_targets(payload: dict[str, Any]) -> dict[str, Any]:
    gene = str(payload.get("gene") or "").strip()
    if not gene:
        raise ValueError("gene is required")
    organism = str(payload.get("organism_id") or "9606").strip()
    size = int(payload.get("size") or 8)
    pdb_rows = _search_rcsb_by_gene(gene, size)
    alphafold_rows = _search_uniprot_for_alphafold(gene, organism, size)
    return {
        "gene": gene,
        "organism_id": organism,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "pdb": pdb_rows,
        "alphafold": alphafold_rows,
    }


TARGET_SEARCH_ALIASES = {
    "HIVRT": ["HIV reverse transcriptase", "HIV-1 reverse transcriptase", "reverse transcriptase HIV-1"],
    "HIV_RT": ["HIV reverse transcriptase", "HIV-1 reverse transcriptase", "reverse transcriptase HIV-1"],
    "HIV-RT": ["HIV reverse transcriptase", "HIV-1 reverse transcriptase", "reverse transcriptase HIV-1"],
    "AMPC": ["AmpC beta-lactamase", "beta lactamase AmpC"],
}


def _search_rcsb_by_gene(gene: str, size: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    query_terms = [gene]
    query_terms.extend(TARGET_SEARCH_ALIASES.get(gene.strip().upper(), []))
    for term in query_terms:
        body = {
            "query": {
                "type": "terminal",
                "service": "full_text",
                "parameters": {"value": term},
            },
            "return_type": "entry",
            "request_options": {"paginate": {"start": 0, "rows": size}},
        }
        request = urllib.request.Request(
            "https://search.rcsb.org/rcsbsearch/v2/query",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        data = _safe_urlopen_json(request) or {}
        for item in data.get("result_set", [])[:size]:
            pdb_id = item.get("identifier")
            if not pdb_id or pdb_id in seen:
                continue
            seen.add(pdb_id)
            entry = _safe_urlopen_json(f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}") or {}
            rows.append(
                {
                    "source": "pdb",
                    "identifier": pdb_id,
                    "title": entry.get("struct", {}).get("title", ""),
                    "experimental_method": "; ".join(entry.get("exptl", [{}])[0].get("method", "") for _ in [0])
                    if entry.get("exptl")
                    else "",
                    "resolution": _entry_resolution(entry),
                    "fetch": {"source": "pdb", "identifier": pdb_id, "format": "cif"},
                    "matched_query": term,
                }
            )
            if len(rows) >= size:
                return rows
    return rows


def _search_uniprot_for_alphafold(gene: str, organism: str, size: int) -> list[dict[str, Any]]:
    query = quote(f"gene_exact:{gene} AND organism_id:{organism}")
    fields = "accession,id,protein_name,gene_names,organism_name,length"
    url = f"https://rest.uniprot.org/uniprotkb/search?query={query}&format=json&fields={fields}&size={size}"
    data = _safe_urlopen_json(url) or {}
    rows: list[dict[str, Any]] = []
    for result in data.get("results", [])[:size]:
        accession = result.get("primaryAccession")
        if not accession:
            continue
        rows.append(
            {
                "source": "alphafold",
                "identifier": accession,
                "title": result.get("proteinDescription", {}).get("recommendedName", {}).get("fullName", {}).get("value", ""),
                "gene_names": [gene_entry.get("geneName", {}).get("value") for gene_entry in result.get("genes", [])],
                "organism": result.get("organism", {}).get("scientificName", ""),
                "length": result.get("sequence", {}).get("length"),
                "fetch": {"source": "alphafold", "identifier": accession},
            }
        )
    return rows


def _start_target_prep_job(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    username = safe_user_name(username or payload.get("username") or get_request_user())
    workspace_root = _dashboard_user_root(state.root, username)
    job = state.add_job(DashboardJob(id=uuid.uuid4().hex[:12], kind="target-prep", username=username, request=payload))
    thread = threading.Thread(target=_run_target_prep_job, args=(state, job.id, payload, workspace_root), daemon=True)
    thread.start()
    return job.to_dict()


def _run_target_prep_job(state: DashboardState, job_id: str, payload: dict[str, Any], workspace_root: Path | None = None) -> None:
    state.update_job(job_id, status="running")
    root = workspace_root or state.root
    try:
        structure = _resolve_readable_input_path(root, str(payload["structure_path"]), field_name="structure path")
        output_dir = _resolve_workspace_output_dir(
            root,
            payload.get("out"),
            root / "runs" / f"target-prep-{structure.stem}",
            field_name="target prep output directory",
        )
        prep = prepare_protein(
            structure,
            output_dir,
            ProteinPrepOptions(
                ph=float(payload.get("ph") or 7.4),
                keep_water=bool(payload.get("keep_water", False)),
                minimize=not bool(payload.get("no_minimize", True)),
                max_minimization_iterations=int(payload.get("max_minimization_iterations") or 500),
            ),
        )
        receptor = prepare_receptor_for_vina(
            Path(prep.prepared_path),
            output_dir,
            allow_bad_residues=bool(payload.get("allow_bad_residues", True)),
            default_altloc=payload.get("default_altloc") or None,
            delete_residues=payload.get("delete_residues") or None,
        )
        state.update_job(
            job_id,
            status="completed",
            result={"protein_prep": prep.model_dump(mode="json"), "receptor_prep": receptor.model_dump(mode="json")},
        )
    except Exception as exc:  # pragma: no cover - exercised through integration use
        state.update_job(job_id, status="failed", error=str(exc))


def _propose_binding_sites(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    structure_path = _resolve_readable_input_path(root, str(payload["structure_path"]), field_name="structure path")
    ligands = find_ligand_residue_names(structure_path)
    preview_html = render_structure_html(
        structure_path,
        root / "runs" / "dashboard-previews" / structure_path.stem / "structure.html",
        title=f"{structure_path.name} Structure Preview",
    )
    return {
        "structure_path": str(structure_path.resolve()),
        "visualization_html": str(preview_html),
        "methods": [
            {
                "key": "ligand-centroid",
                "name": "Known ligand centroid",
                "available_ligands": ligands,
                "recommended": bool(ligands),
                "notes": "Best for redocking and known active-site structures.",
            },
            {
                "key": "residue-centroid",
                "name": "Residue centroid",
                "available_ligands": [],
                "recommended": False,
                "notes": "Use when active-site residues are known from biology or literature.",
            },
        ],
    }


def _preview_structure(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    structure_path = _resolve_readable_input_path(root, str(payload["structure_path"]), field_name="structure path")
    preview_html = render_structure_html(
        structure_path,
        root / "runs" / "dashboard-previews" / structure_path.stem / "structure.html",
        title=f"{structure_path.name} Structure Preview",
    )
    return {"structure_path": str(structure_path.resolve()), "visualization_html": str(preview_html)}


def _create_binding_site(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    structure_path = _resolve_readable_input_path(root, str(payload["structure_path"]), field_name="structure path")
    method = str(payload.get("method") or "ligand-centroid")
    pocket = payload.get("pocket")
    default_name = f"binding-site-{structure_path.stem}"
    if method == "fpocket" and isinstance(pocket, dict):
        default_name = f"{default_name}-pocket-{pocket.get('pocket_id') or 'selected'}"
    requested_out = str(payload.get("out") or "").strip()
    output_dir = _resolve_workspace_output_dir(root, requested_out or None, root / "runs" / default_name, field_name="binding-site output directory")
    padding = float(payload.get("padding") or 6.0)
    minimum_size = float(payload.get("minimum_size") or 12.0)
    if method == "ligand-centroid":
        record = box_from_ligand(
            structure_path,
            ligand=str(payload["ligand"]),
            output_dir=output_dir,
            chain=payload.get("chain") or None,
            padding=padding,
            minimum_size=minimum_size,
        )
    elif method == "residue-centroid":
        residues = payload.get("residues")
        if isinstance(residues, str):
            residues = [part.strip() for part in residues.split(",") if part.strip()]
        record = box_from_residues(structure_path, residues or [], output_dir=output_dir, padding=padding, minimum_size=minimum_size)
    elif method == "fpocket":
        if not isinstance(pocket, dict):
            raise ValueError("fpocket binding-site creation requires a selected pocket")
        record = box_from_fpocket(structure_path, pocket, output_dir=output_dir, padding=padding, minimum_size=minimum_size)
    else:
        raise ValueError("method must be ligand-centroid, residue-centroid, or fpocket")
    html_path = render_binding_site_html(structure_path, Path(record.metadata_path), output_dir / "binding_site.html")
    return {"binding_site": record.model_dump(mode="json"), "visualization_html": str(html_path)}


def _run_fpocket_dashboard(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    structure_path = _resolve_readable_input_path(root, str(payload["structure_path"]), field_name="structure path")
    output_dir = _resolve_workspace_output_dir(
        root,
        payload.get("out"),
        root / "runs" / f"fpocket-{structure_path.stem}",
        field_name="fpocket output directory",
    )
    target_identifier = (
        str(payload.get("target_identifier") or payload.get("pdb_id") or payload.get("uniprot_accession") or "").strip()
        or structure_path.stem
    )
    result = run_fpocket(
        structure_path,
        output_dir,
        top_n=int(payload.get("top_n") or 8),
        min_spheres=int(payload.get("min_spheres") or 15),
        target_identifier=target_identifier or None,
    )
    html_path = render_pockets_html(
        structure_path,
        result["pockets"],  # type: ignore[arg-type]
        output_dir / "fpocket_pockets.html",
        title=f"{structure_path.name} fpocket Pockets",
    )
    result["visualization_html"] = str(html_path)
    (output_dir / "fpocket_pockets.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def _inspect_ligands(payload: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    ligand_path = (
        _resolve_readable_input_path(root, str(payload["ligands"]), field_name="ligand input")
        if root is not None
        else Path(str(payload["ligands"])).expanduser().resolve()
    )
    suffix = ligand_path.suffix.lower()
    if not ligand_path.exists():
        raise FileNotFoundError(ligand_path)
    if ligand_path.is_dir():
        return _inspect_ligand_folder(ligand_path)
    if _is_vina_ready_ligand_input(ligand_path):
        return {
            "input_path": str(ligand_path),
            "path_kind": "file",
            "format": "pdbqt.gz" if ligand_path.name.endswith(".pdbqt.gz") else (suffix.lstrip(".") or "pdbqt"),
            "count": 1,
            "vina_ready": True,
            "valid_ligand_library": True,
            "needs_rdkit_meeko": False,
            "notes": "Trusted PDBQT input is treated as already prepared for Vina. Compressed .pdbqt.gz downloads are decompressed by the dashboard downloader.",
        }
    molecules = load_ligands(ligand_path)
    return {
        "input_path": str(ligand_path),
        "path_kind": "file",
        "format": suffix.lstrip("."),
        "count": len(molecules),
        "valid_ligand_library": True,
        "vina_ready": False,
        "needs_rdkit_meeko": True,
        "notes": "This input can be filtered with RDKit and prepared with Open Babel plus Meeko.",
    }


def _inspect_ligand_folder(folder: Path) -> dict[str, Any]:
    ligand_suffixes = {
        ".pdbqt",
        ".smi",
        ".smiles",
        ".sdf",
        ".sd",
        ".mol2",
        ".csv",
        ".tsv",
    }
    compressed_suffixes = {".pdbqt.gz"}
    skip_dirs = {
        "__pycache__",
        ".git",
        ".ipynb_checkpoints",
        "logs",
        "reports",
        "report",
        "poses",
        "viewer",
        "cache",
    }
    counts: dict[str, int] = {}
    samples: list[str] = []
    visited_dirs = 0
    total_files = 0
    count_truncated = False
    max_files_to_count = 250000
    for dirpath, dirnames, filenames in os.walk(folder):
        visited_dirs += 1
        if visited_dirs > 500:
            count_truncated = True
            break
        dirnames[:] = [name for name in dirnames if name not in skip_dirs and not name.startswith(".")]
        for filename in filenames:
            name = filename.lower()
            file_format = ""
            if any(name.endswith(suffix) for suffix in compressed_suffixes):
                file_format = "pdbqt.gz"
            else:
                suffix = Path(filename).suffix.lower()
                if suffix in ligand_suffixes:
                    file_format = suffix.lstrip(".")
            if not file_format:
                continue
            total_files += 1
            counts[file_format] = counts.get(file_format, 0) + 1
            if len(samples) < 8:
                samples.append(str((Path(dirpath) / filename).resolve()))
            if total_files >= max_files_to_count:
                count_truncated = True
                break
        if total_files >= max_files_to_count:
            break

    pdbqt_count = counts.get("pdbqt", 0) + counts.get("pdbqt.gz", 0)
    source_count = sum(count for fmt, count in counts.items() if fmt not in {"pdbqt", "pdbqt.gz"})
    valid = total_files > 0
    vina_ready = pdbqt_count > 0 and source_count == 0
    mixed = pdbqt_count > 0 and source_count > 0
    if not valid:
        notes = "No ligand-looking files were found. Choose a folder containing .pdbqt, .smi, .sdf, .mol2, .csv, or .tsv ligand files."
    elif vina_ready:
        prefix = "at least " if count_truncated else ""
        notes = f"Folder contains {prefix}{pdbqt_count} PDBQT ligand file(s), so it looks ready for AutoDock Vina."
    elif mixed:
        prefix = "at least " if count_truncated else ""
        notes = f"Folder contains {prefix}{pdbqt_count} PDBQT file(s) and {source_count} source ligand file(s). Prefer selecting the prepared PDBQT folder for docking, or a source file/folder for ligand prep."
    else:
        prefix = "at least " if count_truncated else ""
        notes = f"Folder contains {prefix}{source_count} source ligand file(s). It should be prepared with RDKit/Meeko before docking."
    return {
        "input_path": str(folder),
        "path_kind": "folder",
        "format": "folder",
        "count": pdbqt_count if vina_ready else None,
        "file_count": total_files,
        "counts_by_format": counts,
        "sample_files": samples,
        "valid_ligand_library": valid,
        "vina_ready": vina_ready,
        "needs_rdkit_meeko": valid and not vina_ready,
        "mixed_formats": mixed,
        "count_truncated": count_truncated,
        "notes": notes,
    }


def _is_vina_ready_ligand_input(path: Path) -> bool:
    """Only actual PDBQT files are already Vina-ready; source catalogs may mix formats."""
    name = path.name.lower()
    return name.endswith(".pdbqt") or name.endswith(".pdbqt.gz")


def _ligand_subsets(payload: dict[str, Any]) -> dict[str, Any]:
    source = str(payload.get("source") or "")
    if source != "zinc3d-pdbqt":
        return {
            "source": source,
            "subsets": [],
            "notes": "This source does not yet have an automated subset browser. Use its provider page, then scan or enter the downloaded local file.",
        }
    tranche_prefix = str(payload.get("tranche_prefix") or "AA").upper().strip()
    file_format = str(payload.get("format") or "smi").lower().strip().lstrip(".")
    max_dirs = max(1, min(int(payload.get("max_dirs") or 25), 100))
    max_files = max(1, min(int(payload.get("max_files") or 100), 300))
    return _zinc_subset_rows(tranche_prefix=tranche_prefix, file_format=file_format, max_dirs=max_dirs, max_files=max_files)


def _zinc_subset_rows(tranche_prefix: str, file_format: str, max_dirs: int, max_files: int) -> dict[str, Any]:
    base_url = "https://cache.docking.org/3D/"
    top_dirs = [name for name in _apache_links(base_url) if name.endswith("/") and re.match(r"^[A-Z]{2}/$", name)]
    if tranche_prefix:
        top_dirs = [name for name in top_dirs if name.startswith(tranche_prefix[:2])]
    subsets: list[dict[str, Any]] = []
    for top_dir in top_dirs[:max_dirs]:
        top_url = urljoin(base_url, top_dir)
        all_child_dirs = [name for name in _apache_links(top_url) if name.endswith("/")]
        if file_format == "pdbqt":
            child_dirs = all_child_dirs
        else:
            child_dirs = [name for name in all_child_dirs if not name.endswith(".d/")]
        for child_dir in child_dirs[:max_dirs]:
            child_url = urljoin(top_url, child_dir)
            for file_name, file_url, tranche_dir in _zinc_matching_files(child_url, child_dir, file_format, max_nested=max_dirs):
                subsets.append(_zinc_subset_row(top_dir, tranche_dir, file_name, file_url))
                if len(subsets) >= max_files:
                    return {
                        "source": "zinc3d-pdbqt",
                        "subsets": subsets,
                        "notes": f"Showing first {len(subsets)} matching ZINC files. Narrow the tranche prefix or format for a smaller list.",
                    }
    return {
        "source": "zinc3d-pdbqt",
        "subsets": subsets,
        "notes": f"Found {len(subsets)} matching ZINC files for tranche prefix {tranche_prefix or 'any'} and format {file_format}.",
    }


def _zinc_matching_files(directory_url: str, directory_name: str, file_format: str, max_nested: int = 25) -> list[tuple[str, str, str]]:
    links = _apache_links(directory_url)
    rows: list[tuple[str, str, str]] = []
    nested_dirs_checked = 0
    for link in links:
        if link.endswith("/"):
            if link == "../":
                continue
            if nested_dirs_checked >= max_nested:
                break
            nested_dirs_checked += 1
            for nested in _apache_links(urljoin(directory_url, link)):
                if _zinc_file_matches(nested, file_format):
                    rows.append((nested, urljoin(urljoin(directory_url, link), nested), link))
        elif _zinc_file_matches(link, file_format):
            rows.append((link, urljoin(directory_url, link), directory_name))
    return rows


def _zinc_file_matches(file_name: str, file_format: str) -> bool:
    if file_format == "pdbqt":
        return file_name.endswith(".pdbqt") or file_name.endswith(".pdbqt.gz")
    if file_format == "sdf":
        return file_name.endswith(".sdf") or file_name.endswith(".sdf.gz")
    if file_format == "mol2":
        return file_name.endswith(".mol2") or file_name.endswith(".mol2.gz")
    if file_format == "db2":
        return file_name.endswith(".db2") or file_name.endswith(".db2.gz")
    return file_name.endswith(f".{file_format}")


def _ligand_provider_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    source = str(payload.get("source") or "")
    url = str(payload.get("url") or "").strip()
    if not url:
        raise ValueError("provider URL is required")
    try:
        status, final_url, headers, preview = _provider_preview(url)
    except urllib.error.HTTPError as exc:
        preview = exc.read(8192)
        return _provider_feedback_from_response(source, url, exc.geturl(), exc.code, dict(exc.headers), preview)
    return _provider_feedback_from_response(source, url, final_url, status, headers, preview)


def _provider_preview(url: str) -> tuple[int, str, dict[str, str], bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "OpenStructureLab/0.1",
            "Range": "bytes=0-8191",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.status, response.geturl(), dict(response.headers), response.read(8192)


def _provider_feedback_from_response(
    source: str,
    url: str,
    final_url: str,
    status: int,
    headers: dict[str, str],
    preview: bytes,
) -> dict[str, Any]:
    content_type = headers.get("Content-Type") or headers.get("content-type") or ""
    message = _provider_message(preview)
    lowered = f"{final_url} {content_type} {message} {preview[:2048].decode('utf-8', errors='ignore')}".lower()
    requires_login = any(token in lowered for token in ["login", "sign in", "signin", "password", "credentials", "authentication"])
    access_blocked = status in {401, 403} or any(token in lowered for token in ["access denied", "forbidden", "not authorized"])
    if requires_login:
        state = "login-required"
        note = "Provider redirected to, or displayed, a login page. Use browser/provider credentials or a downloaded local file."
        if not message or "initn3t" in message.lower():
            message = "Login required"
    elif access_blocked:
        state = "blocked"
        note = "Provider blocked scripted access. Use the provider website or download the file interactively, then scan the local file."
    elif "text/html" in content_type.lower() and _looks_like_ligand_download(url):
        state = "provider-message"
        note = "Provider returned an HTML message instead of a ligand data file."
    else:
        state = "available"
        note = "Provider endpoint is reachable."
    return {
        "source": source,
        "url": url,
        "final_url": final_url,
        "status": status,
        "content_type": content_type,
        "content_length": headers.get("Content-Length") or headers.get("content-length") or "",
        "access_state": state,
        "requires_login": requires_login,
        "access_blocked": access_blocked,
        "provider_message": message,
        "notes": note,
    }


def _provider_message(preview: bytes) -> str:
    text = preview.decode("utf-8", errors="replace")
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    for pattern in [r"<title[^>]*>(.*?)</title>", r"<h1[^>]*>(.*?)</h1>", r"<h2[^>]*>(.*?)</h2>"]:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return _clean_html_text(match.group(1))
    lines = [_clean_html_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return lines[0][:240] if lines else ""


def _clean_html_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()[:240]


def _looks_like_ligand_download(url: str) -> bool:
    path = urlparse(url).path.lower()
    return path.endswith((".smi", ".smiles", ".sdf", ".sd", ".pdbqt", ".pdbqt.gz", ".mol2", ".db2", ".csv", ".tsv"))


def _zinc_subset_row(top_dir: str, child_dir: str, file_name: str, url: str) -> dict[str, Any]:
    tranche = child_dir.strip("/")
    return {
        "source_key": "zinc3d-pdbqt",
        "subset_key": f"zinc:{tranche}:{file_name}",
        "name": file_name,
        "tranche": tranche,
        "size_bin": top_dir.strip("/"),
        "url": url,
        "format": _download_format(file_name),
        "vina_ready": file_name.endswith(".pdbqt") or file_name.endswith(".pdbqt.gz"),
        "prep": "none" if file_name.endswith(".pdbqt") or file_name.endswith(".pdbqt.gz") else "required",
        "filters": _zinc_tranche_description(tranche),
        "molecule_count": "provider file; inspect after download",
        "notes": "ZINC static tranche file. Check provider license/redistribution terms before large downloads.",
    }


def _zinc_tranche_description(tranche: str) -> str:
    if len(tranche) < 4:
        return "ZINC size/polarity tranche"
    reactivity = {"A": "anodyne", "B": "bother", "C": "clean", "E": "mild reactive", "G": "reactive", "I": "hot chemistry"}.get(tranche[2], tranche[2])
    ph_charge = tranche[3:]
    return f"size/polarity {tranche[:2]}; reactivity/purchasability/pH/charge code {ph_charge}; reactivity {reactivity}"


def _apache_links(url: str) -> list[str]:
    with urllib.request.urlopen(url, timeout=20) as response:
        html_text = response.read().decode("utf-8", errors="replace")
    return [
        match.group(1)
        for match in re.finditer(r'href="([^"]+)"', html_text)
        if not match.group(1).startswith("?") and not match.group(1).startswith("/") and match.group(1) != "../"
    ]


def _download_format(file_name: str) -> str:
    name = file_name[:-3] if file_name.endswith(".gz") else file_name
    return Path(name).suffix.lstrip(".") or "unknown"


def _start_ligand_download_job(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> DashboardJob:
    username = safe_user_name(username or payload.get("username") or get_request_user())
    workspace_root = _dashboard_user_root(state.root, username)
    job = state.add_job(DashboardJob(id=uuid.uuid4().hex[:12], kind="ligand-download", username=username, request=payload))
    thread = threading.Thread(target=_run_ligand_download_job, args=(state, job.id, payload, workspace_root), daemon=True)
    thread.start()
    return job


def _run_ligand_download_job(state: DashboardState, job_id: str, payload: dict[str, Any], workspace_root: Path | None = None) -> None:
    root = workspace_root or state.root
    try:
        urls = [str(url) for url in payload.get("urls", [])] or [str(payload["url"])]
        out_dir = _resolve_workspace_output_dir(
            root,
            payload.get("out_dir"),
            root / "data-cache" / "ligands" / "downloads",
            field_name="ligand download output directory",
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        max_mb = float(payload.get("max_mb") or 500)
        combine_name = payload.get("combine_name")
        planned_output = out_dir / Path(str(combine_name)).name if combine_name else out_dir / Path(urlparse(urls[0]).path).name
        source_key = str(payload.get("source") or "custom-sdf")
        progress: dict[str, Any] = {
            "phase": "starting",
            "file_count": len(urls),
            "completed_files": 0,
            "planned_output_path": str(planned_output),
            "planned_ligand_count": payload.get("planned_ligand_count"),
            "planned_total_bytes": payload.get("planned_total_bytes"),
            "planned_size": _human_bytes(payload.get("planned_total_bytes")),
            "source": source_key,
            "download_urls": urls,
        }
        state.update_job(job_id, status="running", result=progress.copy())
        final_paths: list[Path] = []
        for index, url in enumerate(urls, start=1):
            progress.update(
                {
                    "phase": "downloading",
                    "current_file_index": index,
                    "current_url": url,
                    "completed_files": len(final_paths),
                    "downloaded_files": [str(path) for path in final_paths],
                }
            )
            state.update_job(job_id, result=progress.copy())

            def report_file_progress(downloaded_bytes: int, total_bytes: int | None) -> None:
                progress.update(
                    {
                        "current_file_bytes": downloaded_bytes,
                        "current_file_total_bytes": total_bytes,
                        "current_file_percent": round((downloaded_bytes / total_bytes) * 100, 1) if total_bytes else None,
                    }
                )
                state.update_job(job_id, result=progress.copy())

            final_paths.append(_download_ligand_url(url, out_dir, max_mb, report_file_progress))
        progress.update({"phase": "merging", "completed_files": len(final_paths), "downloaded_files": [str(path) for path in final_paths]})
        state.update_job(job_id, result=progress.copy())
        final_path = _combine_downloaded_ligands(final_paths, out_dir, combine_name)
        local_count = _local_ligand_count(final_path)
        state.update_job(
            job_id,
            status="completed",
            result={
                **progress,
                "phase": "completed",
                "input_path": str(final_path),
                "output_dir": str(out_dir),
                "docking_ligand_input": str(final_path),
                "source": source_key,
                "download_url": urls[0],
                "download_urls": urls,
                "downloaded_files": [str(path) for path in final_paths],
                "completed_files": len(final_paths),
                "local_ligand_count": local_count,
                "local_size_bytes": final_path.stat().st_size,
                "local_size": _human_bytes(final_path.stat().st_size),
                "vina_ready": final_path.suffix.lower() == ".pdbqt",
                "notes": "Downloaded ligand subset. Inspect the file before screening.",
            },
        )
    except Exception as exc:  # pragma: no cover - exercised through integration use
        state.update_job(job_id, status="failed", error=str(exc))


def _download_ligand_url(
    url: str,
    out_dir: Path,
    max_mb: float,
    progress: Any | None = None,
) -> Path:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("download URL must be http or https")
    file_name = Path(parsed.path).name or "ligands.dat"
    compressed_path = out_dir / file_name
    with file_lock(compressed_path.with_suffix(compressed_path.suffix + ".lock")):
        existing = _maybe_decompress_gzip(compressed_path) if compressed_path.exists() and compressed_path.stat().st_size > 0 else None
        if existing and existing.exists() and existing.stat().st_size > 0:
            if progress:
                progress(existing.stat().st_size, existing.stat().st_size)
            return existing
        request = urllib.request.Request(url, headers={"User-Agent": "OpenStructureLab/0.1"})
        try:
            response_context = urllib.request.urlopen(request, timeout=60)
        except urllib.error.HTTPError as exc:
            preview = exc.read(8192)
            feedback = _provider_feedback_from_response("", url, exc.geturl(), exc.code, dict(exc.headers), preview)
            raise ValueError(_format_provider_download_error(feedback)) from exc
        tmp_path = compressed_path.with_name(f".{compressed_path.name}.tmp.{os.getpid()}")
        with response_context as response:
            length = response.headers.get("Content-Length")
            total_bytes = int(length) if length and length.isdigit() else None
            if total_bytes and total_bytes > max_mb * 1024 * 1024:
                raise ValueError(f"download is larger than {max_mb:g} MB; narrow the subset or raise the limit")
            content_type = response.headers.get("Content-Type", "")
            final_url = response.geturl()
            if _provider_response_needs_message(url, final_url, content_type):
                preview = response.read(8192)
                feedback = _provider_feedback_from_response("", url, final_url, response.status, dict(response.headers), preview)
                raise ValueError(_format_provider_download_error(feedback))
            with tmp_path.open("wb") as handle:
                downloaded = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > max_mb * 1024 * 1024:
                        raise ValueError(f"download exceeded {max_mb:g} MB; narrow the subset or raise the limit")
                    handle.write(chunk)
                    if progress:
                        progress(downloaded, total_bytes)
        os.replace(tmp_path, compressed_path)
    return _maybe_decompress_gzip(compressed_path)


def _provider_response_needs_message(requested_url: str, final_url: str, content_type: str) -> bool:
    lowered = f"{final_url} {content_type}".lower()
    return (
        "login" in lowered
        or "signin" in lowered
        or "text/html" in content_type.lower()
        and _looks_like_ligand_download(requested_url)
    )


def _format_provider_download_error(feedback: dict[str, Any]) -> str:
    message = feedback.get("provider_message") or feedback.get("notes") or "Provider did not return a ligand data file."
    final_url = feedback.get("final_url") or feedback.get("url") or ""
    return f"{feedback.get('notes', 'Provider feedback')}: {message}. Final URL: {final_url}"


def _combine_downloaded_ligands(paths: list[Path], out_dir: Path, combine_name: object | None) -> Path:
    if not combine_name:
        return paths[0]
    output_path = out_dir / Path(str(combine_name)).name
    lock_path = output_path.with_suffix(output_path.suffix + ".lock")
    with file_lock(lock_path):
        return _combine_downloaded_ligands_unlocked(paths, output_path)


def _combine_downloaded_ligands_unlocked(paths: list[Path], output_path: Path) -> Path:
    if len(paths) == 1:
        if paths[0].resolve() == output_path.resolve():
            return paths[0]
        shutil.copyfile(paths[0], output_path)
        return output_path
    suffixes = {path.suffix.lower() for path in paths}
    if suffixes <= {".smi", ".smiles"}:
        with output_path.open("w") as handle:
            for path in paths:
                text = path.read_text()
                handle.write(text)
                if not text.endswith("\n"):
                    handle.write("\n")
        return output_path
    if suffixes == {".sdf"}:
        with output_path.open("w") as handle:
            for path in paths:
                text = path.read_text()
                handle.write(text)
                if not text.endswith("\n"):
                    handle.write("\n")
        return output_path
    return paths[0]


def _maybe_decompress_gzip(path: Path) -> Path:
    if path.suffix.lower() != ".gz":
        return path
    output_path = path.with_suffix("")
    with gzip.open(path, "rb") as source, output_path.open("wb") as target:
        shutil.copyfileobj(source, target)
    return output_path


def _dashboard_ligand_libraries(root: Path, scan_dir: str | None = None) -> list[dict[str, Any]]:
    refreshed = datetime.now(timezone.utc).isoformat()
    libraries: list[dict[str, Any]] = [
        _library_row(
            source_key="zinc3d-pdbqt",
            library_key="zinc-3d-tranches",
            name="ZINC tranche browser (SMILES/PDBQT)",
            location="https://files.docking.org/3D/",
            access="external",
            molecule_count="subset-dependent; choose tranches before download",
            vina_ready=True,
            prep="none",
            filters="heavy atoms, logP/polarity, charge, purchasability, pH/reactivity tranche filters",
            formats=["pdbqt", "smi", "sdf", "mol2", "db2"],
            notes="One-click starter goals download SMILES and need local prep. Advanced ZINC can download PDBQT files when present in the selected tranche, which can skip local ligand prep.",
            refreshed=refreshed,
        ),
        _library_row(
            source_key="virtualflow-enamine-real",
            library_key="virtualflow-real-pdbqt",
            name="VirtualFlow REAL ready-to-dock library",
            location="https://virtual-flow.org/real-library",
            access="external",
            molecule_count="over 1.4B reported ready-to-dock molecules; use focused subsets",
            vina_ready=True,
            prep="none",
            filters="VirtualFlow/REAL subset selection; verify supplier and chemistry filters",
            formats=["pdbqt"],
            notes="Appropriate after the pipeline is validated and a cluster backend is configured. The provider site may require interactive browser access for subset scripts.",
            refreshed=refreshed,
        ),
        _library_row(
            source_key="enamine-sdf",
            library_key="enamine-catalog-downloads",
            name="Enamine catalog downloads",
            location="https://enamine.net/compound-collections",
            access="external",
            molecule_count="catalog-dependent",
            vina_ready=False,
            prep="required",
            filters="supplier catalog, fragment/lead-like/REAL/focused collection filters",
            formats=["sdf", "smi", "csv"],
            notes="Download a catalog subset, then load the local file for RDKit/Meeko prep. Some Enamine file downloads redirect to login and cannot be fetched anonymously.",
            refreshed=refreshed,
        ),
        _library_row(
            source_key="chembl",
            library_key="chembl-downloads",
            name="ChEMBL downloads",
            location="https://www.ebi.ac.uk/chembl/downloads",
            access="external",
            molecule_count="release-dependent; millions of bioactive molecules",
            vina_ready=False,
            prep="required",
            filters="activity/assay confidence, target, size, alerts, drug-like properties",
            formats=["sdf", "smi", "csv"],
            notes="Useful for known actives, controls, and repurposing sets.",
            refreshed=refreshed,
        ),
        _library_row(
            source_key="pubchem",
            library_key="pubchem-downloads",
            name="PubChem downloads / PUG-REST",
            location="https://pubchem.ncbi.nlm.nih.gov/",
            access="external",
            molecule_count="query-dependent; very large public database",
            vina_ready=False,
            prep="required",
            filters="query-dependent; local drug-like and alert filtering strongly recommended",
            formats=["sdf", "smi", "csv", "json"],
            notes="Best for specific known compound sets rather than broad unfiltered screening.",
            refreshed=refreshed,
        ),
    ]
    libraries.extend(_scan_ligand_files(root / "data-cache" / "ligands", source_hint="custom-sdf", refreshed=refreshed))
    libraries.extend(_scan_ligand_files(root / "data-cache" / "validation", source_hint="custom-sdf", refreshed=refreshed))
    libraries.extend(_scan_ligand_library_folders(root / "ligand_libraries", refreshed=refreshed))
    shared_root = _shared_data_root(root)
    if shared_root:
        libraries.extend(
            _scan_ligand_files(
                shared_root / "ligand_libraries",
                source_hint="custom-sdf",
                refreshed=refreshed,
                access="shared-file",
                scope_note="Shared read-only ligand file",
            )
        )
        libraries.extend(
            _scan_ligand_library_folders(
                shared_root / "ligand_libraries",
                refreshed=refreshed,
                access="shared-file",
                scope_note="Shared read-only ligand library",
            )
        )
        for benchmark_ligand_root in [
            shared_root / "benchmarks" / "cdk2-transferred" / "prepared",
            shared_root / "benchmarks" / "cdk2-transferred" / "workflow-run" / "inputs",
        ]:
            libraries.extend(
                _scan_ligand_files(
                    benchmark_ligand_root,
                    refreshed=refreshed,
                    access="shared-file",
                    scope_note="Shared read-only benchmark ligand file",
                )
            )
            libraries.extend(
                _scan_ligand_library_folders(
                    benchmark_ligand_root,
                    refreshed=refreshed,
                    access="shared-file",
                    scope_note="Shared read-only benchmark ligand library",
                )
            )
    if scan_dir:
        scan_path = _resolve_readable_input_path(root, scan_dir, field_name="scan folder")
        access = _path_access(root, scan_path)
        libraries.extend(_scan_ligand_files(scan_path, refreshed=refreshed, access=access, scope_note=_path_scope_label(root, scan_path)))
        libraries.extend(_scan_ligand_library_folders(scan_path, refreshed=refreshed, access=access, scope_note=_path_scope_label(root, scan_path)))
    return _dedupe_libraries(libraries)


def _dashboard_ligand_starter_libraries() -> list[dict[str, Any]]:
    starters = [
        {
            "key": "zinc-smoke-100",
            "source_key": "zinc3d-pdbqt",
            "name": "Tiny smoke test",
            "goal": "make sure the workflow runs",
            "molecule_size": "very small",
            "compound_type": "purchasable, low-complexity starter",
            "scale": "local quick test",
            "purpose": "Fast pipeline check before spending time on a real screen.",
            "expected_molecules": "about 700 molecules; count is calculated before download",
            "vina_ready": False,
            "prep": "required",
            "formats": ["smi"],
            "recommended_use": "Use this first to confirm target prep, pocket selection, ligand prep, docking, and reports work.",
            "download_count": 3,
            "output_name": "zinc_tiny_smoke.smi",
            "urls": [
                "https://cache.docking.org/3D/AA/AAHL/AAAAHL.smi",
                "https://cache.docking.org/3D/AA/AAHM/AAAAHM.smi",
                "https://cache.docking.org/3D/AA/AAHN/AAAAHN.smi",
            ],
        },
        _zinc_goal(
            key="zinc-fragment-like",
            name="Fragment-like purchasable starter",
            goal="screen small fragments for early hit discovery",
            molecule_size="fragment-like / very small",
            compound_type="purchasable, low-complexity fragments",
            scale="local starter",
            purpose="Start a fragment-style screen with small molecules that are quick to prep and dock.",
            expected_molecules="count is calculated before download",
            recommended_use="Use when you want small fragments or want to explore shallow pockets with simpler chemistry.",
            output_name="zinc_fragment_like_starter.smi",
            tranche_codes=["AAHL", "AAHM", "AAHN", "AALL", "AALM", "AALN"],
        ),
        _zinc_goal(
            key="zinc-lead-like",
            name="Lead-like purchasable starter",
            goal="screen lead-like compounds",
            molecule_size="lead-like / small-to-medium",
            compound_type="purchasable lead-like molecules",
            scale="local-to-workstation starter",
            purpose="A practical first discovery screen after smoke testing.",
            expected_molecules="count is calculated before download",
            recommended_use="Use this when you want compounds closer to medicinal chemistry starting points than fragments.",
            output_name="zinc_lead_like_starter.smi",
            tranche_codes=["ADHL", "ADHM", "ADHN", "ADLL", "ADLM", "ADLN", "AEHL", "AEHM", "AEHN", "AELM", "AELN"],
        ),
        _zinc_goal(
            key="zinc-drug-like",
            name="Drug-like purchasable starter",
            goal="screen drug-like compounds",
            molecule_size="drug-like / medium",
            compound_type="purchasable drug-like molecules",
            scale="workstation or small cluster",
            purpose="A broader screen biased toward drug-like chemistry.",
            expected_molecules="count is calculated before download",
            recommended_use="Use after validating the workflow; consider SLURM export if the count is high.",
            output_name="zinc_drug_like_starter.smi",
            tranche_codes=["AEHL", "AEHM", "AEHN", "AEHO", "AELM", "AELN", "AELO"],
        ),
        _zinc_goal(
            key="zinc-neutral-purchasable",
            name="Neutral purchasable starter",
            goal="screen neutral purchasable compounds",
            molecule_size="small-to-medium",
            compound_type="neutral or near-neutral purchasable compounds",
            scale="local-to-cluster starter",
            purpose="Reduce complications from charged compounds while keeping purchasable chemistry.",
            expected_molecules="count is calculated before download",
            recommended_use="Use when you want simpler charge behavior for an initial docking campaign.",
            output_name="zinc_neutral_purchasable_starter.smi",
            tranche_codes=["AAHN", "AALN", "ADHN", "ADLN", "AEHN", "AELN"],
        ),
        {
            "key": "zinc-small-starter",
            "source_key": "zinc3d-pdbqt",
            "name": "Small local starter screen",
            "goal": "first local docking run",
            "molecule_size": "small",
            "compound_type": "purchasable, low-complexity starter",
            "scale": "local small screen",
            "purpose": "Small, low-risk first real screen for local testing.",
            "expected_molecules": "about 1,000-2,000 molecules; count is calculated before download",
            "vina_ready": False,
            "prep": "required",
            "formats": ["smi"],
            "recommended_use": "Use after the smoke test when you want more compounds but still want a quick local run.",
            "download_count": 8,
            "output_name": "zinc_small_starter.smi",
            "urls": [
                "https://cache.docking.org/3D/AA/AAHL/AAAAHL.smi",
                "https://cache.docking.org/3D/AA/AAHM/AAAAHM.smi",
                "https://cache.docking.org/3D/AA/AAHN/AAAAHN.smi",
                "https://cache.docking.org/3D/AA/AAHO/AAAAHO.smi",
                "https://cache.docking.org/3D/AB/ABHL/ABABHL.smi",
                "https://cache.docking.org/3D/AB/ABHM/ABABHM.smi",
                "https://cache.docking.org/3D/AB/ABHN/ABABHN.smi",
                "https://cache.docking.org/3D/AB/ABHO/ABABHO.smi",
            ],
        },
        {
            "key": "chembl-approved-smoke",
            "source_key": "chembl",
            "name": "ChEMBL approved-drug smoke set",
            "goal": "test known bioactive or approved-drug style chemistry",
            "molecule_size": "mixed small molecules",
            "compound_type": "ChEMBL molecules with max phase 4",
            "scale": "tiny validation set",
            "purpose": "Confirm ChEMBL downloads, inspection, and ligand preparation work before using larger ChEMBL exports.",
            "expected_molecules": "25 molecules; count is calculated before download",
            "vina_ready": False,
            "prep": "required",
            "formats": ["sdf"],
            "recommended_use": "Use this as a quick ChEMBL source check, not as a discovery-scale library.",
            "download_count": 1,
            "output_name": "chembl_approved_drug_smoke.sdf",
            "urls": ["https://www.ebi.ac.uk/chembl/api/data/molecule?max_phase=4&limit=25&format=sdf"],
        },
        {
            "key": "pubchem-known-drug-smoke",
            "source_key": "pubchem",
            "name": "PubChem known-drug smoke set",
            "goal": "test a small named-compound PubChem pull",
            "molecule_size": "common small molecules",
            "compound_type": "known compounds by PubChem CID",
            "scale": "tiny validation set",
            "purpose": "Confirm PubChem downloads and local SMILES inspection work before building custom PubChem queries.",
            "expected_molecules": "5 molecules; count is calculated before download",
            "vina_ready": False,
            "prep": "required",
            "formats": ["smi"],
            "recommended_use": "Use this only as a source check; broad PubChem screens need query design and filtering.",
            "download_count": 1,
            "output_name": "pubchem_known_drug_smoke.smi",
            "urls": [
                "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/2244,3672,156391,2519,1983/property/CanonicalSMILES/TXT"
            ],
        },
    ]
    for starter in starters:
        if starter.get("source_key") == "zinc3d-pdbqt":
            starter["urls"] = [_normalize_zinc_url(str(url)) for url in starter.get("urls", [])]
    return starters


def _zinc_goal(
    key: str,
    name: str,
    goal: str,
    molecule_size: str,
    compound_type: str,
    scale: str,
    purpose: str,
    expected_molecules: str,
    recommended_use: str,
    output_name: str,
    tranche_codes: list[str],
) -> dict[str, Any]:
    urls = [_zinc_smiles_url(code) for code in tranche_codes]
    return {
        "key": key,
        "source_key": "zinc3d-pdbqt",
        "name": name,
        "goal": goal,
        "molecule_size": molecule_size,
        "compound_type": compound_type,
        "scale": scale,
        "purpose": purpose,
        "expected_molecules": expected_molecules,
        "vina_ready": False,
        "prep": "required",
        "formats": ["smi"],
        "recommended_use": recommended_use,
        "download_count": len(urls),
        "output_name": output_name,
        "urls": urls,
    }


def _zinc_smiles_url(tranche_code: str) -> str:
    prefix = tranche_code[:2]
    return f"https://files.docking.org/3D/{prefix}/{tranche_code}/{prefix}{tranche_code}.smi"


def _normalize_zinc_url(url: str) -> str:
    return url.replace("https://cache.docking.org/3D/", "https://files.docking.org/3D/")


def _ligand_goal_count(payload: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    key = str(payload.get("key") or "")
    starter = next((row for row in _dashboard_ligand_starter_libraries() if row["key"] == key), None)
    if not starter:
        raise ValueError(f"unknown ligand goal '{key}'")
    files: list[dict[str, Any]] = []
    unavailable: list[str] = []
    for url in starter["urls"]:
        try:
            count = _remote_ligand_count(url)
            size = _remote_ligand_size(url)
            files.append({"url": url, "ligand_count": count, "bytes": size, "size": _human_bytes(size), "status": "ok"})
        except Exception as exc:
            unavailable.append(f"{url} ({exc})")
            files.append({"url": url, "ligand_count": 0, "bytes": 0, "size": "0 B", "status": "unavailable", "error": str(exc)})
    if unavailable and not any(file.get("status") == "ok" for file in files):
        raise ValueError("none of the planned ligand files are available: " + "; ".join(unavailable))
    counts = [int(file["ligand_count"]) for file in files]
    sizes = [int(file["bytes"] or 0) for file in files]
    planned_output_path = ""
    if root is not None:
        planned_output_path = str((root / "data-cache" / "ligands" / "downloads" / str(starter["output_name"])).resolve())
    return {
        "key": key,
        "name": starter["name"],
        "file_count": len(starter["urls"]),
        "available_file_count": sum(1 for file in files if file.get("status") == "ok"),
        "unavailable_file_count": len(unavailable),
        "unavailable_files": unavailable,
        "ligand_count": sum(counts),
        "total_bytes": sum(sizes),
        "total_size": _human_bytes(sum(sizes)),
        "counts": counts,
        "files": files,
        "urls": starter["urls"],
        "planned_output_path": planned_output_path,
        "vina_ready": starter["vina_ready"],
        "prep": starter["prep"],
        "download_estimate": _download_time_note(sum(sizes)),
        "notes": (
            "Counted from the planned download files. Inspect again after download to verify the merged local file."
            if not unavailable
            else f"Counted available planned files; {len(unavailable)} file(s) were unavailable and should be reviewed before launch."
        ),
    }


def _remote_ligand_count(url: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "OpenStructureLab/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    if url.endswith(".gz"):
        raw = gzip.decompress(raw)
    text = raw.decode("utf-8", errors="ignore")
    file_format = _infer_ligand_format(url)
    if file_format == "sdf":
        return sum(1 for line in text.splitlines() if line.startswith("$$$$"))
    return sum(
        1
        for line in text.splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
        and not line.strip().lower().startswith(("smiles ", "smiles\t", "smiles,"))
    )


def _remote_ligand_size(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "OpenStructureLab/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            length = response.headers.get("Content-Length")
            if length and length.isdigit():
                return int(length)
    except Exception:
        return 0
    return 0


def _infer_ligand_format(url_or_path: str) -> str:
    parsed = urlparse(url_or_path)
    query_format = parse_qs(parsed.query).get("format", [""])[0].lower()
    if query_format in {"sdf", "smi", "smiles", "txt", "csv", "tsv", "pdbqt"}:
        return "smi" if query_format in {"smi", "smiles", "txt"} else query_format
    name = Path(parsed.path or url_or_path).name.lower()
    if name.endswith(".gz"):
        name = name[:-3]
    suffix = Path(name).suffix.lower().lstrip(".")
    if suffix in {"sdf", "sd"}:
        return "sdf"
    if suffix in {"smi", "smiles", "txt"}:
        return "smi"
    if suffix in {"csv", "tsv", "pdbqt"}:
        return suffix
    if name in {"txt", "smi", "smiles"}:
        return "smi"
    return suffix or "unknown"


def _local_ligand_count(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(errors="ignore")
    file_format = _infer_ligand_format(str(path))
    if file_format == "sdf":
        return sum(1 for line in text.splitlines() if line.startswith("$$$$"))
    return sum(1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))


def _human_bytes(value: object | None) -> str:
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    if size <= 0:
        return "unknown size"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.1f} {units[unit]}" if unit else f"{int(size)} {units[unit]}"


def _download_time_note(total_bytes: int) -> str:
    if total_bytes <= 0:
        return "Download size is not reported by the provider; progress will update by completed file."
    if total_bytes < 5 * 1024 * 1024:
        return "Small download; usually seconds on a normal connection."
    if total_bytes < 100 * 1024 * 1024:
        return "Moderate download; usually minutes depending on the connection."
    return "Large download; use a focused subset and expect runtime to depend strongly on network speed."


def _library_row(
    source_key: str,
    library_key: str,
    name: str,
    location: str,
    access: str,
    molecule_count: str,
    vina_ready: bool,
    prep: str,
    filters: str,
    formats: list[str],
    notes: str,
    refreshed: str,
) -> dict[str, Any]:
    return {
        "source_key": source_key,
        "library_key": library_key,
        "name": name,
        "location": location,
        "access": access,
        "molecule_count": molecule_count,
        "vina_ready": vina_ready,
        "prep": prep,
        "filters": filters,
        "formats": formats,
        "notes": notes,
        "refreshed_at": refreshed,
        "loadable": access in {"local-file", "shared-file"},
    }


def _scan_ligand_files(
    scan_dir: Path,
    source_hint: str | None = None,
    refreshed: str | None = None,
    access: str = "local-file",
    scope_note: str = "",
    include_single_ligand_files: bool = False,
) -> list[dict[str, Any]]:
    refreshed = refreshed or datetime.now(timezone.utc).isoformat()
    scan_dir = scan_dir.expanduser().resolve()
    if not scan_dir.exists():
        return []
    suffixes = {".smi", ".smiles", ".sdf", ".csv", ".tsv", ".pdbqt"}
    skip_dirs = {
        "docking",
        "interactions",
        "report",
        "redocking",
        "dashboard-pose-views",
        "vina-prep",
        "ligand-vina-prep",
        "pdbqt",
        "sdf",
        "filtered",
    }
    rows: list[dict[str, Any]] = []
    visited_dirs = 0
    for dirpath, dirnames, filenames in os.walk(scan_dir):
        visited_dirs += 1
        if visited_dirs > 2000:
            break
        kept_dirnames: list[str] = []
        for name in dirnames:
            if name in skip_dirs or name.startswith("."):
                continue
            child = Path(dirpath) / name
            try:
                if _inspect_ligand_folder(child).get("valid_ligand_library"):
                    continue
            except Exception:
                pass
            kept_dirnames.append(name)
        dirnames[:] = kept_dirnames
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.suffix.lower() not in suffixes:
                continue
            suffix = path.suffix.lower().lstrip(".")
            molecule_count = _quick_ligand_count(path)
            if not include_single_ligand_files and molecule_count == "1":
                continue
            vina_ready = suffix == "pdbqt"
            source_key = source_hint or ("custom-pdbqt" if vina_ready else _guess_source_from_path(path))
            rows.append(
                _library_row(
                    source_key=source_key,
                    library_key=f"local:{path.resolve()}",
                    name=path.name,
                    location=str(path.resolve()),
                    access=access,
                    molecule_count=molecule_count,
                    vina_ready=vina_ready,
                    prep="none" if vina_ready else "required",
                    filters="unknown from file; inspect and apply selected RDKit preset before screening",
                    formats=[suffix],
                    notes=f"{scope_note or 'Ligand file'} discovered under {scan_dir}",
                    refreshed=refreshed,
                )
            )
            if len(rows) >= 250:
                return rows
    return rows


def _scan_ligand_library_folders(
    scan_dir: Path,
    refreshed: str | None = None,
    access: str = "local-file",
    scope_note: str = "",
    include_single_ligand_folders: bool = False,
) -> list[dict[str, Any]]:
    refreshed = refreshed or datetime.now(timezone.utc).isoformat()
    scan_dir = scan_dir.expanduser().resolve()
    if not scan_dir.exists():
        return []
    rows: list[dict[str, Any]] = []
    candidates = [scan_dir, *[path for path in sorted(scan_dir.iterdir()) if path.is_dir() and not path.name.startswith(".")]]
    for folder in candidates[:200]:
        try:
            inspection = _inspect_ligand_folder(folder)
        except Exception:
            continue
        if not inspection.get("valid_ligand_library"):
            continue
        counts = inspection.get("counts_by_format") or {}
        formats = sorted(str(fmt) for fmt, count in counts.items() if count)
        count = inspection.get("count") or inspection.get("file_count") or "unknown"
        if not include_single_ligand_folders and _molecule_count_is_single(count):
            continue
        rows.append(
            _library_row(
                source_key="custom-pdbqt" if inspection.get("vina_ready") else "custom-sdf",
                library_key=f"local-folder:{folder}",
                name=folder.name,
                location=str(folder),
                access=access,
                molecule_count=str(count),
                vina_ready=bool(inspection.get("vina_ready")),
                prep="none" if inspection.get("vina_ready") else "required",
                filters="unknown from folder; inspect before screening",
                formats=formats or ["folder"],
                notes=str(inspection.get("notes") or f"{scope_note or 'Ligand library folder'} under {scan_dir}"),
                refreshed=refreshed,
            )
        )
    return rows


def _molecule_count_is_single(value: object) -> bool:
    try:
        return int(str(value).strip()) == 1
    except Exception:
        return False


def _quick_ligand_count(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix in {".smi", ".smiles"}:
            count = sum(1 for line in path.open(errors="ignore") if line.strip() and not line.lstrip().startswith("#"))
            return str(count)
        if suffix in {".csv", ".tsv"}:
            count = max(0, sum(1 for _ in path.open(errors="ignore")) - 1)
            return str(count)
        if suffix == ".sdf":
            count = sum(1 for line in path.open(errors="ignore") if line.startswith("$$$$"))
            return str(count)
        if suffix == ".pdbqt":
            return "1"
    except OSError:
        return "unavailable"
    return "unknown"


def _guess_source_from_path(path: Path) -> str:
    lowered = str(path).lower()
    if "chembl" in lowered:
        return "chembl"
    if "zinc" in lowered:
        return "zinc3d-pdbqt"
    if "enamine" in lowered:
        return "enamine-sdf"
    if "pubchem" in lowered:
        return "pubchem"
    return "custom-sdf"


def _dedupe_libraries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = str(row["library_key"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _start_ligand_prep_job(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> DashboardJob:
    username = safe_user_name(username or payload.get("username") or get_request_user())
    workspace_root = _dashboard_user_root(state.root, username)
    job = state.add_job(DashboardJob(id=uuid.uuid4().hex[:12], kind="ligand-prep", username=username, request=payload))
    thread = threading.Thread(target=_run_ligand_prep_job, args=(state, job.id, payload, workspace_root), daemon=True)
    thread.start()
    return job


def _ligand_prep_output_dir(root: Path, payload: dict[str, Any]) -> Path:
    ligand_path = _resolve_readable_input_path(root, str(payload["ligands"]), field_name="ligand input")
    return _resolve_workspace_output_dir(
        root,
        payload.get("out"),
        root / "runs" / f"ligand-prep-{ligand_path.stem}",
        field_name="ligand prep output directory",
    )


def _infer_orchestration_step_from_live_outputs(data: dict[str, Any]) -> None:
    ligand_prep = data.get("ligand_prep_progress") if isinstance(data.get("ligand_prep_progress"), dict) else {}
    docking = data.get("docking_progress") if isinstance(data.get("docking_progress"), dict) else {}
    current = ""
    if ligand_prep and ligand_prep.get("phase") != "completed":
        current = "ligand-prep"
    elif docking and docking.get("phase") not in {"completed", "not-started"}:
        current = "docking"
    elif docking and int(docking.get("docked_ligands") or 0) > 0:
        current = "docking"
    if not current:
        return
    prior_steps = {
        "ligand-prep": {"target", "target-prep", "binding-site", "ligands"},
        "docking": {"target", "target-prep", "binding-site", "ligands", "ligand-prep"},
    }
    data["current_step"] = current
    for row in data.get("steps") or []:
        key = str(row.get("key") or "")
        if key == current:
            row["status"] = "running"
        elif key in prior_steps.get(current, set()):
            row["status"] = "completed"


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return None


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
  tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
  os.replace(tmp, path)


def _parse_iso_timestamp(value: Any) -> float:
  text = str(value or "").strip()
  if not text:
    return 0.0
  try:
    return datetime.fromisoformat(text).timestamp()
  except ValueError:
    return 0.0


def _progress_sort_tuple(row: dict[str, Any]) -> tuple[int, float, str]:
  status_rank = {"running": 3, "starting": 3, "queued": 2, "completed": 1, "failed": 0, "stopped": -1}
  timestamp = _parse_iso_timestamp(row.get("sort_time") or row.get("updated_at") or row.get("finished_at") or row.get("started_at"))
  return (status_rank.get(str(row.get("display_status") or row.get("status") or ""), 0), timestamp, str(row.get("progress_json") or ""))


def _active_vina_process_count(root: Path | None = None) -> int:
    try:
        if root is None:
            result = subprocess.run(["pgrep", "-fc", r"vina --receptor"], capture_output=True, text=True, check=False)
        else:
            result = subprocess.run(["pgrep", "-af", r"vina --receptor"], capture_output=True, text=True, check=False)
    except Exception:
        return 0
    if root is not None:
        root_text = str(root.resolve())
        return len([line for line in (result.stdout or "").splitlines() if root_text in line])
    try:
        return max(0, int((result.stdout or "0").strip() or "0"))
    except ValueError:
        return 0


def _system_load_average() -> dict[str, float]:
    try:
        one, five, fifteen = os.getloadavg()
    except Exception:
        return {}
    return {"one_min": round(one, 2), "five_min": round(five, 2), "fifteen_min": round(fifteen, 2)}


def _annotate_fep_network_similarity(progress: dict[str, Any]) -> None:
  """Fill Tanimoto/score for OpenFE network edges when older progress lacks them."""
  network_plan = progress.get("network_plan") if isinstance(progress.get("network_plan"), dict) else None
  if not network_plan:
    return
  edges = network_plan.get("edges") or []
  if not edges or all(edge.get("tanimoto") is not None for edge in edges if isinstance(edge, dict)):
    return
  selections = progress.get("selections") if isinstance(progress.get("selections"), dict) else {}
  ligand_sdf = Path(str(selections.get("openfe_input_ligands_sdf") or ""))
  if not ligand_sdf.exists():
    return
  try:
    _add_ligand_similarity_to_network(network_plan, ligand_sdf)
  except Exception:
    return


def _annotate_fep_live_openfe_status(progress: dict[str, Any], progress_path: Path) -> None:
  """Surface OpenFE quickrun iteration progress from the terminal log.

  OpenFE writes useful per-iteration status to stdout while a transformation is
  running, but the pipeline progress JSON only advances between transformations.
  Parsing the tail of the terminal log keeps the dashboard visibly alive during
  long CPU-bound quickruns without interfering with the scientific process.
  """
  terminal_log = progress_path.parent / "terminal.log"
  if not terminal_log.exists():
    return
  try:
    raw_log = terminal_log.read_text(encoding="utf-8", errors="replace")
    lines = re.split(r"[\r\n]+", raw_log)[-4000:]
  except OSError:
    return

  iteration: int | None = None
  total: int | None = None
  subtask_current: int | None = None
  subtask_total: int | None = None
  subtask_percent: int | None = None
  estimate = ""
  current_transformation = ""
  phase = ""
  completed_transformation: int | None = None
  failed_transformations = 0
  total_transformations: int | None = None
  last_message = ""
  for line in lines:
    line = line.strip()
    if line:
      last_message = line
    if "Loading transformation from:" in line:
      current_transformation = Path(line.split("Loading transformation from:", 1)[-1].strip()).stem
      phase = "loading transformation"
      subtask_current = None
      subtask_total = None
      subtask_percent = None
    match_done = re.search(r"OpenFE transformation\s+(\d+)\s*/\s*(\d+)\s+(completed|failed)", line)
    if match_done:
      completed_transformation = int(match_done.group(1))
      total_transformations = int(match_done.group(2))
      if match_done.group(3) == "failed":
        failed_transformations += 1
        phase = "failed transformation"
      else:
        phase = "completed transformation"
    if "Planning simulations for this edge" in line:
      phase = "planning simulations"
    elif "Starting system setup unit" in line:
      phase = "system setup"
    elif "Parameterizing systems" in line:
      phase = "parameterizing systems"
    elif "Creating hybrid system" in line:
      phase = "creating hybrid system"
    elif "Hybrid system created" in line:
      phase = "hybrid system created"
    elif "Starting simulation unit" in line:
      phase = "starting simulation"
    elif "minimizing systems" in line:
      phase = "minimizing systems"
    elif "equilibrating systems" in line:
      phase = "equilibrating systems"
    elif "running production phase" in line:
      phase = "production"
    match = re.search(r"Iteration\s+(\d+)\s*/\s*(\d+)", line)
    if match:
      iteration = int(match.group(1))
      total = int(match.group(2))
      phase = "production"
    if "Estimated completion in" in line:
      estimate = line.split("Estimated completion in", 1)[-1].strip()
    match_tqdm = re.search(r"(\d+)%\|.*?\|\s*(\d+)\s*/\s*(\d+)", line)
    if match_tqdm:
      subtask_percent = int(match_tqdm.group(1))
      subtask_current = int(match_tqdm.group(2))
      subtask_total = int(match_tqdm.group(3))
      if not phase or phase in {"planning simulations", "starting simulation"}:
        phase = "simulation progress"

  selections = progress.get("selections") if isinstance(progress.get("selections"), dict) else {}
  output_dir = Path(str(selections.get("output_dir") or ""))
  result_count = 0
  result_files: list[dict[str, Any]] = []
  if output_dir.exists():
    for result_path in sorted((output_dir / "openfe" / "results").glob("*_results.json")):
      result_count += 1
      result_files.append({"name": result_path.name, "path": str(result_path), "size": result_path.stat().st_size})
  network_plan = progress.get("network_plan") if isinstance(progress.get("network_plan"), dict) else {}
  planned_total = int(network_plan.get("n_transformations") or selections.get("openfe_transformation_count") or total_transformations or 0)
  completed_count = max(result_count, completed_transformation or 0)
  transformation_percent = int(round((completed_count / planned_total) * 100)) if planned_total else 0
  iteration_percent = int(round((iteration / max(total, 1)) * 100)) if iteration is not None and total is not None else None
  progress["live_openfe"] = {
    "iteration": iteration,
    "total_iterations": total,
    "percent": iteration_percent,
    "subtask_current": subtask_current,
    "subtask_total": subtask_total,
    "subtask_percent": subtask_percent,
    "phase": phase or "running",
    "estimate": estimate,
    "last_message": last_message[-220:],
    "current_transformation": current_transformation,
    "completed_transformations": completed_count,
    "failed_transformations": failed_transformations,
    "total_transformations": planned_total or None,
    "transformation_percent": transformation_percent,
    "result_files": result_files[-12:],
    "terminal_log_mtime": datetime.fromtimestamp(terminal_log.stat().st_mtime, tz=timezone.utc).isoformat(),
  }


def _annotate_fep_active_process(progress: dict[str, Any], progress_path: Path) -> None:
  """Mark a stale FEP progress file as running when its command is active.

  A restarted external/screen FEP job can spend minutes in setup before the
  progress JSON is rewritten. This annotation is display-only: it does not edit
  the scientific output or progress file on disk.
  """
  selections = progress.get("selections") if isinstance(progress.get("selections"), dict) else {}
  output_dir = str(selections.get("output_dir") or "")
  needles = [str(progress_path)]
  if output_dir:
    needles.append(output_dir)
  try:
    result = subprocess.run(
      ["pgrep", "-af", "oslab.cli fep|oslab fep|fep run"],
      text=True,
      stdout=subprocess.PIPE,
      stderr=subprocess.DEVNULL,
      check=False,
      timeout=2,
    )
  except Exception:
    return
  active_lines = [line for line in result.stdout.splitlines() if line.strip() and any(needle and needle in line for needle in needles)]
  if not active_lines:
    return
  now = datetime.now(timezone.utc).isoformat()
  pids: list[str] = []
  for line in active_lines:
    first = line.strip().split(maxsplit=1)[0]
    if first.isdigit():
      pids.append(first)
  process_detail: dict[str, Any] = {}
  if pids:
    try:
      ps = subprocess.run(
        ["ps", "-p", ",".join(pids), "-o", "pid=,stat=,etime=,%cpu=,%mem=,rss=,command="],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=2,
      )
      rows = [row.strip() for row in ps.stdout.splitlines() if row.strip()]
      if rows:
        process_detail["ps_rows"] = rows[:4]
        best = rows[-1]
        parts = best.split(maxsplit=6)
        if len(parts) >= 6:
          process_detail.update({
            "pid": parts[0],
            "stat": parts[1],
            "elapsed": parts[2],
            "cpu_percent": parts[3],
            "mem_percent": parts[4],
            "rss_kb": parts[5],
          })
    except Exception:
      pass
  output_path = Path(output_dir) if output_dir else None
  recent_files: list[dict[str, Any]] = []
  phase = "running"
  if output_path and output_path.exists():
    try:
      for path in sorted(output_path.rglob("*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)[:12]:
        if path.is_file():
          recent_files.append({
            "path": str(path),
            "name": path.name,
            "size": path.stat().st_size,
            "modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
          })
      if any("/openfe/inputs/" in row["path"] for row in recent_files):
        phase = "preparing OpenFE input files"
      if any("/openfe/results/" in row["path"] for row in recent_files):
        phase = "OpenFE transformations running"
    except Exception:
      pass
  log_candidates: list[Path] = []
  for log_path in [progress_path.parent / "terminal.log"]:
    if log_path.exists():
      log_candidates.append(log_path)
  root = progress_path.parents[1] if len(progress_path.parents) > 1 else progress_path.parent
  try:
    output_name = output_path.name if output_path else progress_path.parent.name
    log_candidates.extend(sorted((root / "benchmarks").glob(f"**/*{output_name}*.log")))
    if output_name.startswith("lambda-CDK2-HIVRT-cdk2"):
      log_candidates.extend(sorted((root / "benchmarks").glob("**/cdk2_*fep*.log")))
  except Exception:
    pass
  log_candidates = sorted(set(log_candidates), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
  last_log_line = ""
  log_path_text = ""
  log_mtime = ""
  for log_path in log_candidates[:5]:
    try:
      lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
      nonempty = [line.strip() for line in lines if line.strip()]
      if nonempty:
        last_log_line = nonempty[-1][-300:]
        log_path_text = str(log_path)
        log_mtime = datetime.fromtimestamp(log_path.stat().st_mtime, tz=timezone.utc).isoformat()
        break
    except Exception:
      continue
  progress["live_process"] = {
    "running": True,
    "matched_command": active_lines[0][-500:],
    "process_count": len(active_lines),
    "checked_at": now,
    "process": process_detail,
    "phase": phase,
    "last_log_line": last_log_line,
    "log_path": log_path_text,
    "log_mtime": log_mtime,
    "recent_files": recent_files,
  }
  if str(progress.get("status") or "") in {"failed", "stopped", ""}:
    progress["display_status"] = "running"
    progress["display_current_step"] = progress.get("current_step") or "fep-run"
    progress["display_note"] = "A FEP process is currently running for this output/progress path; the saved progress file still contains an older status."
    progress["sort_time"] = now


def _mark_fep_progress_stopped(progress_path: Path, reason: str) -> None:
  progress = _read_json_file(progress_path)
  if not isinstance(progress, dict):
    return
  if str(progress.get("status") or "") in {"completed", "failed", "stopped"}:
    return
  now = datetime.now(timezone.utc).isoformat()
  progress["status"] = "stopped"
  progress["current_step"] = "stopped"
  progress["updated_at"] = now
  events = list(progress.get("events") or [])
  events.append({"time": now, "key": "stopped", "message": reason})
  progress["events"] = events[-50:]
  _write_json_atomic(progress_path, progress)


def _stop_existing_fep_sessions(state: DashboardState, keep_session_name: str) -> None:
  state._load_persisted_jobs()
  with state.lock:
    fep_jobs = [job for job in state.jobs.values() if job.kind == "fep"]
  for job in fep_jobs:
    result = dict(job.result or {})
    session_name = str(result.get("session_name") or "")
    progress_json = str(result.get("progress_json") or "")
    if session_name and session_name != keep_session_name and _screen_session_running(session_name):
      _quit_screen_session(session_name)
    if progress_json:
      progress_path = Path(progress_json)
      if progress_path.exists():
        _mark_fep_progress_stopped(progress_path, f"Superseded by newer FEP session {keep_session_name}.")
    if job.status in {"queued", "running"} and session_name != keep_session_name:
      state.update_job(
        job.id,
        status="stopped",
        result={**result, "notes": f"Superseded by newer FEP session {keep_session_name}."},
        error="",
      )
  for progress_path in sorted((state.root / "runs").glob("fep-*/progress.json")):
    progress = _read_json_file(progress_path)
    if not isinstance(progress, dict):
      continue
    session_id = str(progress.get("session_id") or "").strip()
    session_name = f"oslab-fep-{session_id}" if session_id else ""
    if session_name == keep_session_name:
      continue
    if session_name and _screen_session_running(session_name):
      _quit_screen_session(session_name)
    _mark_fep_progress_stopped(progress_path, f"Superseded by newer FEP session {keep_session_name}.")


def _ligand_prep_progress_from_files(root: Path, payload: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    progress = dict(base or {})
    ligand_path = Path(str(payload["ligands"])).resolve()
    output_dir = _ligand_prep_output_dir(root, payload)
    filter_json = output_dir / "filtered" / "ligand_filter_summary.json"
    prep_root = output_dir / "vina-prep"
    if not prep_root.exists():
        alt_prep_root = output_dir / "ligand-vina-prep"
        if alt_prep_root.exists():
            prep_root = alt_prep_root
    prep_json = prep_root / "ligand_prep.json"
    filter_summary = _read_json_file(filter_json)
    prep_summary = _read_json_file(prep_json)
    pdbqt_dir = prep_root / "pdbqt"
    prepared_count = len(list(pdbqt_dir.glob("*.pdbqt"))) if pdbqt_dir.exists() else int(progress.get("prepared_count") or 0)
    prepared_mol_dir = prep_root / "prepared-mols"
    prepared_sdf_count = len(list(prepared_mol_dir.glob("*.sdf"))) if prepared_mol_dir.exists() else prepared_count
    total_molecules = int((filter_summary or {}).get("total_molecules") or progress.get("total_molecules") or 0)
    included_count = int((filter_summary or {}).get("included_count") or progress.get("included_count") or 0)
    if prep_summary:
        prepared_count = int(prep_summary.get("prepared_count") or prepared_count)
    included_sdf = str((filter_summary or {}).get("included_sdf") or "")
    metadata_path = str(prep_json) if prep_json.exists() else str(prep_summary.get("metadata_path") or "") if prep_summary else ""
    prepared_output = str((prep_summary or {}).get("pdbqt_dir") or pdbqt_dir)
    denominator = included_count or total_molecules or None
    if prep_summary:
        phase = "completed"
    elif prepared_count or prepared_sdf_count:
        phase = "preparing-pdbqt"
    elif filter_summary:
        phase = "filtered"
    else:
        phase = progress.get("phase") or "filtering"
    percent = round((prepared_count / denominator) * 100, 1) if denominator else None
    progress.update(
        {
            "phase": phase,
            "input_path": str(ligand_path),
            "output_dir": str(output_dir),
            "filter_summary_json": str(filter_json) if filter_json.exists() else progress.get("filter_summary_json"),
            "included_sdf": included_sdf or progress.get("included_sdf"),
            "pdbqt_dir": str(pdbqt_dir),
            "prepared_output": prepared_output,
            "metadata_path": metadata_path,
            "docking_ligand_input": included_sdf or progress.get("docking_ligand_input"),
            "total_molecules": total_molecules or progress.get("total_molecules"),
            "included_count": included_count or progress.get("included_count"),
            "excluded_count": (filter_summary or {}).get("excluded_count", progress.get("excluded_count")),
            "prepared_sdf_count": prepared_sdf_count,
            "prepared_count": prepared_count,
            "progress_percent": percent,
            "progress_label": _format_ligand_prep_progress_label(phase, prepared_count, denominator),
        }
    )
    return progress


def _format_ligand_prep_progress_label(phase: str, prepared_count: int, denominator: int | None) -> str:
    if phase == "filtering":
        return "Filtering ligands..."
    if denominator:
        return f"Preparing PDBQT ligands: {prepared_count}/{denominator}"
    return f"Preparing PDBQT ligands: {prepared_count}"


def _discover_ligand_prep_jobs(root: Path, known_outputs: set[str]) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    for output_dir in sorted((root / "runs").glob("ligand-prep-*")):
        if str(output_dir.resolve()) in known_outputs:
            continue
        filter_summary = _read_json_file(output_dir / "filtered" / "ligand_filter_summary.json")
        prep_summary = _read_json_file(output_dir / "vina-prep" / "ligand_prep.json")
        if not filter_summary and not prep_summary:
            continue
        input_path = str((filter_summary or {}).get("input_path") or (prep_summary or {}).get("input_sdf") or "")
        if not input_path:
            continue
        payload = {"ligands": input_path, "out": str(output_dir)}
        progress = _ligand_prep_progress_from_files(root, payload, {"output_dir": str(output_dir.resolve())})
        included = int(progress.get("included_count") or 0)
        prepared = int(progress.get("prepared_count") or 0)
        completed = bool(prep_summary) or bool(included and prepared >= included)
        discovered.append(
            {
                "id": f"file-{output_dir.name}",
                "kind": "ligand-prep",
                "status": "completed" if completed else "running",
                "created_at": str((filter_summary or prep_summary or {}).get("created_at") or ""),
                "updated_at": "",
                "request": payload,
                "result": progress,
                "error": "",
            }
        )
    return discovered


def _run_ligand_prep_job(state: DashboardState, job_id: str, payload: dict[str, Any], workspace_root: Path | None = None) -> None:
    root = workspace_root or state.root
    state.update_job(job_id, status="running", result=_ligand_prep_progress_from_files(root, payload, {"phase": "starting"}))
    try:
        ligand_path = _resolve_readable_input_path(root, str(payload["ligands"]), field_name="ligand input")
        output_dir = _ligand_prep_output_dir(root, payload)
        if _is_vina_ready_ligand_input(ligand_path):
            result = {
                "phase": "completed",
                "input_path": str(ligand_path),
                "output_dir": str(output_dir),
                "docking_ligand_input": str(ligand_path),
                "prepared_count": 1,
                "progress_percent": 100,
                "progress_label": "PDBQT input is already prepared.",
                "vina_ready": True,
                "notes": "Input was marked Vina-ready; RDKit/Meeko preparation was skipped.",
            }
        else:
            state.update_job(job_id, result=_ligand_prep_progress_from_files(root, payload, {"phase": "filtering"}))
            filter_summary = filter_ligands(ligand_path, output_dir / "filtered", str(payload.get("preset") or "drug_like"))
            state.update_job(
                job_id,
                result=_ligand_prep_progress_from_files(
                    root,
                    payload,
                    {
                        "phase": "filtered",
                        "total_molecules": filter_summary.total_molecules,
                        "included_count": filter_summary.included_count,
                        "excluded_count": filter_summary.excluded_count,
                        "filter_summary_json": filter_summary.summary_json,
                    },
                ),
            )
            if filter_summary.included_count < 1:
                raise ValueError(
                    f"no ligands passed preset '{filter_summary.preset_key}'. "
                    f"Reviewed {filter_summary.total_molecules}; details: {filter_summary.excluded_csv}"
                )
            prep_metadata_path = output_dir / "vina-prep" / "ligand_prep.json"
            prep_existed_before = prep_metadata_path.exists()
            prep_record = prepare_ligands_for_vina(
                Path(filter_summary.included_sdf),
                output_dir / "vina-prep",
                LigandPrepOptions(
                    ph=float(payload.get("ph") or 7.4),
                    generate_3d=not bool(payload.get("no_gen3d", False)),
                    charge_model=str(payload.get("charge_model") or "gasteiger"),  # type: ignore[arg-type]
                    backend=str(payload.get("ligand_prep_backend") or "rdkit"),  # type: ignore[arg-type]
                    workers=int(payload.get("ligand_prep_workers") or 1),
                    timeout_seconds=int(payload.get("ligand_prep_timeout") or 120),
                ),
            )
            prep_reused = prep_existed_before
            result = {
                **_ligand_prep_progress_from_files(root, payload, {"phase": "completed"}),
                "input_path": str(ligand_path),
                "output_dir": str(output_dir),
                "filter_summary_json": filter_summary.summary_json,
                "included_sdf": filter_summary.included_sdf,
                "prepared_sdf": prep_record.prepared_sdf,
                "pdbqt_dir": prep_record.pdbqt_dir,
                "metadata_path": prep_record.metadata_path,
                "docking_ligand_input": filter_summary.included_sdf,
                "total_molecules": filter_summary.total_molecules,
                "included_count": filter_summary.included_count,
                "excluded_count": filter_summary.excluded_count,
                "prepared_count": prep_record.prepared_count,
                "progress_percent": 100,
                "progress_label": (
                    f"Reused existing ligand prep: {prep_record.prepared_count}/{filter_summary.included_count} PDBQT ligands."
                    if prep_reused
                    else f"Prepared {prep_record.prepared_count}/{filter_summary.included_count} PDBQT ligands."
                ),
                "vina_ready": False,
                "prep_reused": prep_reused,
                "notes": (
                    "Existing ligand prep metadata was found and validated, so RDKit/Meeko conversion was not repeated."
                    if prep_reused
                    else "Dashboard preflight prepared PDBQT files and selected the filtered SDF for the small-screen runner."
                ),
            }
        state.update_job(job_id, status="completed", result=result)
    except Exception as exc:  # pragma: no cover - exercised through integration use
        state.update_job(job_id, status="failed", error=str(exc))


def _start_small_screen_job(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    username = safe_user_name(username or payload.get("username") or get_request_user())
    root = _dashboard_user_root(state.root, username)
    job_id = uuid.uuid4().hex[:12]
    payload = {
        **payload,
        "ligands": str(_resolve_readable_input_path(root, str(payload["ligands"]), field_name="ligands")),
        "receptor": str(_resolve_readable_input_path(root, str(payload["receptor"]), field_name="receptor PDBQT")),
        "binding_site": str(_resolve_readable_input_path(root, str(payload["binding_site"]), field_name="binding-site JSON")),
    }
    output_dir = _resolve_workspace_output_dir(root, payload.get("out"), root / "reports" / f"screen-{job_id}", field_name="docking output directory")
    payload = {**payload, "out": str(output_dir)}
    run_dir = root / "runs" / "dashboard-small-screen-jobs" / job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "small-screen.log"
    session_name = f"oslab-screen-{job_id}"
    attach_command = _screen_attach_command(session_name, root)
    job = state.add_job(
        DashboardJob(
            id=job_id,
            kind="small-screen",
            username=username,
            status="running",
            request=payload,
            result={
                **_small_screen_progress_from_files(payload, {"phase": "starting", "output_dir": str(output_dir)}),
                "session_name": session_name,
                "attach_command": attach_command,
                "log_path": str(log_path),
                "notes": "Docking is running in a detached screen session so it can continue if the dashboard is restarted.",
            },
        )
    )
    screen = shutil.which("screen")
    if screen:
        command = _small_screen_cli_command(root, payload)
        subprocess.run(
            [screen, "-dmS", session_name, _screen_shell(), "-lc", f"{command} > {shlex_quote(str(log_path))} 2>&1"],
            cwd=root,
            check=True,
        )
    else:
        state.update_job(job.id, result={**(job.result or {}), "notes": "screen is unavailable; dashboard thread fallback is not restart-persistent."})
        thread = threading.Thread(target=_run_small_screen_job, args=(state, job.id, payload), daemon=True)
        thread.start()
    return job.to_dict()


def _start_slurm_screen_export_job(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    username = safe_user_name(username or payload.get("username") or get_request_user())
    job = state.add_job(DashboardJob(id=uuid.uuid4().hex[:12], kind="slurm-screen-export", username=username, request=payload))
    thread = threading.Thread(target=_run_slurm_screen_export_job, args=(state, job.id, payload), daemon=True)
    thread.start()
    return job.to_dict()


def _start_orchestrate_job(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    """Run a client-supplied multi-block bash script in a detached screen session.

    This is the server-side execution path for the public reviewer instance:
    the dashboard's script generator emits the bash for the 4-block pipeline,
    the user (or their AI agent via /api/orchestrate POST) submits it, and we
    run it under the user's anonymous-session workspace so multiple reviewers
    stay isolated.
    """
    username = safe_user_name(username or payload.get("username") or get_request_user())
    user_root = _dashboard_user_root(state.root, username)
    user_root.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex[:12]
    run_label = str(payload.get("run_label") or "").strip() or f"orchestrate-{job_id}"
    workdir = user_root / "runs" / f"{run_label}-{job_id}"
    workdir.mkdir(parents=True, exist_ok=True)
    script_body = str(payload.get("script") or "").strip()
    if not script_body:
        return {"error": "script is required"}
    if len(script_body) > 1_000_000:
        return {"error": "script exceeds 1 MB limit"}
    # Always wrap in a safe header.  set -u would trip on unbound vars in
    # user-pasted scripts, so we only enable -e and pipefail.
    header = (
        "#!/usr/bin/env bash\n"
        "set -eo pipefail\n"
        f"export OSLAB_ROOT={shlex_quote(str(state.root))}\n"
        f"export OSLAB_USER={shlex_quote(username)}\n"
        f"export USER_DIR={shlex_quote(str(user_root))}\n"
        f"export OSLAB_USER_SAFE={shlex_quote(username)}\n"
        f"cd {shlex_quote(str(user_root))}\n"
    )
    # OpenFE (Block 4 / FEP) lives in a separate conda env. The oslab CLI
    # finds the official OpenFE binary via OSLAB_OPENFE_BIN; without it,
    # `oslab fep run` aborts with "OpenFE backend not installed". Pick the
    # first openfe binary that exists on this host.
    openfe_candidates = [
        Path("/opt/oslab/current/.micromamba/envs/openfe-rbfe/bin/openfe"),
        Path.home() / ".oslab-openfe-env" / "bin" / "openfe",
    ]
    openfe_bin = next((p for p in openfe_candidates if p.is_file()), None)
    if openfe_bin is not None:
        header += f"export OSLAB_OPENFE_BIN={shlex_quote(str(openfe_bin))}\n"
    script_path = workdir / "run.sh"
    script_path.write_text(header + script_body, encoding="utf-8")
    script_path.chmod(0o755)
    log_path = workdir / "terminal.log"
    progress_path = workdir / "progress.json"
    progress_path.write_text(
        json.dumps({
            "run_label": run_label,
            "kind": "orchestrate",
            "status": "queued",
            "current_step": "queued",
            "percent": 0,
            "message": "orchestrate job queued",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "steps": [],
        }, indent=2),
        encoding="utf-8",
    )
    job = state.add_job(DashboardJob(
        id=job_id,
        kind="orchestrate",
        username=username,
        status="queued",
        request={k: v for k, v in payload.items() if k != "script"},  # don't echo big script
        result={
            "run_label": run_label,
            "workdir": str(workdir),
            "script_path": str(script_path),
            "log_path": str(log_path),
            "progress_path": str(progress_path),
        },
    ))
    env_bin = "/opt/oslab/current/.micromamba/envs/open-structure-lab/bin"
    # PLIP is missing from the production env (admin-owned, can't be modified
    # by the dashboard user). Fall back to a user-space PLIP env if one exists
    # at $HOME/.oslab-plip-env/bin/plip, prepended to PATH so subprocess calls
    # to `plip` from `oslab refine hits` find the binary.
    extra_bins: list[str] = []
    user_plip_bin = Path.home() / ".oslab-plip-env" / "bin"
    if (user_plip_bin / "plip").is_file():
        extra_bins.append(str(user_plip_bin))
    path_prefix = ":".join(extra_bins + [env_bin])
    screen = shutil.which("screen")
    if screen:
        session_name = f"oslab-orch-{job_id}"
        # The script header already cd's into user_root; we also ensure the
        # oslab environment binaries are on PATH so the script can call them
        # without absolute paths.
        wrapped = (
            f"export PATH={shlex_quote(path_prefix)}:$PATH && "
            f"bash {shlex_quote(str(script_path))} > {shlex_quote(str(log_path))} 2>&1; "
            # When the script finishes, mark progress completed/failed so the
            # monitor stops showing "queued".
            f"rc=$?; python3 -c 'import json,sys; "
            f"p=open(sys.argv[1]); d=json.load(p); p.close(); "
            f"d[\"status\"]=\"completed\" if int(sys.argv[2])==0 else \"failed\"; "
            f"d[\"current_step\"]=d[\"status\"]; d[\"percent\"]=100 if int(sys.argv[2])==0 else d.get(\"percent\",0); "
            f"open(sys.argv[1],\"w\").write(json.dumps(d, indent=2))' {shlex_quote(str(progress_path))} $rc"
        )
        try:
            subprocess.run(
                [screen, "-dmS", session_name, _screen_shell(), "-lc", wrapped],
                cwd=str(user_root),
                check=True,
            )
            state.update_job(job_id, status="running", result={**(job.result or {}), "session_name": session_name})
        except subprocess.CalledProcessError as exc:
            state.update_job(job_id, status="failed", error=f"failed to start screen session: {exc}")
    else:
        # Thread fallback (not restart-persistent).
        def _runner() -> None:
            state.update_job(job_id, status="running")
            try:
                with log_path.open("wb") as logf:
                    rc = subprocess.run(
                        ["bash", str(script_path)],
                        cwd=str(user_root),
                        stdout=logf,
                        stderr=subprocess.STDOUT,
                        env={**os.environ, "PATH": f"{env_bin}:" + os.environ.get("PATH", "")},
                    ).returncode
                status = "completed" if rc == 0 else "failed"
                state.update_job(job_id, status=status)
                try:
                    d = json.loads(progress_path.read_text(encoding="utf-8"))
                    d["status"] = status
                    d["current_step"] = status
                    if status == "completed":
                        d["percent"] = 100
                    progress_path.write_text(json.dumps(d, indent=2), encoding="utf-8")
                except Exception:
                    pass
            except Exception as exc:
                state.update_job(job_id, status="failed", error=str(exc))
        threading.Thread(target=_runner, daemon=True).start()
        state.update_job(job_id, status="running", result={**(job.result or {}), "notes": "thread fallback (no screen)"})
    return job.to_dict()


def _run_slurm_screen_export_job(state: DashboardState, job_id: str, payload: dict[str, Any]) -> None:
    state.update_job(job_id, status="running")
    try:
        ligand_options = LigandPrepOptions(
            ph=float(payload.get("ph") or 7.4),
            generate_3d=not bool(payload.get("no_gen3d", False)),
            charge_model=str(payload.get("charge_model") or "gasteiger"),  # type: ignore[arg-type]
            backend=str(payload.get("ligand_prep_backend") or "rdkit"),  # type: ignore[arg-type]
            workers=int(payload.get("ligand_prep_workers") or 1),
            timeout_seconds=int(payload.get("ligand_prep_timeout") or 120),
        )
        vina_options = VinaRunOptions(
            exhaustiveness=int(payload.get("exhaustiveness") or 1),
            num_modes=int(payload.get("num_modes") or 1),
            cpu=int(payload.get("cpu") or 1),
            seed=int(payload.get("seed") or 1),
            workers=int(payload.get("docking_workers") or 1),
        )
        export = export_slurm_small_screen(
            ligands=_resolve_readable_input_path(state.root, str(payload["ligands"]), field_name="ligands"),
            receptor_pdbqt=_resolve_readable_input_path(state.root, str(payload["receptor"]), field_name="receptor PDBQT"),
            binding_site_json=_resolve_readable_input_path(state.root, str(payload["binding_site"]), field_name="binding-site JSON"),
            output_dir=_resolve_workspace_output_dir(state.root, payload.get("out"), state.root / "reports" / f"slurm-screen-{job_id}", field_name="SLURM export output directory"),
            max_ligands=int(payload.get("max_ligands") or 20),
            preset=str(payload.get("preset") or "drug_like"),
            ligand_prep_options=ligand_options,
            vina_options=vina_options,
            job_name=str(payload.get("slurm_job_name") or "oslab-vina"),
            cpus_per_task=int(payload.get("slurm_cpus_per_task") or 1),
            array_concurrency=int(payload["slurm_array_concurrency"]) if payload.get("slurm_array_concurrency") else None,
            time_limit=str(payload.get("slurm_time") or "04:00:00"),
            partition=str(payload["slurm_partition"]) if payload.get("slurm_partition") else None,
            account=str(payload["slurm_account"]) if payload.get("slurm_account") else None,
            gres=str(payload["slurm_gres"]) if payload.get("slurm_gres") else None,
            setup_command=str(payload["slurm_setup_command"]) if payload.get("slurm_setup_command") else None,
            oslab_command=str(payload.get("oslab_command") or "oslab"),
        )
        state.update_job(
            job_id,
            status="completed",
            result={
                "backend": "slurm-export",
                "output_dir": str(export.output_dir),
                "filter_summary_json": export.filter_summary_json,
                "ligand_prep_json": export.ligand_prep_json,
                "submit_script": str(export.docking_export.submit_script),
                "collect_script": str(export.docking_export.collect_script),
                "ligand_count": export.docking_export.ligand_count,
                "notes": "Transfer or run this directory on a SLURM cluster, submit with sbatch, then run collect_results.sh after jobs finish.",
            },
        )
    except Exception as exc:  # pragma: no cover - exercised through integration use
        state.update_job(job_id, status="failed", error=str(exc))


def _small_screen_progress_from_files(payload: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    progress = dict(base or {})
    output_dir = Path(str(payload.get("out") or "reports/small-screen")).resolve()
    requested = int(payload.get("max_ligands") or 20)
    filter_summary = _read_json_file(output_dir / "filtered" / "ligand_filter_summary.json")
    prep_summary = _read_json_file(output_dir / "ligand-vina-prep" / "ligand_prep.json")
    prepared_dir = output_dir / "ligand-vina-prep" / "pdbqt"
    prepared_count = len(list(prepared_dir.glob("*.pdbqt"))) if prepared_dir.exists() else int(progress.get("prepared_count") or 0)
    docked_count = len(list((output_dir / "docking").glob("*/vina_run.json"))) if (output_dir / "docking").exists() else int(progress.get("docked_ligands") or 0)
    target = min(requested, int((filter_summary or {}).get("included_count") or requested))
    if (output_dir / "small_screen_summary.json").exists():
        phase = "completed"
        percent = 100
    elif docked_count:
        phase = "docking"
        percent = round(60 + 40 * (docked_count / max(target, 1)), 1)
    elif prep_summary or prepared_count:
        phase = "preparing-ligands"
        percent = round(30 + 30 * (prepared_count / max(target, 1)), 1)
    elif filter_summary:
        phase = "filtering-complete"
        percent = 30
    else:
        phase = progress.get("phase") or "starting"
        percent = progress.get("progress_percent") or 5
    progress.update(
        {
            "phase": phase,
            "output_dir": str(output_dir),
            "requested_max_ligands": requested,
            "total_molecules": (filter_summary or {}).get("total_molecules", progress.get("total_molecules")),
            "included_count": (filter_summary or {}).get("included_count", progress.get("included_count")),
            "prepared_count": prepared_count,
            "docked_ligands": docked_count,
            "progress_percent": min(100, percent),
            "progress_label": _format_small_screen_progress_label(phase, prepared_count, docked_count, target),
        }
    )
    return progress


def _infer_ligand_pdbqt_dir_from_output(output_dir: Path | None) -> str:
    if not output_dir:
        return ""
    candidates = [
        output_dir / "ligand-vina-prep" / "pdbqt",
        output_dir / "pdbqt",
    ]
    for candidate in candidates:
        try:
            if candidate.is_dir() and any(candidate.glob("*.pdbqt")):
                return str(candidate.resolve())
        except OSError:
            continue
    return ""


def _orchestration_docking_progress(output_dir: Path, selections: dict[str, Any]) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    requested = int(selections.get("max_ligands") or selections.get("ligand_prepared_count") or 0)
    prepared = int(selections.get("ligand_prepared_count") or 0)
    target = min(requested, prepared) if requested and prepared else (requested or prepared or 0)
    docked = len(list((output_dir / "docking").glob("*/vina_run.json"))) if (output_dir / "docking").exists() else 0
    summary = _read_json_file(output_dir / "small_screen_summary.json")
    if summary:
        docked = int(summary.get("docked_ligands") or docked)
        target = int(summary.get("requested_max_ligands") or target or docked)
        phase = "completed"
        percent = 100
    elif docked:
        phase = "docking"
        percent = round(100 * docked / max(target, docked, 1), 1)
    elif output_dir.exists():
        phase = "starting-docking"
        percent = 0
    else:
        phase = "not-started"
        percent = 0
    label = (
        f"Docking complete: {docked}/{target or requested or '?'} ligands docked"
        if phase == "completed"
        else f"Docking ligands: {docked}/{target or requested or '?'}"
    )
    return {
        "phase": phase,
        "output_dir": str(output_dir),
        # Standard field names expected by the JS dockingProgressDetail:
        "docked_count": docked,
        "target_count": target or requested,
        "prepared_count": prepared,
        "attempted_count": docked,
        # Legacy aliases:
        "requested_max_ligands": target or requested,
        "prepared_ligands": prepared,
        "docked_ligands": docked,
        "progress_percent": min(100, percent),
        "progress_label": label,
    }


def _format_small_screen_progress_label(phase: str, prepared_count: int, docked_count: int, target: int) -> str:
    if phase in {"starting", "filtering-complete"}:
        return "Filtering ligands and preparing screen input..."
    if phase == "preparing-ligands":
        return f"Preparing ligands: {prepared_count}/{target}"
    if phase == "docking":
        return f"Docking ligands: {docked_count}/{target}"
    if phase == "completed":
        return f"Completed docking: {docked_count}/{target}"
    return phase


def _run_small_screen_job(state: DashboardState, job_id: str, payload: dict[str, Any]) -> None:
    state.update_job(job_id, status="running", result=_small_screen_progress_from_files(payload, {"phase": "starting"}))
    try:
        summary = run_small_screen(
            ligands=Path(str(payload["ligands"])),
            receptor_pdbqt=Path(str(payload["receptor"])),
            binding_site_json=Path(str(payload["binding_site"])),
            output_dir=Path(str(payload["out"])),
            max_ligands=int(payload.get("max_ligands") or 20),
            preset=str(payload.get("preset") or "drug_like"),
            run_plip=not bool(payload.get("no_plip", False)),
            ligand_prep_options=LigandPrepOptions(
                ph=float(payload.get("ph") or 7.4),
                generate_3d=not bool(payload.get("no_gen3d", False)),
                charge_model=str(payload.get("charge_model") or "gasteiger"),  # type: ignore[arg-type]
                backend=str(payload.get("ligand_prep_backend") or "rdkit"),  # type: ignore[arg-type]
                workers=int(payload.get("ligand_prep_workers") or 1),
                timeout_seconds=int(payload.get("ligand_prep_timeout") or 120),
            ),
            vina_options=VinaRunOptions(
                exhaustiveness=int(payload.get("exhaustiveness") or 1),
                num_modes=int(payload.get("num_modes") or 1),
                cpu=int(payload.get("cpu") or 1),
                seed=int(payload.get("seed") or 1),
                workers=int(payload.get("docking_workers") or 1),
            ),
            report_context=dict(payload.get("report_context") or {}),
        )
        state.update_job(
            job_id,
            status="completed",
            result={
                **summary.model_dump(mode="json"),
                "phase": "completed",
                "progress_percent": 100,
                "progress_label": f"Completed docking: {summary.docked_ligands}/{summary.requested_max_ligands}",
            },
        )
    except Exception as exc:  # pragma: no cover - exercised through integration use
        state.update_job(job_id, status="failed", error=str(exc))


def _small_screen_cli_command(root: Path, payload: dict[str, Any]) -> str:
    env_bin = _runtime_env_bin()
    oslab_bin = env_bin / "oslab"
    argv = [
        str(oslab_bin if oslab_bin.exists() else "oslab"),
        "screen",
        "small",
        "--ligands",
        str(payload["ligands"]),
        "--receptor",
        str(payload["receptor"]),
        "--binding-site",
        str(payload["binding_site"]),
        "--out",
        str(payload["out"]),
        "--max-ligands",
        str(int(payload.get("max_ligands") or 20)),
        "--preset",
        str(payload.get("preset") or "drug_like"),
        "--ph",
        str(float(payload.get("ph") or 7.4)),
        "--charge-model",
        str(payload.get("charge_model") or "gasteiger"),
        "--ligand-prep-backend",
        str(payload.get("ligand_prep_backend") or "rdkit"),
        "--ligand-prep-workers",
        str(int(payload.get("ligand_prep_workers") or 1)),
        "--ligand-prep-timeout",
        str(int(payload.get("ligand_prep_timeout") or 120)),
        "--docking-workers",
        str(int(payload.get("docking_workers") or 1)),
        "--exhaustiveness",
        str(int(payload.get("exhaustiveness") or 1)),
        "--num-modes",
        str(int(payload.get("num_modes") or 1)),
        "--cpu",
        str(int(payload.get("cpu") or 1)),
        "--seed",
        str(int(payload.get("seed") or 1)),
    ]
    if bool(payload.get("no_plip", False)):
        argv.append("--no-plip")
    if bool(payload.get("no_gen3d", False)):
        argv.append("--no-gen3d")
    command = " ".join(shlex_quote(part) for part in argv)
    return f"cd {shlex_quote(str(root))} && PATH={shlex_quote(str(env_bin))}:$PATH {command}"


def _runtime_env_bin() -> Path:
    return Path(sys.executable).resolve().parent


def _runtime_oslab_bin() -> Path:
    env_bin = _runtime_env_bin()
    oslab_bin = env_bin / "oslab"
    return oslab_bin if oslab_bin.exists() else Path(shutil.which("oslab") or "oslab")


def _default_micromamba_path() -> Path:
    configured = os.environ.get("OSLAB_MICROMAMBA") or os.environ.get("MAMBA_EXE")
    candidates = [Path(configured).expanduser()] if configured else []
    adjacent_root = _runtime_env_bin().parent.parent.parent / "bin" / "micromamba"
    candidates.extend(
        [
            adjacent_root,
            Path.home() / ".local" / "bin" / "micromamba",
        ]
    )
    found = shutil.which("micromamba")
    if found:
        candidates.insert(1, Path(found))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return adjacent_root


def _dashboard_check_tools() -> dict[str, Any]:
    statuses = [*check_cli_tools(), *check_python_imports()]
    rows = [{"name": status.name, "available": status.available, "detail": status.detail} for status in statuses]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": all(row["available"] for row in rows),
        "tools": rows,
    }


def _dashboard_permissions(root: Path) -> dict[str, Any]:
    env_meta = _run_environment_metadata(root)
    # Use the dashboard process user for permissions/defaults. The SSH user in
    # run_environment.json describes how a client connects to the server and may
    # intentionally differ from the Unix account running this dashboard.
    user = str(os.environ.get("USER") or env_meta.get("user") or env_meta.get("ssh_user") or "").strip()
    mamba = _default_micromamba_path()
    env_prefix = _runtime_env_bin().parent
    can_update = (
        bool(env_meta.get("admin_user"))
        or user in {"root", "ubuntu"}
        or os.access(env_prefix, os.W_OK)
        or os.access(mamba, os.W_OK)
    )
    shared = _shared_data_root(root)
    configured_workers = env_meta.get("default_total_workers")
    try:
        default_total_workers = int(configured_workers) if configured_workers else 0
    except (TypeError, ValueError):
        default_total_workers = 0
    if default_total_workers < 1:
        detected_workers = os.cpu_count() or 1
        default_total_workers = detected_workers
    if user not in {"root", "ubuntu"} and root.resolve() != Path("/data/oslab"):
        default_total_workers = min(default_total_workers, 30)
    return {
        "user": user,
        "is_admin": can_update,
        "can_update_tools": can_update,
        "oslab_root": str(root.resolve()),
        "shared_data_root": str(shared) if shared else "",
        "default_total_workers": default_total_workers,
        "default_total_workers_note": (
            f"Detected default: {default_total_workers} CPU workers from this instance"
            + ("." if user in {"root", "ubuntu"} or root.resolve() == Path("/data/oslab") else " (capped at 30 for non-root users).")
        ),
        "tool_update_note": (
            "This dashboard user can update the shared OSLab software environment."
            if can_update
            else "Tool updates are disabled for this user; ask the OSLab admin to update the shared install."
        ),
    }


def _start_update_tools_job(state: DashboardState, payload: dict[str, Any]) -> DashboardJob:
    if not _dashboard_permissions(state.root).get("can_update_tools"):
        raise PermissionError("Tool updates are disabled for this user. Ask the OSLab admin to update the shared install.")
    job = state.add_job(DashboardJob(id=uuid.uuid4().hex[:12], kind="update-tools", request=payload))
    thread = threading.Thread(target=_run_update_tools_job, args=(state, job.id, payload), daemon=True)
    thread.start()
    return job


def _run_update_tools_job(state: DashboardState, job_id: str, payload: dict[str, Any]) -> None:
    state.update_job(job_id, status="running")
    try:
        env_name = str(payload.get("env_name") or "open-structure-lab")
        update_pip = bool(payload.get("update_pip", True))
        mamba = Path(str(payload.get("mamba") or _default_micromamba_path()))
        if not mamba.exists():
            raise FileNotFoundError(f"micromamba not found at {mamba}")
        commands: list[dict[str, Any]] = []
        mamba_command = [str(mamba), "update", "-n", env_name, "--all", "-y"]
        result = subprocess.run(
            mamba_command,
            cwd=state.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=int(payload.get("timeout_seconds") or 1800),
            check=False,
        )
        commands.append({"name": "micromamba update --all", "command": mamba_command, "returncode": result.returncode, "output_tail": result.stdout[-6000:]})
        pip_result = None
        if update_pip:
            python_bin = _runtime_env_bin() / "python"
            pip_packages = [
                "meeko",
                "plip",
                "prolif",
                "openfe",
                "openfecli",
                "openff-toolkit",
                "openmmforcefields",
                "spyrmsd",
                "MDAnalysis",
                "gemmi",
                "pydantic",
            ]
            pip_command = [str(python_bin), "-m", "pip", "install", "--upgrade", "--upgrade-strategy", "only-if-needed", *pip_packages]
            pip_result = subprocess.run(
                pip_command,
                cwd=state.root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=int(payload.get("pip_timeout_seconds") or 1800),
                check=False,
            )
            commands.append({"name": "pip update Python workflow packages", "command": pip_command, "returncode": pip_result.returncode, "output_tail": pip_result.stdout[-6000:]})
        final_returncode = result.returncode
        warning = ""
        if pip_result is not None and pip_result.returncode != 0:
            warning = "pip-managed package update reported an error; micromamba update may still have completed."
        state.update_job(
            job_id,
            status="completed" if final_returncode == 0 else "failed",
            result={
                "commands": commands,
                "returncode": final_returncode,
                "output_tail": (commands[-1]["output_tail"] if commands else ""),
                "warning": warning,
                "notes": "Updated open-source packages in the local micromamba environment. Re-run tool checks and CDK2 validation after updates.",
            },
            error="" if final_returncode == 0 else result.stdout[-1000:],
        )
    except Exception as exc:  # pragma: no cover - environment-specific
        state.update_job(job_id, status="failed", error=str(exc))


def _start_cdk2_validation_job(state: DashboardState, payload: dict[str, Any]) -> dict[str, Any]:
    job = state.add_job(DashboardJob(id=uuid.uuid4().hex[:12], kind="cdk2-validation", request=payload))
    thread = threading.Thread(target=_run_cdk2_validation_job, args=(state, job.id, payload), daemon=True)
    thread.start()
    return job.to_dict()


def _run_cdk2_validation_job(state: DashboardState, job_id: str, payload: dict[str, Any]) -> None:
    state.update_job(job_id, status="running")
    try:
        output_dir = _resolve_workspace_output_dir(
            state.root,
            payload.get("out"),
            state.root / "runs" / f"cdk2-dashboard-validation-{job_id}",
            field_name="validation output directory",
        )
        # Validation needs ligands + receptor + binding-site JSON. Look in the
        # workspace first; on a fresh install none of these have been generated
        # yet, so fall back to the package-bundled CDK2 demo (same 5 ligands
        # the Quick Start uses). Without this fallback the endpoint silently
        # fails with FileNotFoundError on a fresh workspace.
        bundled = Path(__file__).resolve().parent / "bundled_demo" / "cdk2"
        ligand_candidates = [
            state.root / "data-cache" / "validation" / "tiny_screen.smi",
            state.root / "data-cache" / "validation" / "cdk2_known_vs_decoys_20.smi",
            bundled / "demo_ligands.smi",
        ]
        validation_ligands = next((p for p in ligand_candidates if p.exists()), ligand_candidates[0])
        receptor_candidates = [
            state.root / "runs" / "cdk2-receptor" / "receptor.pdbqt",
            bundled / "receptor.pdbqt",
        ]
        validation_receptor = next((p for p in receptor_candidates if p.exists()), receptor_candidates[0])
        site_candidates = [
            state.root / "runs" / "cdk2-site" / "binding_site.json",
            bundled / "site.json",
        ]
        validation_site = next((p for p in site_candidates if p.exists()), site_candidates[0])
        summary = run_small_screen(
            ligands=validation_ligands,
            receptor_pdbqt=validation_receptor,
            binding_site_json=validation_site,
            output_dir=output_dir,
            max_ligands=int(payload.get("max_ligands") or 5),
            preset=str(payload.get("preset") or "drug_like"),
            run_plip=False,
            ligand_prep_options=LigandPrepOptions(
                ph=7.4,
                generate_3d=True,
                charge_model="gasteiger",
                backend="rdkit",
                workers=max(1, int(payload.get("ligand_prep_workers") or 2)),
                timeout_seconds=120,
            ),
            vina_options=VinaRunOptions(
                exhaustiveness=1,
                num_modes=1,
                cpu=1,
                seed=1,
                workers=max(1, int(payload.get("docking_workers") or 1)),
            ),
        )
        expected_min_docked = int(payload.get("expected_min_docked") or 5)
        expected_max_best_score = float(payload.get("expected_max_best_score") or -5.0)
        passed = summary.docked_ligands >= expected_min_docked and (
            summary.best_score is not None and summary.best_score <= expected_max_best_score
        )
        state.update_job(
            job_id,
            status="completed" if passed else "failed",
            result={
                "passed": passed,
                "output_dir": summary.output_dir,
                "docked_ligands": summary.docked_ligands,
                "best_ligand": summary.best_ligand,
                "best_score": summary.best_score,
                "expected_min_docked": expected_min_docked,
                "expected_max_best_score": expected_max_best_score,
                "report": summary.docking_report,
                "results_csv": summary.results_csv,
                "notes": "CDK2 validation passes when the tiny screen docks all expected ligands and the best Vina score is at or below the expected threshold.",
            },
            error="" if passed else "CDK2 validation did not meet expected thresholds.",
        )
    except Exception as exc:  # pragma: no cover - exercised through integration use
        state.update_job(job_id, status="failed", error=str(exc))


def _start_terminal_orchestration(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    username = safe_user_name(username or payload.get("username") or get_request_user())
    root = _dashboard_user_root(state.root, username)
    _enforce_resource_limit(state, "terminal-orchestration", username)
    session_id = new_job_id("workflow")
    session_name = screen_session_name("workflow", session_id)
    progress_json = job_progress_path(root, "terminal-orchestration", session_id)
    log_path = progress_json.parent / "terminal.log"
    progress_json.parent.mkdir(parents=True, exist_ok=True)
    env_bin = _runtime_env_bin()
    oslab_bin = _runtime_oslab_bin()
    command = (
        f"cd {shlex_quote(str(root))} && "
        f"PATH={shlex_quote(str(env_bin))}:$PATH "
        f"{shlex_quote(str(oslab_bin))} orchestrate terminal "
        f"--root {shlex_quote(str(root))} "
        f"--progress-json {shlex_quote(str(progress_json))}; "
        "echo; echo 'Terminal orchestration finished. Reports are listed in the dashboard Reports tab.'"
    )
    opened_terminal, open_error = _open_macos_terminal_command(f"set -o pipefail; ({command}) 2>&1 | tee -a {shlex_quote(str(log_path))}", root)
    if not opened_terminal:
        screen = shutil.which("screen")
        if not screen:
            raise RuntimeError("Could not open Terminal.app directly, and screen is not available as a fallback.")
        subprocess.run(
            [screen, "-dmS", session_name, _screen_shell(), "-lc", f"{command} 2>&1 | tee -a {shlex_quote(str(log_path))}"],
            cwd=root,
            check=True,
        )
        session_label = session_name
        attach_command = _screen_attach_command(session_name, root)
        terminal_backend = "screen"
    else:
        session_label = "Terminal.app window"
        attach_command = "Open Terminal.app window created by the dashboard."
        terminal_backend = "terminal-app"
        session_name = ""
    job = state.add_job(
        DashboardJob(
            id=session_id,
            kind="terminal-orchestration",
            username=username,
            status="running",
            request=payload,
            result={
                "session_name": session_name,
                "session_label": session_label,
                "attach_command": attach_command,
                "progress_json": str(progress_json),
                "log_path": str(log_path),
                "terminal_backend": terminal_backend,
                "notes": "Interactive selections happen in Terminal.app. This dashboard monitors the progress artifact and run outputs.",
            },
        )
    )
    result = dict(job.result or {})
    result["attach_command"] = attach_command
    result["terminal_opened"] = opened_terminal
    if open_error:
        result["terminal_open_error"] = open_error
    state.update_job(job.id, result=result)
    return job.to_dict()


def _start_hit_refinement_terminal(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    username = safe_user_name(username or payload.get("username") or get_request_user())
    root = _dashboard_user_root(state.root, username)
    _enforce_resource_limit(state, "hit-refinement", username)
    session_id = new_job_id("hit-refinement")
    session_name = screen_session_name("hit-refine", session_id)
    progress_json = job_progress_path(root, "hit-refinement", session_id)
    log_path = progress_json.parent / "terminal.log"
    progress_json.parent.mkdir(parents=True, exist_ok=True)
    initial_progress = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "job_id": session_id,
        **campaign_context(),
        "status": "starting",
        "current_step": "select-run",
        "progress_json": str(progress_json),
        "terminal_log": str(log_path),
        "steps": [
            {"key": "select-run", "status": "pending"},
            {"key": "select-hits", "status": "pending"},
            {"key": "parameters", "status": "pending"},
            {"key": "redock", "status": "pending"},
            {"key": "plip", "status": "pending"},
            {"key": "report", "status": "pending"},
        ],
        "selections": {},
        "provenance": runtime_provenance(forcefields={"vina": "CLI"}, structures={}),
        "events": [{"time": datetime.now(timezone.utc).isoformat(), "step": "start", "message": "Starting hit refinement terminal."}],
        "notes": ["Answer the terminal prompts; this monitor updates after each answer."],
    }
    atomic_write_json(progress_json, initial_progress)
    env_bin = _runtime_env_bin()
    oslab_bin = _runtime_oslab_bin()
    command = (
        f"cd {shlex_quote(str(root))} && "
        f"PATH={shlex_quote(str(env_bin))}:$PATH "
        f"{shlex_quote(str(oslab_bin))} refine hits "
        f"--root {shlex_quote(str(root))} "
        "--interactive "
        f"--progress-json {shlex_quote(str(progress_json))}; "
        "echo; echo 'Hit refinement finished. Reports are listed in the dashboard Reports tab.'"
    )
    opened_terminal, open_error = _open_macos_terminal_command(f"set -o pipefail; ({command}) 2>&1 | tee -a {shlex_quote(str(log_path))}", root)
    if not opened_terminal:
        screen = shutil.which("screen")
        if not screen:
            raise RuntimeError("Could not open Terminal.app directly, and screen is not available as a fallback.")
        subprocess.run(
            [screen, "-dmS", session_name, _screen_shell(), "-lc", f"{command} 2>&1 | tee -a {shlex_quote(str(log_path))}"],
            cwd=root,
            check=True,
        )
        session_label = session_name
        attach_command = _screen_attach_command(session_name, root)
        terminal_backend = "screen"
    else:
        session_label = "Terminal.app window"
        attach_command = "Open Terminal.app window created by the dashboard."
        terminal_backend = "terminal-app"
        session_name = ""
    job = state.add_job(
        DashboardJob(
            id=session_id,
            kind="hit-refinement",
            username=username,
            status="running",
            request=payload,
            result={
                "session_name": session_name,
                "session_label": session_label,
                "attach_command": attach_command,
                "progress_json": str(progress_json),
                "log_path": str(log_path),
                "progress": initial_progress,
                "terminal_backend": terminal_backend,
                "notes": "Interactive hit refinement happens in Terminal.app. The dashboard monitors the progress JSON and final report paths.",
            },
        )
    )
    result = dict(job.result or {})
    result["terminal_opened"] = opened_terminal
    if open_error:
        result["terminal_open_error"] = open_error
    state.update_job(job.id, result=result)
    return job.to_dict()


def _start_md_optimization_terminal(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    username = safe_user_name(username or payload.get("username") or get_request_user())
    root = _dashboard_user_root(state.root, username)
    _enforce_resource_limit(state, "md-optimization", username)
    session_id = new_job_id("md-optimization")
    session_name = screen_session_name("md-optim", session_id)
    progress_json = job_progress_path(root, "md-optimization", session_id)
    log_path = progress_json.parent / "terminal.log"
    progress_json.parent.mkdir(parents=True, exist_ok=True)

    top_n = 3
    output_dir = str(root / "reports" / f"md-optimization-{session_id}")

    initial_progress = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "job_id": session_id,
        **campaign_context(),
        "status": "starting",
        "current_step": "select-inputs",
        "current_ligand": "",
        "progress_json": str(progress_json),
        "terminal_log": str(log_path),
        "steps": [
            {"key": "select-inputs", "status": "pending"},
            {"key": "md-prep", "status": "pending"},
            {"key": "md-simulation", "status": "pending"},
            {"key": "md-interactions", "status": "pending"},
            {"key": "mmgbsa", "status": "pending"},
            {"key": "report", "status": "pending"},
        ],
        "ligand_status": {},
        "ligand_results": {},
        "ligand_progress": {"completed_ligands": 0, "total_ligands": 0, "current_ligand": "", "current_stage": ""},
        "selections": {},
        "provenance": runtime_provenance(forcefields={"protein": "amber14-all.xml", "water": "amber14/tip3pfb.xml", "ligand": "openff-2.2.0"}, structures={}),
        "events": [{"time": datetime.now(timezone.utc).isoformat(), "message": "Starting MD optimization pipeline."}],
        "notes": ["MD wizard runs in Terminal. The dashboard monitors choices, cluster export, progress, and reports."],
        "dashboard_defaults": {
            "output_dir": output_dir,
            "top_n": top_n,
            "ph": 7.4,
            "water_padding_nm": 1.2,
            "ionic_strength_m": 0.15,
            "temperature_k": 300.0,
            "minimization_steps": 1000,
            "smirnoff_forcefield": "openff-2.2.0",
            "production_ns": 1.0,
            "nvt_ns": 0.1,
            "npt_ns": 0.1,
            "timestep_fs": 2.0,
            "n_frames": 50,
            "crop_radius_angstrom": 15.0,
            "max_solvated_atoms": 200_000,
        },
    }
    atomic_write_json(progress_json, initial_progress)

    env_bin = _runtime_env_bin()
    oslab_bin = _runtime_oslab_bin()

    command = (
        f"cd {shlex_quote(str(root))} && "
        f"PYTHONUTF8=1 PATH={shlex_quote(str(env_bin))}:$PATH "
        f"{shlex_quote(str(oslab_bin))} md optimize "
        f"--root {shlex_quote(str(root))} "
        "--interactive "
        f"--progress-json {shlex_quote(str(progress_json))}; "
        "echo; echo 'MD optimization finished. Results are listed in the MD and Optimization tab.'"
    )

    opened_terminal, open_error = _open_macos_terminal_command(f"set -o pipefail; ({command}) 2>&1 | tee -a {shlex_quote(str(log_path))}", root)
    if not opened_terminal:
        screen = shutil.which("screen")
        if not screen:
            raise RuntimeError("Could not open Terminal.app directly, and screen is not available as a fallback.")
        subprocess.run(
            [screen, "-dmS", session_name, _screen_shell(), "-lc", f"({command}) 2>&1 | tee -a {shlex_quote(str(log_path))}"],
            cwd=root,
            check=True,
        )
        session_label = session_name
        attach_command = _screen_attach_command(session_name, root)
        terminal_backend = "screen"
    else:
        session_label = "Terminal.app window"
        attach_command = "Open Terminal.app window created by the dashboard."
        terminal_backend = "terminal-app"
        session_name = ""

    job = state.add_job(
        DashboardJob(
            id=session_id,
            kind="md-optimization",
            username=username,
            status="running",
            request=payload,
            result={
                "session_name": session_name,
                "session_label": session_label,
                "attach_command": attach_command,
                "progress_json": str(progress_json),
                "log_path": str(log_path),
                "progress": initial_progress,
                "terminal_backend": terminal_backend,
                "notes": "MD optimization pipeline runs automatically in Terminal.app. The dashboard monitors the progress JSON.",
            },
        )
    )
    result = dict(job.result or {})
    result["terminal_opened"] = opened_terminal
    if open_error:
        result["terminal_open_error"] = open_error
    state.update_job(job.id, result=result)
    return job.to_dict()


_FEP_FORCEFIELD_RE = re.compile(r"^openff-\d+\.\d+\.\d+$")


def _start_fep_terminal(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    """Launch an interactive FEP terminal session via screen."""
    username = safe_user_name(username or payload.get("username") or get_request_user())
    root = _dashboard_user_root(state.root, username)
    root_resolved = root.resolve()
    _enforce_resource_limit(state, "fep", username)
    session_id = new_job_id("fep")
    session_name = screen_session_name("fep", session_id)
    progress_json = job_progress_path(root, "fep", session_id)
    progress_json.parent.mkdir(parents=True, exist_ok=False)
    log_path = progress_json.parent / "terminal.log"

    md_progress_json = str(payload.get("md_progress_json") or "").strip()
    if md_progress_json:
        md_resolved = Path(md_progress_json).resolve()
        if not _is_within(md_resolved, root_resolved):
            raise ValueError("md_progress_json must be under the project root.")
        md_progress_json = str(md_resolved)

    try:
        top_n = int(payload.get("top_n") or 3)
    except (TypeError, ValueError):
        raise ValueError("top_n must be an integer")
    if not (2 <= top_n <= 50):
        raise ValueError(f"top_n {top_n} is outside the supported range [2, 50]")

    input_mode = str(payload.get("input_mode") or "topn").strip().lower()
    if input_mode not in {"topn", "analog"}:
        raise ValueError(f"input_mode {input_mode!r} must be 'topn' or 'analog'")

    analog_parent = str(payload.get("analog_parent") or "").strip()
    if analog_parent and not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$", analog_parent):
        raise ValueError("analog_parent name contains invalid characters")

    try:
        n_analogs = int(payload.get("n_analogs") or 20)
    except (TypeError, ValueError):
        raise ValueError("n_analogs must be an integer")
    if not (2 <= n_analogs <= 200):
        raise ValueError(f"n_analogs {n_analogs} is outside the supported range [2, 200]")

    raw_output_dir = str(payload.get("output_dir") or "").strip()
    if raw_output_dir:
        out_resolved = Path(raw_output_dir).resolve()
        if not _is_within(out_resolved, root_resolved):
            raise ValueError("output_dir must be under the project root.")
        output_dir = str(out_resolved)
    else:
        output_dir = str(root / "reports" / f"fep-{session_id}")

    sim_options = payload.get("sim_options") or {}

    def _bounded_int(value: Any, default: int, lo: int, hi: int, label: str) -> int:
      try:
        ivalue = int(value) if value is not None else default
      except (TypeError, ValueError):
        raise ValueError(f"{label} must be an integer")
      if not (lo <= ivalue <= hi):
        raise ValueError(f"{label} {ivalue} is outside the supported range [{lo}, {hi}]")
      return ivalue

    def _bounded_float(value: Any, default: float, lo: float, hi: float, label: str) -> float:
      try:
        fvalue = float(value) if value is not None else default
      except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number")
      if not (lo <= fvalue <= hi):
        raise ValueError(f"{label} {fvalue} is outside the supported range [{lo}, {hi}]")
      return fvalue

    n_lambda = _bounded_int(sim_options.get("n_lambda"), 11, 5, 64, "n_lambda")
    n_steps_per_window = _bounded_int(
      sim_options.get("n_steps_per_window"), 25_000, 1_000, 10_000_000, "n_steps_per_window"
    )
    n_equilibration_steps = _bounded_int(
      sim_options.get("n_equilibration_steps"), 5_000, 0, 1_000_000, "n_equilibration_steps"
    )
    temperature_k = _bounded_float(
      sim_options.get("temperature_k"), 300.0, 200.0, 500.0, "temperature_k"
    )

    raw_forcefield = str(sim_options.get("forcefield") or "openff-2.2.1").strip()
    if not _FEP_FORCEFIELD_RE.match(raw_forcefield):
      raise ValueError(
        f"forcefield {raw_forcefield!r} is not a valid SMIRNOFF identifier "
        "(expected 'openff-MAJOR.MINOR.PATCH')."
      )

    initial_progress = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "job_id": session_id,
        **campaign_context(),
        "status": "starting",
        "current_step": "select-inputs",
        "session_id": session_id,
        "progress_json": str(progress_json),
        "terminal_log": str(log_path),
        "steps": [
            {"key": "select-inputs",    "status": "pending"},
            {"key": "network-planning", "status": "pending"},
            {"key": "edge-prep",        "status": "pending"},
            {"key": "fep-run",          "status": "pending"},
            {"key": "analysis",         "status": "pending"},
            {"key": "report",           "status": "pending"},
        ],
        "edge_status": {},
        "edge_results": {},
        "network_plan": {},
        "ligand_ranking": [],
        "selections": {},
        "provenance": runtime_provenance(forcefields={"ligand": raw_forcefield, "rbfe_backend": "OpenFE"}, structures={}),
        "events": [{"time": datetime.now(timezone.utc).isoformat(), "message": "Starting FEP pipeline."}],
        "notes": ["FEP pipeline runs in terminal. Dashboard monitors progress JSON."],
        # Defaults from the dashboard form. The wizard reads these and uses
        # them as the *defaults* for matching prompts so the user can press
        # Enter to accept what they configured in the UI.
        "dashboard_defaults": {
            "input_mode": input_mode,
            "analog_parent": analog_parent,
            "n_analogs": n_analogs,
            "top_n": top_n,
            "n_lambda": n_lambda,
            "n_steps_per_window": n_steps_per_window,
            "n_equilibration_steps": n_equilibration_steps,
            "temperature_k": temperature_k,
            "forcefield": raw_forcefield,
            "output_dir": output_dir,
        },
    }
    # Atomic write so the dashboard never sees a half-formed progress.json
    # while the wizard is still constructing the initial state.
    _write_json_atomic(progress_json, initial_progress)

    env_bin = _runtime_env_bin()
    oslab_bin = _runtime_oslab_bin()

    command = (
        f"cd {shlex_quote(str(root))} && "
        f"PYTHONUTF8=1 OSLAB_OPENMM_PLATFORM=${{OSLAB_OPENMM_PLATFORM:-CUDA}} "
        f"OSLAB_CUDA_PRECISION=${{OSLAB_CUDA_PRECISION:-mixed}} "
        f"PATH={shlex_quote(str(env_bin))}:$PATH "
        f"{shlex_quote(str(oslab_bin))} fep run "
        f"--root {shlex_quote(str(root))} "
        f"--interactive "
        f"--progress-json {shlex_quote(str(progress_json))} "
        + (f"--md-progress-json {shlex_quote(md_progress_json)} " if md_progress_json else "")
        + f"--top-n {top_n} "
        f"--n-lambda {n_lambda} "
        f"--n-steps-per-window {n_steps_per_window} "
        f"--n-equilibration-steps {n_equilibration_steps} "
        f"--temperature-k {temperature_k} "
        f"--forcefield {shlex_quote(raw_forcefield)} "
        f"--out {shlex_quote(output_dir)}; "
        "echo; echo 'FEP pipeline finished. Results are listed in the FEP tab.'"
    )

    opened_terminal, open_error = _open_macos_terminal_command(f"set -o pipefail; ({command}) 2>&1 | tee -a {shlex_quote(str(log_path))}", root)
    if not opened_terminal:
        screen = shutil.which("screen")
        if not screen:
            raise RuntimeError("Could not open Terminal.app directly, and screen is not available as a fallback.")
        subprocess.run(
            [screen, "-dmS", session_name, _screen_shell(), "-lc",
             f"({command}) 2>&1 | tee -a {shlex_quote(str(log_path))}"],
            cwd=root,
            check=True,
        )
        session_label = session_name
        attach_command = _screen_attach_command(session_name, root)
        terminal_backend = "screen"
    else:
        session_label = "Terminal.app window"
        attach_command = "Open Terminal.app window created by the dashboard."
        terminal_backend = "terminal-app"
        session_name = ""

    job = state.add_job(
        DashboardJob(
            id=session_id,
            kind="fep",
            username=username,
            status="running",
            request=payload,
            result={
                "session_name": session_name,
                "session_label": session_label,
                "attach_command": attach_command,
                "progress_json": str(progress_json),
                "log_path": str(log_path),
                "progress": initial_progress,
                "terminal_backend": terminal_backend,
                "notes": "FEP pipeline runs interactively in Terminal.app. The dashboard monitors the progress JSON.",
            },
        )
    )
    result = dict(job.result or {})
    result["terminal_opened"] = opened_terminal
    if open_error:
        result["terminal_open_error"] = open_error
    state.update_job(job.id, result=result)
    return job.to_dict()


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _screen_shell() -> str:
    return shutil.which("zsh") or shutil.which("bash") or "/bin/sh"


def _aws_public_ipv4() -> str:
    try:
        token_request = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            method="PUT",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
        )
        with urllib.request.urlopen(token_request, timeout=1) as response:
            token = response.read().decode().strip()
        ip_request = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/public-ipv4",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(ip_request, timeout=1) as response:
            return response.read().decode().strip()
    except Exception:
        return ""


def _screen_attach_command(session_name: str, root: Path | None = None) -> str:
    if os.uname().sysname == "Darwin":
        return f"screen -r {session_name}"

    connection = _dashboard_connection_info(root) if root is not None else {}
    host = str(connection.get("ssh_attach_host") or "").strip() or os.environ.get("OSLAB_SSH_ATTACH_HOST", "").strip()
    if not host and connection.get("ssh_host"):
        user = str(connection.get("ssh_user") or "").strip()
        host = f"{user}@{connection['ssh_host']}" if user else str(connection["ssh_host"])
    if not host:
        public_ip = _aws_public_ipv4()
        if public_ip:
            host = f"ubuntu@{public_ip}"
    if not host:
        return f"screen -r {session_name}"

    identity = str(connection.get("ssh_identity") or os.environ.get("OSLAB_SSH_IDENTITY", "~/.ssh/codex-key")).strip()
    identity_arg = f" -i {shlex_quote(identity)}" if identity else ""
    remote_command = shlex_quote(f"screen -r {session_name}")
    return f"ssh -t{identity_arg} {shlex_quote(host)} {remote_command}"



def _run_environment_metadata(root: Path) -> dict[str, Any]:
    """Load optional per-workspace execution metadata for script generation."""
    candidates: list[Path] = []
    for base in [root, *root.parents]:
        if base == Path("/"):
            continue
        candidates.extend(
            [
                base / "run_environment.json",
                base / "config" / "run_environment.json",
                base / ".oslab" / "run_environment.json",
            ]
        )
    candidates.extend(
        [
            Path("/data/oslab/run_environment.json"),
            Path("/opt/oslab/current/run_environment.json"),
        ]
    )
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text())
        except Exception:
            continue
        if isinstance(data, dict):
            data.setdefault("metadata_path", str(path))
            return data
    return {}

def _offset_local_dashboard_port(local_port: str, remote_port: str, actual_remote_port: int | None) -> str:
    if actual_remote_port is None:
        return local_port
    try:
        return str(int(local_port) + (int(actual_remote_port) - int(remote_port)))
    except (TypeError, ValueError):
        return local_port


def _dashboard_connection_info(root: Path, dashboard_port: int | None = None) -> dict[str, Any]:
    env_meta = _run_environment_metadata(root)
    process_user = str(os.environ.get("USER") or env_meta.get("user") or "").strip()
    meta_host = str(env_meta.get("ssh_host") or env_meta.get("server_ip") or env_meta.get("server_hostname") or "").strip()
    meta_user = str(env_meta.get("ssh_user") or "").strip()
    if process_user and process_user not in {"root", "ubuntu"} and meta_host:
        meta_user = process_user
    host_value = f"{meta_user}@{meta_host}" if meta_user and meta_host else meta_host
    if not host_value:
        host_value = str(env_meta.get("ssh_attach_host") or "").strip()
    if not host_value:
        host_value = os.environ.get("OSLAB_SSH_ATTACH_HOST", "").strip()
    public_ip = _aws_public_ipv4()
    if not host_value and public_ip:
        host_value = f"ubuntu@{public_ip}"
    user = ""
    host = host_value
    if "@" in host_value:
        user, host = host_value.split("@", 1)
    elif host_value:
        user = str(env_meta.get("ssh_user") or os.environ.get("USER", "")).strip() or "ubuntu"
    identity = str(env_meta.get("ssh_key") or env_meta.get("ssh_identity") or os.environ.get("OSLAB_SSH_IDENTITY", "~/.ssh/codex-key")).strip()
    metadata_remote_port = str(env_meta.get("remote_dashboard_port") or env_meta.get("dashboard_remote_port") or os.environ.get("OSLAB_DASHBOARD_PORT", "8766")).strip() or "8766"
    metadata_local_port = str(env_meta.get("local_dashboard_port") or env_meta.get("dashboard_local_port") or os.environ.get("OSLAB_LOCAL_FORWARD_PORT", "9877")).strip() or "9877"
    remote_port = str(dashboard_port or metadata_remote_port)
    local_port = _offset_local_dashboard_port(metadata_local_port, metadata_remote_port, dashboard_port)
    root_value = str(env_meta.get("oslab_root") or root)
    shared = _shared_data_root(root)
    login_host = f"{user}@{host}" if user and host else host_value
    identity_display = identity if identity.startswith("~/") else shlex_quote(identity)
    identity_arg = f" -i {identity_display}" if identity else ""
    login_command = f"ssh{identity_arg} {login_host}" if login_host else ""
    tunnel_command = (
        f"ssh -N -L {local_port}:127.0.0.1:{remote_port}"
        f"{identity_arg} {login_host}"
        if login_host
        else ""
    )
    return {
        "ssh_attach_host": host_value,
        "ssh_user": user,
        "ssh_host": host,
        "ssh_identity": identity,
        "dashboard_remote_port": remote_port,
        "dashboard_local_port": local_port,
        "root": root_value,
        "shared_data_root": str(shared) if shared else "",
        "login_command": login_command,
        "tunnel_command": tunnel_command,
        "dashboard_url": f"http://127.0.0.1:{local_port}/",
    }


def _screen_session_running(session_name: str) -> bool:
    screen = shutil.which("screen")
    if not screen:
        return False
    result = subprocess.run([screen, "-ls", session_name], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return f".{session_name}" in result.stdout or f"\t{session_name}" in result.stdout or f" {session_name}" in result.stdout


def _quit_screen_session(session_name: str) -> None:
    screen = shutil.which("screen")
    if not screen:
        return
    subprocess.run([screen, "-S", session_name, "-X", "quit"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


def _terminal_progress_completed(result: dict[str, Any]) -> bool:
    progress_path = str(result.get("progress_json") or "")
    if not progress_path:
        return False
    progress = _read_json_file(Path(progress_path))
    return bool(progress and progress.get("status") in {"completed", "failed"})


def _tail_text(path: Path, max_chars: int = 4000) -> str:
    try:
        if not path.exists() or not path.is_file():
            return ""
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    return text[-max_chars:]


def _open_macos_terminal_attach(session_name: str, root: Path) -> tuple[bool, str]:
    if os.uname().sysname != "Darwin":
        return False, "Automatic terminal opening is only implemented for macOS."
    attach_command = f"cd {shlex_quote(str(root))}; screen -r {shlex_quote(session_name)}"
    apple_script = (
        'tell application "Terminal"\n'
        "  activate\n"
        f"  do script {json.dumps(attach_command)}\n"
        "end tell\n"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()
    return True, ""


def _open_macos_terminal_command(command: str, root: Path) -> tuple[bool, str]:
    if os.uname().sysname != "Darwin":
        return False, "Automatic terminal opening is only implemented for macOS."
    terminal_command = f"cd {shlex_quote(str(root))}; {command}"
    apple_script = (
        'tell application "Terminal"\n'
        "  activate\n"
        f"  do script {json.dumps(terminal_command)}\n"
        "end tell\n"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", apple_script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        return False, str(exc)
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()
    return True, ""




def _is_foreign_dashboard_job(root: Path, job: DashboardJob) -> bool:
    result = job.result if isinstance(job.result, dict) else {}
    progress_value = str(result.get("progress_json") or "")
    attach_command = str(result.get("attach_command") or "")
    if "ubuntu@3.128.25.91" in attach_command and root.name == "OSLabLambda":
        return True
    if progress_value:
        try:
            progress_path = Path(progress_value).resolve()
            if root.resolve() not in [progress_path, *progress_path.parents]:
                return True
        except Exception:
            return True
    return False


def _dashboard_resource_limit(kind: str) -> int:
    env_key = f"OSLAB_MAX_{kind.upper().replace('-', '_')}_JOBS"
    try:
        return max(1, int(os.environ.get(env_key) or 1))
    except ValueError:
        return 1


def _enforce_resource_limit(state: DashboardState, kind: str, username: str | None = None) -> None:
    username = safe_user_name(username or get_request_user())
    limit = _dashboard_resource_limit(kind)
    running = [
        job
        for job in state._jobs_snapshot(username)
        if job.get("kind") == kind and job.get("status") in {"queued", "running", "starting"}
    ]
    if len(running) >= limit:
        raise RuntimeError(
            f"{kind} resource limit reached ({len(running)}/{limit}). "
            f"Set OSLAB_MAX_{kind.upper().replace('-', '_')}_JOBS to raise it."
        )


def _summary_kind(filename: str) -> str:
    if filename.startswith("small_screen"):
        return "small-screen"
    if filename.startswith("validation"):
        return "validation"
    if filename.startswith("hit_refinement"):
        return "hit-refinement"
    if filename.startswith("docking"):
        return "docking"
    return "report"


def _run_sort_key(row: dict[str, Any]) -> str:
    return str(row.get("created_at") or "")


def _dedupe_run_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"hit-refinement": 0, "md-optimization": 1, "validation": 2, "small-screen": 3, "docking": 4}
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("delete_path") or row.get("summary_path") or ""),
            str(row.get("results_json") or row.get("report_markdown") or ""),
        )
        existing = best.get(key)
        if existing is None or priority.get(str(row.get("kind")), 9) < priority.get(str(existing.get("kind")), 9):
            best[key] = row
    return sorted(best.values(), key=_run_sort_key, reverse=True)


def _dashboard_structure_records(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in list_structure_records(root):
        row = record.model_dump(mode="json")
        gene = _record_gene_symbol(record.source, record.identifier)
        row["gene_symbol"] = gene
        if gene:
            row["key"] = _gene_key(row["key"], gene)
        rows.append(row)
    return rows


def _record_gene_symbol(source: str, identifier: str) -> str:
    cache_key = f"{source}:{identifier}"
    if cache_key in _GENE_CACHE:
        return _GENE_CACHE[cache_key]
    gene = ""
    if source == "alphafold":
        data = _safe_urlopen_json(f"https://alphafold.ebi.ac.uk/api/prediction/{identifier}") or []
        if isinstance(data, list) and data:
            gene = str(data[0].get("gene") or "")
    _GENE_CACHE[cache_key] = gene
    return gene


def _gene_key(key: str, gene: str) -> str:
    parts = key.split(":")
    if len(parts) >= 2:
        parts[1] = f"{gene}/{parts[1]}"
        return ":".join(parts)
    return f"{gene}:{key}"


def _allowed_report_roots(root: Path) -> list[Path]:
    roots: list[Path] = [root.resolve()]
    for sub in ("reports", "runs"):
        d = root / sub
        try:
            if not d.is_dir():
                continue
            for entry in d.iterdir():
                try:
                    if entry.is_symlink():
                        roots.append(entry.resolve())
                except OSError:
                    continue
        except OSError:
            continue
    return roots


def _read_report(root: Path, query: dict[str, list[str]]) -> dict[str, Any]:
    raw = Path(query.get("path", [""])[0])
    raw_abs = raw if raw.is_absolute() else (Path.cwd() / raw)
    requested_resolved = raw_abs.resolve()
    allowed = _allowed_report_roots(root)
    accessible = any(a in [requested_resolved, *requested_resolved.parents] for a in allowed)
    if not accessible:
        raise ValueError("report must be under the project root")
    requested = requested_resolved if requested_resolved.exists() else raw_abs
    if not requested.is_file():
        raise FileNotFoundError(requested)
    max_chars = 200_000
    with requested.open(errors="ignore") as handle:
        text = handle.read(max_chars + 1)
    truncated = len(text) > max_chars
    if truncated:
        text = text[:max_chars]
    return {"path": str(requested), "text": text, "truncated": truncated, "size_bytes": requested.stat().st_size}


def _delete_report(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    report_dir = Path(str(payload.get("delete_path") or "")).resolve()
    allowed_roots = [(root / "reports").resolve(), (root / "runs").resolve()]
    if not any(allowed in [report_dir, *report_dir.parents] for allowed in allowed_roots):
        raise ValueError("report deletion is limited to the project reports and runs folders")
    if report_dir in allowed_roots or report_dir == root.resolve():
        raise ValueError("refusing to delete a top-level project folder")
    if not report_dir.exists():
        return {"status": "not-found", "deleted_path": str(report_dir)}
    if not report_dir.is_dir():
        raise ValueError("delete_path must be a report directory")
    shutil.rmtree(report_dir)
    return {"status": "deleted", "deleted_path": str(report_dir)}


def _target_base_from_report_name(name: str) -> str:
    for suffix in (
        "-md-optimization",
        "-hit-refinement",
        "-docking",
        "-fep",
        "-screen",
    ):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _ensure_package_root(root: Path) -> Path:
    package_root = root / "packages"
    try:
        package_root.mkdir(parents=True, exist_ok=True)
        try:
            package_root.chmod(0o1777)
        except OSError:
            pass
        probe = package_root / f".write-test-{uuid.uuid4().hex}"
        probe.write_text("ok\n")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise ValueError(
            f"Could not create a downloadable package under {package_root}. "
            "Check that this dashboard user can write to the OSLab root packages/ folder."
        ) from exc
    return package_root


def _package_row_from_directory(root: Path, directory: Path) -> dict[str, Any] | None:
    try:
        resolved = directory.resolve()
        if root not in [resolved, *resolved.parents] or not resolved.is_dir():
            return None
        if resolved.name in {"dashboard-jobs", "packages"}:
            return None
        if resolved.parent.name == "packages" or resolved.name.startswith("."):
            return None
        progress_json = resolved / "progress.json"
        markdowns = sorted((resolved / "report").glob("*.md")) if (resolved / "report").exists() else []
        report_markdown = str(markdowns[0]) if markdowns else ""
        results_json = ""
        for name in ("vina_results.json", "per_ligand_seed_summary.json", "fep_results.json", "md_optimization_results.json"):
            candidate = resolved / "report" / name
            if candidate.exists():
                results_json = str(candidate)
                break
        name = resolved.name
        kind = "artifacts"
        for suffix, inferred in (
            ("-md-optimization", "md-optimization"),
            ("-hit-refinement", "hit-refinement"),
            ("-docking", "docking"),
            ("-fep", "fep"),
            ("-screen", "small-screen"),
        ):
            if name.endswith(suffix):
                kind = inferred
                break
        return {
            "key": f"{kind}:{name}",
            "name": name,
            "summary_path": str(progress_json if progress_json.exists() else resolved),
            "delete_path": str(resolved),
            "kind": kind,
            "report_markdown": report_markdown,
            "results_json": results_json,
            "results_csv": "",
            "progress_json": str(progress_json) if progress_json.exists() else "",
            "created_at": datetime.fromtimestamp(resolved.stat().st_mtime, timezone.utc).isoformat(),
            "status": "available",
        }
    except OSError:
        return None


def _package_candidate_rows(state: DashboardState, username: str | None = None) -> list[dict[str, Any]]:
    scan_roots = _dashboard_workspace_roots(state.root, username)
    rows = list(state._runs(username))
    seen = {str(row.get("delete_path") or row.get("summary_path") or row.get("name") or "") for row in rows}
    for root in scan_roots:
        for base in (root / "reports", root / "runs"):
            if not base.exists():
                continue
            for directory in sorted(base.iterdir()):
                row = _package_row_from_directory(root, directory)
                if not row:
                    continue
                key = str(row.get("delete_path") or row.get("summary_path") or row.get("name") or "")
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
    return rows


def _package_last_target_results(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    root = _dashboard_user_root(state.root, username).resolve()
    runs = _package_candidate_rows(state, username)
    completed_kinds = {"docking", "small-screen", "hit-refinement", "md-optimization", "fep", "validation", "artifacts"}
    candidates = [
        row for row in runs
        if row.get("kind") in completed_kinds and (row.get("report_markdown") or row.get("summary_path") or row.get("delete_path"))
    ]
    if not candidates:
        raise ValueError("No reports or run artifacts were found to package.")
    candidates.sort(key=lambda row: _parse_iso_timestamp(row.get("created_at")), reverse=True)
    requested_base = str(payload.get("target_base") or "").strip()
    target_base = requested_base or _target_base_from_report_name(str(candidates[0].get("name") or "oslab-target"))
    if not target_base:
        raise ValueError("Could not determine the last target.")

    package_root = _ensure_package_root(root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_base = re.sub(r"[^A-Za-z0-9_.-]+", "_", target_base).strip("_") or "oslab-target"
    zip_path = package_root / f"{safe_base}-completed-results-{stamp}.zip"

    selected_rows = [
        row for row in runs
        if str(row.get("name") or "").startswith(target_base)
        and row.get("kind") in completed_kinds
        and (row.get("report_markdown") or row.get("summary_path") or row.get("delete_path"))
    ]
    include_dirs: list[Path] = []
    include_files: list[Path] = []
    for row in selected_rows:
        for key in ("report_markdown", "summary_path", "results_json", "results_csv", "progress_json"):
            value = str(row.get(key) or "")
            if value:
                path = Path(value).resolve()
                if path.exists() and root in [path, *path.parents]:
                    include_files.append(path)
        delete_path = str(row.get("delete_path") or "")
        if delete_path:
            path = Path(delete_path).resolve()
            if path.exists() and path.is_dir() and root in [path, *path.parents]:
                include_dirs.append(path)
    for scan_root in _dashboard_workspace_roots(state.root, username):
        for base_dir in (scan_root / "reports", scan_root / "runs"):
            for path in base_dir.glob(f"{target_base}*"):
                resolved = path.resolve()
                if resolved.exists() and scan_root in [resolved, *resolved.parents]:
                    include_dirs.append(resolved)

    seen_paths: set[Path] = set()
    manifest: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target_base": target_base,
        "oslab_root": str(state.root.resolve()),
        "user_root": str(root),
        "dashboard_user": safe_user_name(username or get_request_user()),
        "server_user": os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
        "included_reports": selected_rows,
        "included_paths": [],
        "skipped_paths": [],
        "notes": (
            "Package generated from the newest target family in the Reports tab. "
            "It includes completed block outputs found under reports/ and runs/. "
            "The ZIP is served through the dashboard so the browser downloads it to the user's local computer; "
            "the browser controls whether the destination is Desktop, Downloads, or another folder."
        ),
    }
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(set(include_files)):
            if path in seen_paths or not path.is_file():
                continue
            seen_paths.add(path)
            archive_root = next((base for base in _dashboard_workspace_roots(state.root, username) if base in [path, *path.parents]), root)
            arcname = path.relative_to(archive_root)
            try:
                archive.write(path, arcname)
                manifest["included_paths"].append(str(path))
            except OSError as exc:
                manifest["skipped_paths"].append({"path": str(path), "reason": str(exc)})
        for directory in sorted(set(include_dirs)):
            for path in sorted(directory.rglob("*")):
                if path in seen_paths or not path.is_file():
                    continue
                if path == zip_path or package_root in [path, *path.parents]:
                    continue
                try:
                    size = path.stat().st_size
                except OSError as exc:
                    manifest["skipped_paths"].append({"path": str(path), "reason": str(exc)})
                    continue
                if size > 500 * 1024 * 1024:
                    manifest["skipped_paths"].append({"path": str(path), "reason": "larger than 500 MB package limit"})
                    continue
                seen_paths.add(path)
                archive_root = next((base for base in _dashboard_workspace_roots(state.root, username) if base in [path, *path.parents]), root)
                arcname = path.relative_to(archive_root)
                try:
                    archive.write(path, arcname)
                    manifest["included_paths"].append(str(path))
                except OSError as exc:
                    manifest["skipped_paths"].append({"path": str(path), "reason": str(exc)})
        archive.writestr("MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    return {
        "status": "packaged",
        "target_base": target_base,
        "zip_path": str(zip_path),
        "download_filename": zip_path.name,
        "download_url": f"/api/file?path={quote(str(zip_path))}",
        "file_count": len(manifest["included_paths"]),
        "skipped_count": len(manifest["skipped_paths"]),
        "size_bytes": zip_path.stat().st_size,
        "included_report_count": len(selected_rows),
        "local_download_note": "Download is delivered by the browser to the local computer. Choose Desktop if the browser asks for a destination.",
    }


def _delete_orchestration_artifact(state: DashboardState, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    action = str(payload.get("action") or "").strip()
    if action not in {"session", "log", "report"}:
        raise ValueError("action must be session, log, or report")
    progress_json = Path(str(payload.get("progress_json") or "")).expanduser().resolve()
    session_name = str(payload.get("session_name") or "").strip()
    if action == "session":
        if session_name:
            _quit_screen_session(session_name)
        _mark_terminal_progress_stopped(progress_json, "Stopped from dashboard.")
        _remove_terminal_job_for_progress(state, progress_json, session_name)
        return {"status": "stopped", "session_name": session_name, "progress_json": str(progress_json)}
    if action == "log":
        if session_name:
            _quit_screen_session(session_name)
        _remove_terminal_job_for_progress(state, progress_json, session_name)
        try:
            log_dir = _validated_orchestration_log_dir(_dashboard_user_root(state.root, username), progress_json)
        except ValueError:
            log_dir = _validated_orchestration_log_dir(state.root, progress_json)
        if log_dir.exists():
            shutil.rmtree(log_dir)
            return {"status": "deleted", "deleted_path": str(log_dir)}
        return {"status": "not-found", "deleted_path": str(log_dir)}
    progress = _read_json_file(progress_json) if progress_json.exists() else {}
    selections = progress.get("selections") if isinstance(progress, dict) and isinstance(progress.get("selections"), dict) else {}
    report_path = str(payload.get("report_dir") or selections.get("output_dir") or "").strip()
    if not report_path:
        raise ValueError("no report/output directory is recorded for this orchestration")
    return _delete_report(state.root, {"delete_path": report_path})


def _validated_orchestration_log_dir(root: Path, progress_json: Path) -> Path:
    root = root.resolve()
    runs_root = (root / "runs").resolve()
    if not progress_json:
        raise ValueError("progress_json is required")
    if progress_json.name != "progress.json":
        raise ValueError("progress_json must point to an orchestration progress.json")
    log_dir = progress_json.parent.resolve()
    if runs_root not in [log_dir, *log_dir.parents] or not log_dir.name.startswith("terminal-orchestration-"):
        raise ValueError("log deletion is limited to terminal-orchestration folders under the project runs folder")
    return log_dir


def _mark_terminal_progress_stopped(progress_json: Path, reason: str) -> None:
    if not progress_json or not progress_json.exists():
        return
    data = _read_json_file(progress_json)
    if not isinstance(data, dict):
        return
    now = datetime.now(timezone.utc).isoformat()
    data["status"] = "stopped"
    data["stopped_at"] = now
    data["updated_at"] = now
    data["stop_reason"] = reason
    for step in data.get("steps") or []:
        if isinstance(step, dict) and step.get("status") == "running":
            step["status"] = "stopped"
    data.setdefault("events", []).append(
        {"time": now, "step": data.get("current_step", "unknown"), "message": reason, "fields": {}}
    )
    progress_json.write_text(json.dumps(data, indent=2) + "\n")


def _remove_terminal_job_for_progress(state: DashboardState, progress_json: Path, session_name: str = "") -> None:
    target_progress = str(progress_json) if progress_json else ""
    with state.lock:
        job_ids = [
            job_id
            for job_id, job in state.jobs.items()
            if job.kind == "terminal-orchestration"
            and (
                str((job.result or {}).get("progress_json") or "") == target_progress
                or (session_name and str((job.result or {}).get("session_name") or "") == session_name)
            )
        ]
    for job_id in job_ids:
        state._remove_job(job_id)
    jobs_dir = state.root / "runs" / "dashboard-jobs"
    if not jobs_dir.exists():
        return
    for job_path in jobs_dir.glob("*.json"):
        try:
            data = json.loads(job_path.read_text())
        except Exception:
            continue
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        if data.get("kind") == "terminal-orchestration" and (
            str(result.get("progress_json") or "") == target_progress
            or (session_name and str(result.get("session_name") or "") == session_name)
        ):
            try:
                job_path.unlink()
            except FileNotFoundError:
                pass


def _report_delete_dir(root: Path, summary_path: Path) -> Path:
    requested = summary_path.resolve()
    root = root.resolve()
    if root not in [requested, *requested.parents]:
        raise ValueError("summary path must be under the project root")
    if requested.parent.name == "report" and requested.parent.parent != root:
        return requested.parent.parent.resolve()
    return requested.parent.resolve()


def _read_ligand_results(root: Path, query: dict[str, list[str]]) -> dict[str, Any]:
    requested = _project_file(root, query.get("path", [""])[0])
    suffix = requested.suffix.lower()
    if suffix == ".json":
        rows = json.loads(requested.read_text())
    elif suffix == ".csv":
        with requested.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        raise ValueError("ligand results must be a JSON or CSV file")
    if not isinstance(rows, list):
        raise ValueError("ligand results must contain a list of rows")
    return {
        "path": str(requested),
        "count": len(rows),
        "rows": rows[:200],
        "truncated": len(rows) > 200,
    }


def _render_ligand_pose_view(root: Path, query: dict[str, list[str]]) -> dict[str, Any]:
    run_json = _project_file(root, query.get("run_json", [""])[0])
    mode = query.get("mode", ["both"])[0]
    if mode not in {"target", "ligand", "both", "publication"}:
        mode = "both"
    run_data = json.loads(run_json.read_text())
    binding_site_json = _project_file(root, run_data["binding_site_json"])
    site = json.loads(binding_site_json.read_text())
    structure_path = _readable_input_file(root, site["structure_path"], field_name="binding-site structure")
    docked_ligand = _project_file(root, run_data["output_pdbqt"])
    ligand_pdbqt = _readable_input_file(root, run_data["ligand_pdbqt"], field_name="prepared ligand PDBQT") if run_data.get("ligand_pdbqt") else None
    bonded_docked_ligand = _bonded_docked_ligand_sdf(root, docked_ligand)
    viewer_ligand = bonded_docked_ligand or docked_ligand
    interactions = _plip_interactions_for_run(root, run_json, run_data)
    output_html = root.resolve() / "runs" / "dashboard-pose-views" / f"{docked_ligand.stem}-{mode}.html"
    render_binding_site_html(
        structure_path=structure_path,
        binding_site_json=binding_site_json,
        output_html=output_html,
        docked_ligand=viewer_ligand,
        display_mode=mode,
        interactions=interactions,
    )
    ligand_svg = _ligand_2d_svg(ligand_pdbqt) if ligand_pdbqt else ""
    return {
        "visualization_html": str(output_html),
        "ligand": docked_ligand.stem,
        "mode": mode,
        "ligand_svg": ligand_svg,
        "ligand_2d_source": str(_find_prepared_ligand_sdf(ligand_pdbqt)) if ligand_pdbqt and _find_prepared_ligand_sdf(ligand_pdbqt) else "",
        "ligand_3d_source": str(viewer_ligand),
        "ligand_3d_source_type": "bonded-sdf" if bonded_docked_ligand else "pdbqt",
        "plip_interaction_count": len(interactions),
    }


def _render_md_final_frame_view(root: Path, query: dict[str, list[str]]) -> dict[str, Any]:
    """Render 3dmol.js viewer for the MD final frame (cropped receptor + post-MD ligand pose)."""
    import html as _html

    progress_json_raw = query.get("progress_json", [""])[0]
    ligand_name = query.get("ligand", [""])[0]
    if not ligand_name:
        return {"error": "ligand parameter required"}
    if not progress_json_raw:
        return {"error": "progress_json parameter required"}

    progress_json_path = Path(progress_json_raw).resolve()
    allowed = _allowed_report_roots(root)
    def _under_allowed(p: Path) -> bool:
        return any(a in [p, *p.parents] for a in allowed)
    if not _under_allowed(progress_json_path):
        return {"error": "progress_json must be under the project root"}

    try:
        progress = json.loads(progress_json_path.read_text())
    except Exception as exc:
        return {"error": f"Could not read progress JSON: {exc}"}

    ligand_results = progress.get("ligand_results") or {}
    lig_data = ligand_results.get(ligand_name)
    if not lig_data:
        return {"error": f"No results for ligand {ligand_name!r} in progress JSON"}

    sim_record_path_str = lig_data.get("simulation_record") or ""
    if not sim_record_path_str:
        return {"error": "Simulation record path not found in ligand results"}
    sim_record_path = Path(sim_record_path_str).resolve()
    if not _under_allowed(sim_record_path):
        return {"error": "Simulation record must be under the project root"}

    try:
        sim_record = json.loads(sim_record_path.read_text())
    except Exception as exc:
        return {"error": f"Could not read simulation record: {exc}"}

    final_frame_pdb = Path(sim_record.get("final_frame_pdb") or "").resolve()
    if not _under_allowed(final_frame_pdb):
        return {"error": "final_frame.pdb must be under the project root"}
    if not final_frame_pdb.exists():
        return {"error": f"final_frame.pdb not found at {final_frame_pdb}"}

    pdb_data = final_frame_pdb.read_text()
    escaped_name = _html.escape(ligand_name)
    escaped_path = _html.escape(str(final_frame_pdb))
    viewer_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>MD Final Frame \u2014 {escaped_name}</title>
  <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #202124; background: #fff; }}
    #viewer {{ width: 100%; height: 82vh; display: block; }}
    #panel {{ padding: 10px 14px; border-top: 1px solid #ddd; font-size: 13px; line-height: 1.6; }}
    code {{ background: #f1f3f4; padding: 2px 5px; border-radius: 4px; }}
    .swatch {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:middle; }}
  </style>
</head>
<body>
  <div id="viewer"></div>
  <div id="panel">
    <strong>MD Final Frame</strong> &nbsp; Ligand: <code>{escaped_name}</code>
    &nbsp; <span class="swatch" style="background:#5c85d6"></span>Cropped receptor
    &nbsp; <span class="swatch" style="background:#2e7d32"></span>Ligand LIG
    &nbsp; <span style="color:#888">Source: <code>{escaped_path}</code></span>
  </div>
  <script>
    const pdbData = {json.dumps(pdb_data)};
    const viewer = $3Dmol.createViewer("viewer", {{backgroundColor: "white"}});
    viewer.addModel(pdbData, "pdb");

    // Protein = ATOM records (not hetflag). LIG = HETATM resn LIG. Water/ions are HETATM too,
    // so setStyle({{}},{{}}) clears all, then we selectively show protein + LIG only.
    function applyMode(mode) {{
      viewer.removeAllSurfaces();
      viewer.setStyle({{}}, {{}});  // hide everything first (water/ions stay hidden)
      if (mode === "surface") {{
        viewer.setStyle({{not: {{hetflag: true}}}}, {{cartoon: {{color: "spectrum", opacity: 0.15}}}});
        viewer.setStyle({{resn: "LIG"}}, {{stick: {{colorscheme: "greenCarbon", radius: 0.24}}}});
        try {{
          viewer.addSurface($3Dmol.SurfaceType.VDW,
            {{opacity: 0.55, color: "white"}},
            {{not: {{hetflag: true}}}});
        }} catch(e) {{}}
      }} else if (mode === "bubble") {{
        viewer.setStyle({{not: {{hetflag: true}}}}, {{sphere: {{scale: 0.25, colorscheme: "spectrum", opacity: 0.45}}}});
        viewer.setStyle({{resn: "LIG"}}, {{stick: {{colorscheme: "greenCarbon", radius: 0.26}}, sphere: {{scale: 0.4, colorscheme: "greenCarbon", opacity: 0.75}}}});
      }} else {{
        // cartoon (default)
        viewer.setStyle({{not: {{hetflag: true}}}}, {{cartoon: {{color: "spectrum", opacity: 0.9}}}});
        viewer.setStyle({{resn: "LIG"}}, {{stick: {{colorscheme: "greenCarbon", radius: 0.24}}, sphere: {{scale: 0.28, colorscheme: "greenCarbon", opacity: 0.65}}}});
      }}
      viewer.zoomTo({{resn: "LIG"}});
      viewer.render();
    }}

    applyMode("cartoon");

    window.addEventListener("message", event => {{
      if (!event.data || event.data.type !== "oslab-render-mode") return;
      applyMode(event.data.mode || "cartoon");
    }});
  </script>
</body>
</html>
"""

    output_html = root.resolve() / "runs" / "dashboard-pose-views" / f"md-frame-{ligand_name}.html"
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(viewer_html)

    return {
        "visualization_html": str(output_html),
        "ligand": ligand_name,
        "final_frame_pdb": str(final_frame_pdb),
    }


_FEP_EDGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}__[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _is_within(child: Path, parent: Path) -> bool:
    """True iff ``child`` (resolved) is ``parent`` (resolved) or below it."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _fep_original_ligand_2d(
    *,
    root: Path,
    output_dir: Path,
    selections: dict[str, Any],
    fallback_mol: Chem.Mol | None,
    fallback_source: str,
) -> tuple[str, str, str]:
    """Return the original/reference ligand 2D depiction for the FEP overlay panel."""
    name_candidates = [
        str(selections.get("analog_parent") or ""),
        str(selections.get("reference_ligand") or ""),
    ]
    name_candidates = [name for name in name_candidates if name]
    ligand_sdf_raw = selections.get("openfe_input_ligands_sdf") or output_dir / "openfe" / "inputs" / "ligands_bound_frame.sdf"
    ligand_sdf = Path(ligand_sdf_raw).resolve()
    root_resolved = root.resolve()
    if ligand_sdf.exists() and _is_within(ligand_sdf, root_resolved):
        try:
            mols = _load_openfe_ligands_by_original_name(ligand_sdf)
        except Exception:
            mols = {}
        for name in name_candidates:
            mol = mols.get(name)
            if mol is not None:
                return name, _mol_2d_svg(mol), str(ligand_sdf)
    if fallback_mol is not None:
        fallback_name = name_candidates[0] if name_candidates else "Original ligand"
        return fallback_name, _mol_2d_svg(fallback_mol), fallback_source
    return (name_candidates[0] if name_candidates else "Original ligand"), "", ""


def _openfe_fep_overlay_payload(
    *,
    root: Path,
    output_dir: Path,
    selections: dict[str, Any],
    edge_name: str,
    a_name: str,
    b_name: str,
    ddg: float | None,
) -> dict[str, Any] | None:
    ligand_sdf_raw = selections.get("openfe_input_ligands_sdf") or output_dir / "openfe" / "inputs" / "ligands_bound_frame.sdf"
    protein_pdb_raw = selections.get("openfe_input_protein_pdb") or output_dir / "openfe" / "inputs" / "protein.pdb"
    ligand_sdf = Path(ligand_sdf_raw).resolve()
    protein_pdb = Path(protein_pdb_raw).resolve()
    root_resolved = root.resolve()
    if not ligand_sdf.exists():
        return None
    if not _is_within(ligand_sdf, root_resolved):
        return {"error": "OpenFE ligand SDF must be under the project root"}
    if protein_pdb.exists() and not _is_within(protein_pdb, root_resolved):
        return {"error": "OpenFE protein PDB must be under the project root"}

    mols = _load_openfe_ligands_by_original_name(ligand_sdf)
    lig_a = mols.get(a_name)
    lig_b = mols.get(b_name)
    if lig_a is None or lig_b is None:
        available = ", ".join(sorted(mols)[:12])
        return {
            "error": (
                f"OpenFE overlay could not find both edge ligands in {ligand_sdf.name}. "
                f"Needed {a_name} and {b_name}; available: {available}"
            )
        }

    pdb_block_a = Chem.MolToMolBlock(lig_a)
    pdb_block_b = _align_ligand_mol_to_reference(lig_a, lig_b) or Chem.MolToMolBlock(lig_b)
    original_name, original_svg, original_source = _fep_original_ligand_2d(
        root=root,
        output_dir=output_dir,
        selections=selections,
        fallback_mol=lig_a,
        fallback_source=str(ligand_sdf),
    )
    complex_pdb_for_view = protein_pdb.read_text(errors="replace") if protein_pdb.exists() else ""
    coordinate_status = "bound-frame"
    overlay_note = "OpenFE input overlay from bound-frame ligand SDF and protein-only PDB."
    if protein_pdb.exists():
        min_contact = _min_ligand_protein_distance(lig_a, protein_pdb)
        if min_contact is None:
            coordinate_status = "unknown-frame"
            overlay_note = "Could not verify ligand/protein contact distance for this OpenFE input."
        elif min_contact > 8.0:
            coordinate_status = "invalid-frame"
            complex_pdb_for_view = ""
            overlay_note = (
                f"OpenFE input appears out of frame: closest protein-ligand contact is {min_contact:.1f} Å. "
                "Do not interpret this run until the bound ligand pose is repaired."
            )
        else:
            overlay_note = f"OpenFE bound-frame input; closest protein-ligand contact {min_contact:.1f} Å."

    return _write_fep_overlay_payload(
        root=root,
        edge_name=edge_name,
        a_name=a_name,
        b_name=b_name,
        ddg=ddg,
        complex_pdb_for_view=complex_pdb_for_view,
        pdb_block_a=pdb_block_a,
        pdb_block_b=pdb_block_b,
        ligand_a_svg=_mol_2d_svg(lig_a),
        ligand_b_svg=_mol_2d_svg(lig_b),
        ligand_a_source=str(ligand_sdf),
        ligand_b_source=str(ligand_sdf),
        original_ligand_name=original_name,
        original_ligand_svg=original_svg,
        original_ligand_source=original_source,
        overlay_note=overlay_note,
        coordinate_status=coordinate_status,
    )


def _write_fep_overlay_payload(
    *,
    root: Path,
    edge_name: str,
    a_name: str,
    b_name: str,
    ddg: float | None,
    complex_pdb_for_view: str,
    pdb_block_a: str,
    pdb_block_b: str,
    ligand_a_svg: str,
    ligand_b_svg: str,
    ligand_a_source: str,
    ligand_b_source: str,
    original_ligand_name: str,
    original_ligand_svg: str,
    original_ligand_source: str,
    overlay_note: str,
    coordinate_status: str,
) -> dict[str, Any]:
    import html as _html

    ddg_str = f"ΔΔG = {ddg:+.2f} kcal/mol" if ddg is not None else "ΔΔG = n/a"
    escaped_edge = _html.escape(edge_name)
    viewer_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FEP Overlay — {escaped_edge}</title>
  <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #202124; background: #fff; }}
    #viewer {{ width: 100%; height: 82vh; display: block; }}
    #panel {{ padding: 10px 14px; border-top: 1px solid #ddd; font-size: 13px; line-height: 1.6; }}
    .swatch {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:middle; }}
  </style>
</head>
<body>
  <div id="viewer"></div>
  <div id="panel">
    <strong>FEP Edge: {escaped_edge}</strong> &nbsp; {_html.escape(ddg_str)}
    &nbsp; <span class="swatch" style="background:#00897b"></span>Ligand A ({_html.escape(a_name)})
    &nbsp; <span class="swatch" style="background:#e65100"></span>Ligand B ({_html.escape(b_name)})
    {('<span class="swatch" style="background:#5c85d6"></span>Protein') if complex_pdb_for_view else ''}
    {f'<br><span style="color:#8a5a00">{_html.escape(overlay_note)}</span>' if overlay_note else ''}
  </div>
  <script>
    const complexPdb = {json.dumps(complex_pdb_for_view)};
    const ligAData = {json.dumps(pdb_block_a)};
    const ligBData = {json.dumps(pdb_block_b)};
    const viewer = $3Dmol.createViewer("viewer", {{backgroundColor: "white"}});
    let nextModelIndex = 0;
    let complexModelIndex = null;
    let ligAModelIndex = null;
    let ligBModelIndex = null;

    if (complexPdb) {{
      viewer.addModel(complexPdb, "pdb");
      complexModelIndex = nextModelIndex++;
    }}
    if (ligAData) {{
      viewer.addModel(ligAData, "mol");
      ligAModelIndex = nextModelIndex++;
    }}
    if (ligBData) {{
      viewer.addModel(ligBData, "mol");
      ligBModelIndex = nextModelIndex++;
    }}

    let currentRenderMode = "cartoon";
    let currentLigandView = "overlay";

    function applyView(renderMode, ligandView) {{
      viewer.removeAllSurfaces();
      viewer.setStyle({{}}, {{}});
      if (complexModelIndex !== null) {{
        if (renderMode === "surface") {{
          viewer.setStyle({{model: complexModelIndex, not: {{hetflag: true}}}}, {{cartoon: {{color: "spectrum", opacity: 0.12}}}});
          try {{ viewer.addSurface($3Dmol.SurfaceType.VDW, {{opacity: 0.45, color: "white"}}, {{model: complexModelIndex, not: {{hetflag: true}}}}); }} catch(e) {{}}
        }} else if (renderMode === "bubble") {{
          viewer.setStyle({{model: complexModelIndex, not: {{hetflag: true}}}}, {{sphere: {{scale: 0.22, colorscheme: "spectrum", opacity: 0.35}}}});
        }} else {{
          viewer.setStyle({{model: complexModelIndex, not: {{hetflag: true}}}}, {{cartoon: {{color: "spectrum", opacity: 0.85}}}});
        }}
      }}
      const showA = ligandView === "overlay" || ligandView === "a";
      const showB = ligandView === "overlay" || ligandView === "b";
      if (ligAModelIndex !== null && showA) {{
        viewer.setStyle({{model: ligAModelIndex}}, {{stick: {{colorscheme: "cyanCarbon", radius: 0.22}}, sphere: {{scale: 0.3, colorscheme: "cyanCarbon", opacity: 0.6}}}});
      }}
      if (ligBModelIndex !== null && showB) {{
        viewer.setStyle({{model: ligBModelIndex}}, {{stick: {{colorscheme: "orangeCarbon", radius: 0.22}}, sphere: {{scale: 0.3, colorscheme: "orangeCarbon", opacity: 0.6}}}});
      }}
      if (ligandView === "a" && ligAModelIndex !== null) viewer.zoomTo({{model: ligAModelIndex}});
      else if (ligandView === "b" && ligBModelIndex !== null) viewer.zoomTo({{model: ligBModelIndex}});
      else if (ligAModelIndex !== null && ligBModelIndex !== null) viewer.zoomTo({{or: [{{model: ligAModelIndex}}, {{model: ligBModelIndex}}]}});
      else if (ligAModelIndex !== null) viewer.zoomTo({{model: ligAModelIndex}});
      else if (ligBModelIndex !== null) viewer.zoomTo({{model: ligBModelIndex}});
      else if (complexModelIndex !== null) viewer.zoomTo({{model: complexModelIndex}});
      else viewer.zoomTo();
      viewer.render();
    }}
    applyView(currentRenderMode, currentLigandView);
    window.addEventListener("message", event => {{
      if (!event.data) return;
      if (event.data.type === "oslab-render-mode") {{
        currentRenderMode = event.data.mode || "cartoon";
        applyView(currentRenderMode, currentLigandView);
      }}
      if (event.data.type === "oslab-fep-ligand-view") {{
        currentLigandView = event.data.view || "overlay";
        applyView(currentRenderMode, currentLigandView);
      }}
    }});
  </script>
</body>
</html>
"""
    slug = edge_name.replace("/", "_").replace("\\", "_")
    output_html = root.resolve() / "runs" / "dashboard-pose-views" / f"fep-overlay-{slug}.html"
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(viewer_html)
    return {
        "visualization_html": str(output_html),
        "edge": edge_name,
        "ddG_bind_kcal": ddg,
        "ligand_a_name": a_name,
        "ligand_b_name": b_name,
        "ligand_a_svg": ligand_a_svg,
        "ligand_b_svg": ligand_b_svg,
        "ligand_a_2d_source": ligand_a_source,
        "ligand_b_2d_source": ligand_b_source,
        "original_ligand_name": original_ligand_name,
        "original_ligand_svg": original_ligand_svg,
        "original_ligand_2d_source": original_ligand_source,
        "overlay_note": overlay_note,
        "coordinate_status": coordinate_status,
    }


def _render_fep_overlay_view(root: Path, query: dict[str, list[str]]) -> dict[str, Any]:
    """Render 3dmol.js overlay of ligand A + ligand B from an FEP edge."""
    import html as _html

    progress_json_raw = query.get("progress_json", [""])[0]
    edge_name = query.get("edge", [""])[0]
    if not edge_name:
        return {"error": "edge parameter required"}
    if not _FEP_EDGE_NAME_RE.match(edge_name):
        # Reject any name containing path separators, "..", control chars, or
        # not matching the "{ligA}__{ligB}" template. Prevents path traversal.
        return {"error": "Invalid edge name"}
    if not progress_json_raw:
        return {"error": "progress_json parameter required"}

    root_resolved = root.resolve()
    progress_json_path = Path(progress_json_raw).resolve()
    if not _is_within(progress_json_path, root_resolved):
        return {"error": "progress_json must be under the project root"}

    try:
        progress = json.loads(progress_json_path.read_text())
    except Exception as exc:
        return {"error": f"Could not read progress JSON: {exc}"}

    sel = progress.get("selections") or {}
    output_dir = sel.get("output_dir") or ""
    if not output_dir:
        return {"error": "No output_dir found in progress JSON"}

    # The output directory the FEP run wrote to must itself live under root,
    # otherwise a malicious progress.json could redirect file reads.
    output_dir_path = Path(output_dir).resolve()
    if not _is_within(output_dir_path, root_resolved):
        return {"error": "FEP output_dir must be under the project root"}

    a_name, b_name = edge_name.split("__", 1)
    edge_results = (progress.get("edge_results") or {}).get(edge_name, {})
    ddg = edge_results.get("ddG_bind_kcal")
    openfe_payload = _openfe_fep_overlay_payload(
        root=root,
        output_dir=output_dir_path,
        selections=sel,
        edge_name=edge_name,
        a_name=a_name,
        b_name=b_name,
        ddg=ddg,
    )
    if openfe_payload is not None:
        return openfe_payload

    edge_run_dir = (output_dir_path / "edge_runs" / edge_name).resolve()
    edges_dir = (output_dir_path / "edges" / edge_name).resolve()
    if not _is_within(edge_run_dir, output_dir_path) or not _is_within(edges_dir, output_dir_path):
        # Defence in depth: edge_name passed validation above, but re-check
        # after path joining/resolution.
        return {"error": "Edge directory escapes output_dir"}

    complex_pdb_data = ""
    complex_pdb_for_view = ""
    ligand_a_bound_pose = None
    complex_frame_candidates = [
      edges_dir / "receptor_cropped.pdb",
      edge_run_dir / "complex" / "lambda_00" / "final_frame.pdb",
    ]
    complex_frame = next(
      (
        candidate
        for candidate in complex_frame_candidates
        if candidate.exists()
        and (
          _is_within(candidate, edge_run_dir)
          or _is_within(candidate, edges_dir)
        )
      ),
      None,
    )
    if complex_frame is not None:
      complex_pdb_data = complex_frame.read_text()
      complex_pdb_for_view = complex_pdb_data

    lig_a_sdf = edges_dir / "ligandA.sdf"
    lig_b_sdf = edges_dir / "ligandB.sdf"
    ligand_a_mol = _load_first_sdf_mol(lig_a_sdf) if lig_a_sdf.exists() and _is_within(lig_a_sdf, edges_dir) else None
    ligand_b_mol = _load_first_sdf_mol(lig_b_sdf) if lig_b_sdf.exists() and _is_within(lig_b_sdf, edges_dir) else None
    pdb_block_a = ""
    pdb_block_b = ""
    overlay_note = ""
    if complex_pdb_data and complex_frame is not None and lig_a_sdf.exists() and _is_within(lig_a_sdf, edges_dir):
      ligand_a_bound_pose = _ligand_pose_from_complex_frame(lig_a_sdf, complex_frame)
    if ligand_a_bound_pose is not None:
      pdb_block_a = Chem.MolToMolBlock(ligand_a_bound_pose)
      alignment_reference = ligand_a_bound_pose
      coordinate_status = "bound-frame"
    else:
      pdb_block_a = Chem.MolToMolBlock(ligand_a_mol) if ligand_a_mol is not None else ""
      alignment_reference = ligand_a_mol
      coordinate_status = "sdf-only"
      if complex_pdb_data:
        overlay_note = "No bound ligand coordinates were found in the protein frame; using the ligand SDF coordinates."

    if alignment_reference is not None and lig_b_sdf.exists() and _is_within(lig_b_sdf, edges_dir):
      pdb_block_b = _align_ligand_to_bound_pose(alignment_reference, lig_b_sdf)
      if not pdb_block_b and ligand_b_mol is not None:
        pdb_block_b = Chem.MolToMolBlock(ligand_b_mol)
      if not pdb_block_b:
        overlay_note = "Ligand B could not be aligned or loaded; showing ligand A only."
    elif ligand_b_mol is not None:
      pdb_block_b = Chem.MolToMolBlock(ligand_b_mol)

    if complex_frame is not None and alignment_reference is not None:
      min_contact = _min_ligand_protein_distance(alignment_reference, complex_frame)
      if min_contact is not None and min_contact > 8.0:
        coordinate_status = "invalid-frame"
        complex_pdb_for_view = ""
        overlay_note = (
          f"Ligand/receptor coordinates are not in the same bound frame "
          f"(closest protein-ligand contact {min_contact:.1f} Å). "
          "This legacy edge should not be interpreted as an RBFE ΔΔG calculation."
        )
    ligand_a_svg = _sdf_2d_svg(lig_a_sdf) if lig_a_sdf.exists() and _is_within(lig_a_sdf, edges_dir) else ""
    ligand_b_svg = _sdf_2d_svg(lig_b_sdf) if lig_b_sdf.exists() and _is_within(lig_b_sdf, edges_dir) else ""
    original_name, original_svg, original_source = _fep_original_ligand_2d(
        root=root,
        output_dir=output_dir_path,
        selections=sel,
        fallback_mol=ligand_a_mol,
        fallback_source=str(lig_a_sdf) if lig_a_sdf.exists() else "",
    )

    if not complex_pdb_for_view and not (pdb_block_a or pdb_block_b):
        return {"error": f"No usable receptor or ligand coordinates found for edge {edge_name}"}

    ddg_str = f"ΔΔG = {ddg:+.2f} kcal/mol" if ddg is not None else "ΔΔG = n/a"

    escaped_edge = _html.escape(edge_name)
    viewer_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FEP Overlay — {escaped_edge}</title>
  <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; color: #202124; background: #fff; }}
    #viewer {{ width: 100%; height: 82vh; display: block; }}
    #panel {{ padding: 10px 14px; border-top: 1px solid #ddd; font-size: 13px; line-height: 1.6; }}
    code {{ background: #f1f3f4; padding: 2px 5px; border-radius: 4px; }}
    .swatch {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:4px; vertical-align:middle; }}
  </style>
</head>
<body>
  <div id="viewer"></div>
  <div id="panel">
    <strong>FEP Edge: {escaped_edge}</strong> &nbsp; {_html.escape(ddg_str)}
    &nbsp; <span class="swatch" style="background:#00897b"></span>Ligand A ({_html.escape(a_name)})
    &nbsp; <span class="swatch" style="background:#e65100"></span>Ligand B ({_html.escape(b_name)})
    {('<span class="swatch" style="background:#5c85d6"></span>Receptor (bound complex frame)') if complex_pdb_for_view else ''}
    {f'<br><span style="color:#8a5a00">{_html.escape(overlay_note)}</span>' if overlay_note else ''}
  </div>
  <script>
    const complexPdb = {json.dumps(complex_pdb_for_view)};
    const ligAData = {json.dumps(pdb_block_a)};
    const ligBData = {json.dumps(pdb_block_b)};
    const viewer = $3Dmol.createViewer("viewer", {{backgroundColor: "white"}});
    let nextModelIndex = 0;
    let complexModelIndex = null;
    let ligAModelIndex = null;
    let ligBModelIndex = null;

    if (complexPdb) {{
      viewer.addModel(complexPdb, "pdb");
      complexModelIndex = nextModelIndex++;
    }}
    if (ligAData) {{
      viewer.addModel(ligAData, "mol");
      ligAModelIndex = nextModelIndex++;
    }}
    if (ligBData) {{
      viewer.addModel(ligBData, "mol");
      ligBModelIndex = nextModelIndex++;
    }}

    function applyMode(mode) {{
      viewer.removeAllSurfaces();
      viewer.setStyle({{}}, {{}});
      if (complexModelIndex !== null) {{
        if (mode === "surface") {{
          viewer.setStyle({{model: complexModelIndex, not: {{hetflag: true}}}}, {{cartoon: {{color: "spectrum", opacity: 0.12}}}});
          viewer.setStyle({{model: complexModelIndex, resn: "LIG"}}, {{stick: {{colorscheme: "cyanCarbon", radius: 0.22}}, sphere: {{scale: 0.3, colorscheme: "cyanCarbon", opacity: 0.6}}}});
          try {{ viewer.addSurface($3Dmol.SurfaceType.VDW, {{opacity: 0.45, color: "white"}}, {{model: complexModelIndex, not: {{hetflag: true}}}}); }} catch(e) {{}}
        }} else if (mode === "bubble") {{
          viewer.setStyle({{model: complexModelIndex, not: {{hetflag: true}}}}, {{sphere: {{scale: 0.22, colorscheme: "spectrum", opacity: 0.35}}}});
          viewer.setStyle({{model: complexModelIndex, resn: "LIG"}}, {{stick: {{colorscheme: "cyanCarbon", radius: 0.22}}, sphere: {{scale: 0.35, colorscheme: "cyanCarbon", opacity: 0.75}}}});
        }} else {{
          viewer.setStyle({{model: complexModelIndex, not: {{hetflag: true}}}}, {{cartoon: {{color: "spectrum", opacity: 0.85}}}});
          viewer.setStyle({{model: complexModelIndex, resn: "LIG"}}, {{stick: {{colorscheme: "cyanCarbon", radius: 0.22}}, sphere: {{scale: 0.3, colorscheme: "cyanCarbon", opacity: 0.6}}}});
        }}
      }}
      if (ligAModelIndex !== null) {{
        viewer.setStyle({{model: ligAModelIndex}}, {{stick: {{colorscheme: "cyanCarbon", radius: 0.22}}, sphere: {{scale: 0.3, colorscheme: "cyanCarbon", opacity: 0.6}}}});
      }}
      if (ligBModelIndex !== null) {{
        viewer.setStyle({{model: ligBModelIndex}}, {{stick: {{colorscheme: "orangeCarbon", radius: 0.22}}, sphere: {{scale: 0.3, colorscheme: "orangeCarbon", opacity: 0.6}}}});
      }}
      if (ligAModelIndex !== null) {{
        viewer.zoomTo({{model: ligAModelIndex}});
      }} else if (ligBModelIndex !== null) {{
        viewer.zoomTo({{model: ligBModelIndex}});
      }} else if (complexModelIndex !== null) {{
        viewer.zoomTo({{model: complexModelIndex}});
      }} else {{
        viewer.zoomTo();
      }}
      viewer.render();
    }}

    applyMode("cartoon");

    window.addEventListener("message", event => {{
      if (!event.data || event.data.type !== "oslab-render-mode") return;
      applyMode(event.data.mode || "cartoon");
    }});
  </script>
</body>
</html>
"""
    slug = edge_name.replace("/", "_").replace("\\", "_")
    output_html = root.resolve() / "runs" / "dashboard-pose-views" / f"fep-overlay-{slug}.html"
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(viewer_html)

    return {
        "visualization_html": str(output_html),
        "edge": edge_name,
        "ddG_bind_kcal": ddg,
        "ligand_a_name": a_name,
        "ligand_b_name": b_name,
        "ligand_a_svg": ligand_a_svg,
        "ligand_b_svg": ligand_b_svg,
        "ligand_a_2d_source": str(lig_a_sdf) if lig_a_sdf.exists() else "",
        "ligand_b_2d_source": str(lig_b_sdf) if lig_b_sdf.exists() else "",
        "original_ligand_name": original_name,
        "original_ligand_svg": original_svg,
        "original_ligand_2d_source": original_source,
        "overlay_note": overlay_note,
        "coordinate_status": coordinate_status,
    }


def _plip_interactions_for_run(root: Path, run_json: Path, run_data: dict[str, Any]) -> list[dict[str, str]]:
    analysis_path, summary_path = _interaction_files_for_run(root, run_json, run_data)
    rows: list[dict[str, str]] = []
    if summary_path:
        try:
            loaded = json.loads(summary_path.read_text())
            if isinstance(loaded, list):
                rows = [dict(row) for row in loaded if isinstance(row, dict)]
        except Exception:
            rows = []
    if rows and all(row.get("lig_x") and row.get("prot_x") for row in rows):
        return rows
    xml_path = None
    if analysis_path:
        try:
            analysis = json.loads(analysis_path.read_text())
            xml_value = analysis.get("plip_xml") if isinstance(analysis, dict) else ""
            xml_path = _project_file(root, str(xml_value)) if xml_value else None
        except Exception:
            xml_path = None
    if xml_path and xml_path.exists():
        try:
            rows = plip_interaction_rows(xml_path)
        except Exception:
            pass
    return rows


def _interaction_files_for_run(root: Path, run_json: Path, run_data: dict[str, Any]) -> tuple[Path | None, Path | None]:
    output_pdbqt = str(run_data.get("output_pdbqt") or "")
    direct_analysis = run_json.parent / "interaction_analysis.json"
    direct_summary = run_json.parent / "interaction_summary.json"
    if direct_analysis.exists():
        return direct_analysis, _interaction_summary_from_analysis(root, direct_analysis) or (direct_summary if direct_summary.exists() else None)
    if direct_summary.exists():
        return None, direct_summary
    for parent in [run_json.parent, *run_json.parents]:
        interactions_dir = parent / "interactions"
        if not interactions_dir.is_dir():
            continue
        for analysis_json in interactions_dir.glob("**/interaction_analysis.json"):
            try:
                analysis = json.loads(analysis_json.read_text())
            except Exception:
                continue
            if output_pdbqt and str(analysis.get("docked_ligand_pdbqt") or "") != output_pdbqt:
                continue
            return analysis_json, _interaction_summary_from_analysis(root, analysis_json) or analysis_json.with_name("interaction_summary.json")
    return None, None


def _interaction_summary_from_analysis(root: Path, analysis_json: Path) -> Path | None:
    if not analysis_json.exists():
        return None
    try:
        data = json.loads(analysis_json.read_text())
    except Exception:
        return None
    summary = data.get("interaction_json") if isinstance(data, dict) else ""
    if summary:
        try:
            path = _project_file(root, str(summary))
            return path if path.exists() else None
        except Exception:
            return None
    fallback = analysis_json.with_name("interaction_summary.json")
    return fallback if fallback.exists() else None


def _interaction_summary_for_run(root: Path, run_json: Path, run_data: dict[str, Any]) -> Path | None:
    output_pdbqt = str(run_data.get("output_pdbqt") or "")
    direct_candidates = [
        run_json.parent / "interaction_summary.json",
        run_json.parent / "interaction_analysis.json",
    ]
    for candidate in direct_candidates:
        resolved = _interaction_summary_from_candidate(candidate)
        if resolved:
            return resolved
    for parent in [run_json.parent, *run_json.parents]:
        interactions_dir = parent / "interactions"
        if not interactions_dir.is_dir():
            continue
        for analysis_json in interactions_dir.glob("**/interaction_analysis.json"):
            try:
                analysis = json.loads(analysis_json.read_text())
            except Exception:
                continue
            if output_pdbqt and str(analysis.get("docked_ligand_pdbqt") or "") != output_pdbqt:
                continue
            summary = analysis.get("interaction_json")
            if summary:
                summary_path = _project_file(root, str(summary))
                if summary_path.exists():
                    return summary_path
            fallback = analysis_json.with_name("interaction_summary.json")
            if fallback.exists():
                return fallback
    return None


def _interaction_summary_from_candidate(candidate: Path) -> Path | None:
    if not candidate.exists():
        return None
    if candidate.name == "interaction_summary.json":
        return candidate
    try:
        data = json.loads(candidate.read_text())
    except Exception:
        return None
    summary = data.get("interaction_json") if isinstance(data, dict) else ""
    path = Path(str(summary)) if summary else candidate.with_name("interaction_summary.json")
    return path if path.exists() else None


def _bonded_docked_ligand_sdf(root: Path, docked_pdbqt: Path) -> Path | None:
    smiles, mapping, coords = _pdbqt_smiles_mapping_and_coords(docked_pdbqt)
    if not smiles or not mapping or not coords:
        return None
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    conformer = Chem.Conformer(mol.GetNumAtoms())
    assigned = 0
    for smiles_index, pdbqt_serial in mapping.items():
        atom_index = smiles_index - 1
        if atom_index < 0 or atom_index >= mol.GetNumAtoms() or pdbqt_serial not in coords:
            continue
        x, y, z = coords[pdbqt_serial]
        conformer.SetAtomPosition(atom_index, Point3D(x, y, z))
        assigned += 1
    if assigned < max(1, mol.GetNumAtoms() - 1):
        return None
    mol.RemoveAllConformers()
    mol.AddConformer(conformer, assignId=True)
    mol.SetProp("_Name", docked_pdbqt.stem)
    out = root.resolve() / "runs" / "dashboard-pose-views" / f"{docked_pdbqt.stem}-bonded.sdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    writer = Chem.SDWriter(str(out))
    writer.write(mol)
    writer.close()
    return out if out.exists() and out.stat().st_size > 0 else None


def _pdbqt_smiles_mapping_and_coords(docked_pdbqt: Path) -> tuple[str, dict[int, int], dict[int, tuple[float, float, float]]]:
    smiles = ""
    mapping_values: list[int] = []
    coords: dict[int, tuple[float, float, float]] = {}
    in_first_model = True
    for line in docked_pdbqt.read_text().splitlines():
        if line.startswith("MODEL") and not line.startswith("MODEL 1"):
            break
        if line.startswith("ENDMDL"):
            break
        if line.startswith("REMARK SMILES IDX"):
            parts = line.split()[3:]
            mapping_values.extend(int(part) for part in parts if part.isdigit())
            continue
        if line.startswith("REMARK SMILES "):
            smiles = line.split("REMARK SMILES ", 1)[1].strip()
            continue
        if line.startswith(("ATOM", "HETATM")):
            try:
                serial = int(line[6:11])
                coords[serial] = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            except ValueError:
                continue
    mapping = {
        mapping_values[index]: mapping_values[index + 1]
        for index in range(0, len(mapping_values) - 1, 2)
    }
    return smiles, mapping, coords


def _ligand_2d_svg(ligand_pdbqt: Path) -> str:
    sdf = _find_prepared_ligand_sdf(ligand_pdbqt)
    if not sdf:
        return ""
    return _sdf_2d_svg(sdf)


def _sdf_2d_svg(path: Path) -> str:
    supplier = Chem.SDMolSupplier(str(path), removeHs=True)
    mol = next((candidate for candidate in supplier if candidate is not None), None)
    if mol is None:
        return ""
    return _mol_2d_svg(mol)


def _mol_2d_svg(mol: Chem.Mol) -> str:
    mol = Chem.Mol(mol)
    try:
        Chem.SanitizeMol(mol)
    except Exception:
        pass
    try:
        mol = Chem.RemoveHs(mol, sanitize=True)
    except Exception:
        try:
            mol = Chem.RemoveHs(mol, sanitize=False)
        except Exception:
            pass
    rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(250, 220)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText()


def _load_openfe_ligands_by_original_name(path: Path) -> dict[str, Chem.Mol]:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False)
    mols: dict[str, Chem.Mol] = {}
    for mol in supplier:
        if mol is None:
            continue
        safe_name = mol.GetProp("_Name") if mol.HasProp("_Name") else ""
        original_name = mol.GetProp("OSLAB_ORIGINAL_NAME") if mol.HasProp("OSLAB_ORIGINAL_NAME") else safe_name
        if original_name:
            mols[original_name] = mol
        if safe_name:
            mols.setdefault(safe_name, mol)
    return mols


def _min_ligand_protein_distance(ligand: Chem.Mol, protein_pdb: Path) -> float | None:
    """Closest heavy-atom distance between a ligand conformer and protein ATOM records."""
    if ligand.GetNumConformers() == 0:
        return None
    conf = ligand.GetConformer()
    ligand_points: list[tuple[float, float, float]] = []
    for atom in ligand.GetAtoms():
        if atom.GetAtomicNum() <= 1:
            continue
        pos = conf.GetAtomPosition(atom.GetIdx())
        ligand_points.append((float(pos.x), float(pos.y), float(pos.z)))
    protein_points: list[tuple[float, float, float]] = []
    try:
        lines = protein_pdb.read_text(errors="replace").splitlines()
    except Exception:
        return None
    for line in lines:
        if not line.startswith("ATOM"):
            continue
        element = line[76:78].strip()
        atom_name = line[12:16].strip()
        if element == "H" or (not element and atom_name.startswith("H")):
            continue
        try:
            protein_points.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
        except ValueError:
            continue
    if not ligand_points or not protein_points:
        return None
    min_sq: float | None = None
    for lx, ly, lz in ligand_points:
        for px, py, pz in protein_points:
            dsq = (lx - px) ** 2 + (ly - py) ** 2 + (lz - pz) ** 2
            if min_sq is None or dsq < min_sq:
                min_sq = dsq
    return (min_sq ** 0.5) if min_sq is not None else None


def _load_first_sdf_mol(path: Path) -> Chem.Mol | None:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False)
    return next((candidate for candidate in supplier if candidate is not None), None)


def _ligand_pose_from_complex_frame(template_sdf: Path, complex_frame: Path, residue_name: str = "LIG") -> Chem.Mol | None:
    template = _load_first_sdf_mol(template_sdf)
    if template is None:
        return None
    coords: list[Point3D] = []
    for line in complex_frame.read_text().splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        if line[17:20].strip() != residue_name:
            continue
        try:
            coords.append(Point3D(float(line[30:38]), float(line[38:46]), float(line[46:54])))
        except ValueError:
            return None
    if len(coords) != template.GetNumAtoms():
        return None
    posed = Chem.Mol(template)
    posed.RemoveAllConformers()
    conf = Chem.Conformer(posed.GetNumAtoms())
    for atom_index, point in enumerate(coords):
        conf.SetAtomPosition(atom_index, point)
    posed.AddConformer(conf, assignId=True)
    return posed


def _align_ligand_to_bound_pose(bound_ligand: Chem.Mol, ligand_sdf: Path) -> str:
    ligand = _load_first_sdf_mol(ligand_sdf)
    if ligand is None:
        return ""
    return _align_ligand_mol_to_reference(bound_ligand, ligand)


def _align_ligand_mol_to_reference(bound_ligand: Chem.Mol, ligand: Chem.Mol) -> str:
    aligned = Chem.Mol(ligand)
    mcs = rdFMCS.FindMCS(
        [bound_ligand, aligned],
        atomCompare=rdFMCS.AtomCompare.CompareElements,
        bondCompare=rdFMCS.BondCompare.CompareOrder,
        ringMatchesRingOnly=True,
        completeRingsOnly=True,
    )
    if not mcs.smartsString:
        return ""
    pattern = Chem.MolFromSmarts(mcs.smartsString)
    if pattern is None:
        return ""
    bound_match = bound_ligand.GetSubstructMatch(pattern)
    ligand_match = aligned.GetSubstructMatch(pattern)
    if not bound_match or not ligand_match:
        return ""
    rdMolAlign.AlignMol(aligned, bound_ligand, atomMap=list(zip(ligand_match, bound_match)))
    return Chem.MolToMolBlock(aligned)


def _find_prepared_ligand_sdf(ligand_pdbqt: Path) -> Path | None:
    stem = ligand_pdbqt.stem
    prep_dir = ligand_pdbqt.parent.parent
    prepared_dir = prep_dir / "prepared-mols"
    candidates = [prepared_dir / f"{stem}.sdf"]
    candidates.extend(sorted(prepared_dir.glob(f"*_{stem}.sdf")))
    candidates.extend(sorted(prepared_dir.glob(f"*{stem}*.sdf")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _project_file(root: Path, path: str) -> Path:
    raw_abs = Path(path) if Path(path).is_absolute() else (Path.cwd() / path)
    requested = raw_abs.resolve()
    allowed = _allowed_report_roots(root)
    if not any(a in [requested, *requested.parents] for a in allowed):
        raise ValueError("file must be under the project root")
    if not requested.is_file():
        raise FileNotFoundError(requested)
    return requested


def _readable_input_file(root: Path, path: str, *, field_name: str = "input file") -> Path:
    requested = _resolve_readable_input_path(root, path, field_name=field_name)
    if not requested.is_file():
        raise FileNotFoundError(requested)
    return requested


def _dashboard_ligand_sources() -> list[dict[str, Any]]:
    refreshed = datetime.now(timezone.utc).isoformat()
    rows = []
    for row in ligand_source_rows():
        row = dict(row)
        row["metadata_refreshed_at"] = refreshed
        row["live_metadata_note"] = (
            "Library sizes change. This dashboard records the source URL and curated size note; use the provider page for current tranche/download details."
        )
        rows.append(row)
    return rows


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    return value


def _urlopen_json(request_or_url: urllib.request.Request | str) -> dict[str, Any]:
    with urllib.request.urlopen(request_or_url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _safe_urlopen_json(request_or_url: urllib.request.Request | str) -> dict[str, Any] | None:
    try:
        return _urlopen_json(request_or_url)
    except Exception:
        return None


def _entry_resolution(entry: dict[str, Any]) -> float | None:
    values = entry.get("rcsb_entry_info", {}).get("resolution_combined") or []
    return values[0] if values else None


_DASHBOARD_TEMPLATE_PATH = Path(__file__).parent / "templates" / "dashboard.html"
_DASHBOARD_STATIC_DIR = Path(__file__).parent / "static"


def _static_mtime(name: str) -> str:
    try:
        return str(int((_DASHBOARD_STATIC_DIR / name).stat().st_mtime))
    except OSError:
        return "0"


_DEMO_BANNER_HTML = """
  <div class="demo-banner">
    <strong>Demo preview</strong> — public CDK2 enrichment run, read-only.
    <span class="demo-banner-hint">Reports for Blocks 1–4 are in <em>Your runs &amp; results</em> below. The form is pre-filled to show what the run script looks like.</span>
  </div>
""".strip()



def _unredact_for_demo(value):
    """Reverse of _redact_for_demo applied to inbound API parameters.

    The browser receives sanitized state (root / progress_json / etc.) and
    echoes those paths back in subsequent API calls. Translate them back to
    the real workspace paths before they are used for filesystem access.
    Walks dicts/lists recursively.
    """
    if not os.environ.get("OSLAB_DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on"):
        return value
    real_user = "jiyoun"
    fake_user = "oslab-demo"
    real_root = "/data/oslab/users/jiyoun/OSLab-demo"
    fake_root = "/data/oslab/users/oslab-demo/OSLab"
    def _restore(s):
        if not isinstance(s, str):
            return s
        return s.replace(fake_root, real_root).replace(fake_user, real_user)
    def _walk(v):
        if isinstance(v, str):
            return _restore(v)
        if isinstance(v, dict):
            return {k: _walk(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [_walk(x) for x in v]
        return v
    return _walk(value)


def _redact_for_demo(value):
    """Replace the operator's username and personal workspace paths in API
    payloads when OSLAB_DEMO_MODE is set. Operates on dicts/lists recursively.
    The replacement is a bulk substring swap because the operator's username
    ("jiyoun") is unique enough as a token that no legitimate field contains it
    as a substring (PDB IDs, UniProt accessions, gene symbols, domain names
    all avoid lowercase 6-letter alphabetic patterns that match this token)."""
    if not os.environ.get("OSLAB_DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on"):
        return value
    real_user = "jiyoun"
    fake_user = "oslab-demo"
    real_root = "/data/oslab/users/jiyoun/OSLab-demo"
    fake_root = "/data/oslab/users/oslab-demo/OSLab"
    def _scrub_str(s):
        s = s.replace(real_root, fake_root)
        s = s.replace(real_user, fake_user)
        return s
    def _walk(v):
        if isinstance(v, str):
            return _scrub_str(v)
        if isinstance(v, dict):
            return {k: _walk(vv) for k, vv in v.items()}
        if isinstance(v, list):
            return [_walk(x) for x in v]
        return v
    return _walk(value)


def _load_dashboard_html() -> str:
    html = _DASHBOARD_TEMPLATE_PATH.read_text(encoding="utf-8")
    demo_mode = os.environ.get("OSLAB_DEMO_MODE", "").strip().lower() in ("1", "true", "yes", "on")
    banner = _DEMO_BANNER_HTML if demo_mode else ""
    body_class = " class=\"demo-mode\"" if demo_mode else ""
    # Inject file-mtime versions so browser caches invalidate automatically when
    # a static asset changes — users never need to hard-refresh.
    rendered = (
        html.replace("__CSS_VER__", _static_mtime("dashboard.css"))
        .replace("__JS_VER__", _static_mtime("dashboard.js"))
        .replace("__JSV2_VER__", _static_mtime("dashboard_v2.js"))
        .replace("__DEMO_BANNER__", banner)
        .replace("<body>", f"<body{body_class}>")
    )
    if demo_mode:
        # Sanitize personal workspace paths baked into the template (e.g. inside
        # the AI Instructions textarea) so the public demo source view does not
        # leak the operator's username.
        rendered = rendered.replace("/data/oslab/users/jiyoun/OSLab", "/data/oslab/users/oslab-demo/OSLab")
    return rendered
