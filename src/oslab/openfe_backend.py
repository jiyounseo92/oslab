"""Official OpenFE RBFE backend integration for OS Lab."""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .gpu import gpu_assignment_for_task, gpu_env_for_subprocess, gpu_worker_count
from .jobs import DEFAULT_RDKIT_SEED, set_rdkit_seed


ProgressCallback = Callable[[dict[str, Any]], None]


class OpenFEBackendError(RuntimeError):
    """Raised when the OpenFE backend cannot prepare, run, or gather results."""


@dataclass(frozen=True)
class OpenFEBackend:
    openfe_bin: Path
    python_bin: Path
    version: str


@dataclass(frozen=True)
class OpenFEPreparedInputs:
    input_dir: Path
    ligand_sdf: Path
    protein_pdb: Path
    settings_yaml: Path
    manifest_json: Path
    ligand_name_map: dict[str, str]
    original_name_map: dict[str, str]
    coordinate_checks: list[dict[str, Any]]
    protein_summary: dict[str, Any]


@dataclass(frozen=True)
class OpenFEPlan:
    network_dir: Path
    graphml: Path
    alchemical_network_json: Path
    transformations: list[Path]
    network_dict: dict[str, Any]


def find_openfe_backend(repo_root: Path | None = None) -> OpenFEBackend | None:
    """Find the official OpenFE CLI installed for OS Lab."""
    candidates: list[Path] = []
    env_bin = os.environ.get("OSLAB_OPENFE_BIN")
    if env_bin:
        candidates.append(Path(env_bin))
    active_env_candidate = Path(sys.executable).resolve().parent / "openfe"
    candidates.append(active_env_candidate)
    which = shutil.which("openfe")
    if which:
        candidates.append(Path(which))

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            result = subprocess.run(
                [str(candidate), "--version"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=90,
                check=False,
            )
        except Exception:
            continue
        text = (result.stdout or "").strip()
        if result.returncode == 0 and text.startswith("openfe, version"):
            python_bin = candidate.parent / "python"
            if not python_bin.exists():
                python_bin = Path(sys.executable)
            version = text.rsplit(" ", 1)[-1]
            return OpenFEBackend(openfe_bin=candidate.resolve(), python_bin=python_bin.resolve(), version=version)
    return None


def prepare_openfe_inputs(
    *,
    output_dir: Path,
    selected_ligands: list[str],
    ligand_smiles: dict[str, str],
    reference_ligand: str,
    receptor_pdb: str | None,
    md_run: dict[str, Any] | None,
    progress_callback: ProgressCallback | None = None,
) -> OpenFEPreparedInputs:
    """Create a bound-frame multi-SDF and protein-only PDB for OpenFE."""
    input_dir = output_dir / "openfe" / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    ligand_sdf = input_dir / "ligands_bound_frame.sdf"
    protein_pdb = input_dir / "protein.pdb"
    settings_yaml = input_dir / "openfe_settings.yaml"
    manifest_json = input_dir / "input_manifest.json"

    ligand_name_map = _unique_openfe_names(selected_ligands)
    original_name_map = {safe: original for original, safe in ligand_name_map.items()}

    protein_source = _protein_pdb_source(md_run, reference_ligand) or (Path(receptor_pdb) if receptor_pdb else None)
    if not protein_source or not protein_source.exists():
        raise OpenFEBackendError(
            "OpenFE RBFE requires a protein PDB. Complete MD/Optimization first or provide a receptor PDB."
        )
    if progress_callback:
        progress_callback({"message": f"OpenFE input prep: writing protein-only PDB from {protein_source}"})
    _write_protein_only_pdb(protein_source, protein_pdb)
    protein_summary = _protein_input_summary(protein_pdb, protein_source)
    reference_pose = _md_ligand_mol(md_run, reference_ligand)
    if reference_pose is None:
        raise OpenFEBackendError(
            "OpenFE RBFE requires a bound-frame 3D pose for the reference ligand. "
            "Run MD/Optimization or provide a prior docked/optimized ligand pose before starting FEP; "
            "SMILES-only 3D embeddings are not valid complex coordinates."
        )

    mols = _collect_ligand_molecules(
        selected_ligands=selected_ligands,
        ligand_smiles=ligand_smiles,
        reference_ligand=reference_ligand,
        md_run=md_run,
        ligand_name_map=ligand_name_map,
        progress_callback=progress_callback,
    )
    if len(mols) < 2:
        raise OpenFEBackendError("OpenFE RBFE requires at least two valid 3D ligand molecules.")
    if progress_callback:
        progress_callback({"message": f"OpenFE input prep: validating bound-frame coordinates for {len(mols)} ligands"})
    coordinate_checks = _validate_bound_frame_ligands(mols, protein_pdb)
    if progress_callback:
        progress_callback({"message": f"OpenFE input prep: writing bound-frame ligand SDF with {len(mols)} ligands"})
    _write_multimol_sdf(mols, ligand_sdf)

    charge_method = os.environ.get("OSLAB_OPENFE_CHARGE_METHOD", "am1bcc").strip().lower() or "am1bcc"
    if charge_method not in {"am1bcc", "am1bccelf10", "nagl", "espaloma"}:
        charge_method = "am1bcc"
    charge_backend = os.environ.get("OSLAB_OPENFE_CHARGE_BACKEND", "ambertools").strip().lower() or "ambertools"
    if charge_method == "nagl":
        charge_backend = "rdkit"
    if charge_backend not in {"ambertools", "openeye", "rdkit"}:
        charge_backend = "ambertools"
    settings_yaml.write_text(
        "mapper:\n"
        "  method: KartografAtomMapper\n"
        "  settings:\n"
        "    atom_max_distance: 0.95\n"
        "    atom_map_hydrogens: true\n"
        "    map_hydrogens_on_hydrogens_only: true\n"
        "    map_exact_ring_matches_only: true\n"
        "    allow_partial_fused_rings: true\n"
        "    allow_bond_breaks: false\n"
        "network:\n"
        "  method: generate_minimal_spanning_network\n"
        "partial_charge:\n"
        f"  method: {charge_method}\n"
        "  settings:\n"
        f"    off_toolkit_backend: {charge_backend}\n",
        encoding="utf-8",
    )

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "backend": "OpenFE",
        "ligand_sdf": str(ligand_sdf),
        "protein_pdb": str(protein_pdb),
        "settings_yaml": str(settings_yaml),
        "ligand_name_map": ligand_name_map,
        "original_name_map": original_name_map,
        "protein_source": str(protein_source),
        "protein_summary": protein_summary,
        "coordinate_checks": coordinate_checks,
        "partial_charge_method": charge_method,
        "partial_charge_backend": charge_backend,
    }
    manifest_json.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return OpenFEPreparedInputs(
        input_dir=input_dir,
        ligand_sdf=ligand_sdf,
        protein_pdb=protein_pdb,
        settings_yaml=settings_yaml,
        manifest_json=manifest_json,
        ligand_name_map=ligand_name_map,
        original_name_map=original_name_map,
        coordinate_checks=coordinate_checks,
        protein_summary=protein_summary,
    )


def plan_openfe_network(
    *,
    backend: OpenFEBackend,
    repo_root: Path,
    prepared: OpenFEPreparedInputs,
    reference_ligand: str,
    output_dir: Path,
    n_lambda: int,
    n_steps_per_window: int,
    n_equilibration_steps: int,
    temperature_k: float,
    forcefield: str,
    n_protocol_repeats: int = 1,
    n_cores: int = 1,
    progress_callback: ProgressCallback | None = None,
) -> OpenFEPlan:
    """Run the OS Lab OpenFE planner helper and parse its network files."""
    network_dir = output_dir / "openfe" / "network"
    transformations_dir = network_dir / "transformations"
    openmm_platform = _openmm_platform()
    requested_manifest = {
        "backend": "OpenFE",
        "backend_version": backend.version,
        "ligand_sdf": str(prepared.ligand_sdf),
        "protein_pdb": str(prepared.protein_pdb),
        "settings_yaml": str(prepared.settings_yaml),
        "reference_ligand": reference_ligand,
        "n_lambda": n_lambda,
        "n_steps_per_window": n_steps_per_window,
        "n_equilibration_steps": n_equilibration_steps,
        "temperature_k": temperature_k,
        "forcefield": _normalize_openff_forcefield(forcefield),
        "n_protocol_repeats": n_protocol_repeats,
        "openmm_platform": openmm_platform,
    }
    plan_manifest = network_dir / "oslab_openfe_plan_manifest.json"
    transformations = sorted(transformations_dir.glob("*.json")) if transformations_dir.exists() else []
    if transformations and not _manifest_matches(plan_manifest, requested_manifest):
        shutil.rmtree(network_dir, ignore_errors=True)
        transformations = []
    if not transformations:
        runner_script = _openfe_runner_script(repo_root)
        cmd = [
            str(backend.python_bin),
            "-E",
            str(runner_script),
            "plan",
            "--molecules",
            str(prepared.ligand_sdf),
            "--protein",
            str(prepared.protein_pdb),
            "--settings",
            str(prepared.settings_yaml),
            "--output-dir",
            str(network_dir),
            "--n-protocol-repeats",
            str(n_protocol_repeats),
            "--n-cores",
            str(n_cores),
            "--n-lambda",
            str(n_lambda),
            "--n-steps-per-window",
            str(n_steps_per_window),
            "--n-equilibration-steps",
            str(n_equilibration_steps),
            "--temperature-k",
            str(temperature_k),
            "--forcefield",
            _normalize_openff_forcefield(forcefield),
            "--openmm-platform",
            openmm_platform,
        ]
        _run_streamed_command(
            cmd,
            cwd=repo_root,
            log_path=output_dir / "openfe" / "openfe_plan.log",
            progress_callback=progress_callback,
            env_extra=_openfe_env(backend, repo_root),
        )
        transformations = sorted(transformations_dir.glob("*.json"))
        plan_manifest.write_text(json.dumps(requested_manifest, indent=2), encoding="utf-8")

    graphml = network_dir / "ligand_network.graphml"
    alchemical_network_json = network_dir / f"{network_dir.name}.json"
    if not transformations:
        raise OpenFEBackendError(f"OpenFE did not write transformation JSON files in {transformations_dir}")
    safe_reference = prepared.ligand_name_map.get(reference_ligand, reference_ligand)
    network_dict = parse_openfe_ligand_network(
        graphml=graphml,
        reference_ligand=safe_reference,
        original_name_map=prepared.original_name_map,
    )
    _add_ligand_similarity_to_network(network_dict, prepared.ligand_sdf)
    network_dict.update(
        {
            "backend": "OpenFE",
            "backend_version": backend.version,
            "openfe_network_dir": str(network_dir),
            "openfe_graphml": str(graphml),
            "openfe_transformations": [str(p) for p in transformations],
            "n_transformations": len(transformations),
            "openmm_platform": openmm_platform,
        }
    )
    return OpenFEPlan(
        network_dir=network_dir,
        graphml=graphml,
        alchemical_network_json=alchemical_network_json,
        transformations=transformations,
        network_dict=network_dict,
    )


def run_openfe_transformations(
    *,
    backend: OpenFEBackend,
    transformations: list[Path],
    output_dir: Path,
    progress_callback: ProgressCallback | None = None,
    max_minutes_per_transformation: float | None = None,
    gpu_plan: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Run every OpenFE transformation JSON with resume support."""
    if max_minutes_per_transformation is None:
        raw_timeout = os.environ.get("OSLAB_OPENFE_MAX_MINUTES_PER_TRANSFORMATION", "240")
        try:
            max_minutes_per_transformation = float(raw_timeout)
        except (TypeError, ValueError):
            max_minutes_per_transformation = 240.0
    timeout_seconds = (
        int(max_minutes_per_transformation * 60)
        if max_minutes_per_transformation and max_minutes_per_transformation > 0
        else None
    )
    results_dir = output_dir / "openfe" / "results"
    work_dir = output_dir / "openfe" / "work"
    results_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    total = len(transformations)
    callback_lock = threading.Lock()

    def _emit(event: dict[str, Any]) -> None:
        if progress_callback is None:
            return
        with callback_lock:
            progress_callback(event)

    def _run_one(index: int, transformation: Path) -> dict[str, Any]:
        assignment = gpu_assignment_for_task(gpu_plan or {}, index - 1) if gpu_plan else None
        result_json = results_dir / f"{transformation.stem}_results.json"
        if _openfe_result_completed(result_json):
            _emit({"message": f"OpenFE transformation {index}/{total} already completed: {transformation.name}"})
            return {
                "transformation": str(transformation),
                "result_json": str(result_json),
                "status": "skipped-existing",
                "gpu_assignment": assignment or {},
            }
        cmd = [
            str(backend.openfe_bin),
            "quickrun",
            str(transformation),
            "--work-dir",
            str(work_dir / transformation.stem),
            "-o",
            str(result_json),
            "--resume",
        ]
        status = "completed"
        error = ""
        log_path = output_dir / "openfe" / "quickrun_logs" / f"{transformation.stem}.log"
        try:
            gpu_msg = ""
            if assignment and assignment.get("cuda_visible_devices"):
                gpu_msg = (
                    f" on CUDA_VISIBLE_DEVICES={assignment.get('cuda_visible_devices')} "
                    f"({assignment.get('gpu_name') or 'CUDA device'})"
                )
            limit_msg = (
                f" with {max_minutes_per_transformation:g} minute wall-time limit"
                if timeout_seconds
                else ""
            )
            _emit({"message": f"OpenFE transformation {index}/{total} starting{gpu_msg}{limit_msg}: {transformation.name}"})
            env_extra = _openfe_env(backend)
            if gpu_plan is not None:
                env_extra.update(gpu_env_for_subprocess(gpu_plan, assignment))
            _run_streamed_command(
                cmd,
                cwd=output_dir,
                log_path=log_path,
                progress_callback=_emit,
                env_extra=env_extra,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            error = str(exc)
            status = "timed_out" if "timed out" in error.lower() else "failed"
        return {
            "transformation": str(transformation),
            "result_json": str(result_json),
            "status": status,
            "error": error,
            "max_minutes_per_transformation": max_minutes_per_transformation,
            "gpu_assignment": assignment or {},
            "log_path": str(log_path),
        }

    rows_by_index: dict[int, dict[str, Any]] = {}
    max_workers = 1
    if gpu_plan is not None and str(gpu_plan.get("openmm_platform") or "").lower() == "cuda":
        max_workers = min(max(1, total), gpu_worker_count(gpu_plan))
    if max_workers > 1:
        _emit({"message": f"OpenFE quickrun GPU scheduler: running up to {max_workers} transformation(s) concurrently."})
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_run_one, index, transformation): (index, transformation)
                for index, transformation in enumerate(transformations, 1)
            }
            for future in as_completed(futures):
                index, transformation = futures[future]
                try:
                    row = future.result()
                except Exception as exc:
                    row = {
                        "transformation": str(transformation),
                        "result_json": str(results_dir / f"{transformation.stem}_results.json"),
                        "status": "failed",
                        "error": str(exc),
                    }
                rows_by_index[index] = row
                completed += 1
                _emit(
                    {
                        "message": f"OpenFE transformation {index}/{total} {row.get('status')}: {transformation.name}",
                        "completed_transformations": completed,
                        "total_transformations": total,
                    }
                )
    else:
        for index, transformation in enumerate(transformations, 1):
            row = _run_one(index, transformation)
            rows_by_index[index] = row
            _emit(
                {
                    "message": f"OpenFE transformation {index}/{total} {row.get('status')}: {transformation.name}",
                    "completed_transformations": index,
                    "total_transformations": total,
                }
            )
    rows = [rows_by_index[index] for index in range(1, total + 1) if index in rows_by_index]
    legacy_log = output_dir / "openfe" / "openfe_quickrun.log"
    with legacy_log.open("w", encoding="utf-8") as handle:
        handle.write("OpenFE quickrun logs are written per transformation in openfe/quickrun_logs/.\n")
        for row in rows:
            handle.write(f"{Path(str(row.get('transformation', ''))).name}\t{row.get('status')}\t{row.get('log_path', '')}\n")
    (output_dir / "openfe" / "run_records.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows


def gather_openfe_results(
    *,
    backend: OpenFEBackend,
    output_dir: Path,
    original_name_map: dict[str, str],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Gather OpenFE result JSONs into TSV/JSON summaries."""
    openfe_dir = output_dir / "openfe"
    results_dir = openfe_dir / "results"
    ddg_tsv = openfe_dir / "openfe_ddg.tsv"
    raw_tsv = openfe_dir / "openfe_raw.tsv"
    completed_results = [p for p in results_dir.glob("*.json") if _openfe_result_completed(p)]
    if not completed_results:
        raise OpenFEBackendError(
            "No completed OpenFE result JSON files were found. The simulations failed before analysis; "
            "check openfe/openfe_quickrun.log for the first simulation error."
        )
    for report, path in [("ddg", ddg_tsv), ("raw", raw_tsv)]:
        cmd = [
            str(backend.openfe_bin),
            "gather",
            str(results_dir),
            "--report",
            report,
            "--allow-partial",
            "-o",
            str(path),
        ]
        _run_streamed_command(
            cmd,
            cwd=output_dir,
            log_path=openfe_dir / "openfe_gather.log",
            progress_callback=progress_callback,
            env_extra=_openfe_env(backend),
        )

    edge_results = parse_openfe_ddg_tsv(ddg_tsv, original_name_map)
    result = {
        "backend": "OpenFE",
        "ddg_tsv": str(ddg_tsv),
        "raw_tsv": str(raw_tsv),
        "edge_results": edge_results,
    }
    (openfe_dir / "openfe_gathered_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def parse_openfe_ddg_tsv(path: Path, original_name_map: dict[str, str] | None = None) -> list[dict[str, Any]]:
    original_name_map = original_name_map or {}
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            lig_i_safe = row.get("ligand_i", "")
            lig_j_safe = row.get("ligand_j", "")
            lig_i = original_name_map.get(lig_i_safe, lig_i_safe)
            lig_j = original_name_map.get(lig_j_safe, lig_j_safe)
            ddg_raw = row.get("DDG(i->j) (kcal/mol)", "")
            unc_raw = row.get("uncertainty (kcal/mol)", "")
            ddg = _float_or_none(ddg_raw)
            unc = _float_or_none(unc_raw)
            status = "completed" if ddg is not None and unc is not None else "failed"
            rows.append(
                {
                    "ligand_a": lig_i,
                    "ligand_b": lig_j,
                    "ddG_bind_kcal": ddg,
                    "ddG_bind_err_kcal": unc,
                    "status": status,
                    "backend": "OpenFE",
                    "warnings": [] if status == "completed" else [f"OpenFE gather returned {ddg_raw!r}"],
                }
            )
    return rows


def parse_openfe_ligand_network(
    *,
    graphml: Path,
    reference_ligand: str,
    original_name_map: dict[str, str],
) -> dict[str, Any]:
    """Parse OpenFE ligand_network.graphml into the dashboard/report shape."""
    if not graphml.exists():
        return {"ligand_names": list(original_name_map.values()), "reference_ligand": reference_ligand, "edges": []}
    ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
    tree = ET.parse(graphml)
    root = tree.getroot()
    moldict_key = ""
    mapping_key = ""
    for key in root.findall("g:key", ns):
        if key.attrib.get("attr.name") == "moldict":
            moldict_key = key.attrib.get("id", "")
        if key.attrib.get("attr.name") == "mapping":
            mapping_key = key.attrib.get("id", "")
    node_names: dict[str, str] = {}
    for node in root.findall(".//g:node", ns):
        node_id = node.attrib.get("id", "")
        name = node_id
        for data in node.findall("g:data", ns):
            if data.attrib.get("key") == moldict_key and data.text:
                try:
                    moldata = json.loads(data.text)
                    name = str((moldata.get("molprops") or {}).get("ofe-name") or node_id)
                except Exception:
                    name = node_id
        node_names[node_id] = original_name_map.get(name, name)
    edges: list[dict[str, Any]] = []
    for edge in root.findall(".//g:edge", ns):
        source = node_names.get(edge.attrib.get("source", ""), edge.attrib.get("source", ""))
        target = node_names.get(edge.attrib.get("target", ""), edge.attrib.get("target", ""))
        mapping_atoms = 0
        for data in edge.findall("g:data", ns):
            if data.attrib.get("key") == mapping_key and data.text:
                try:
                    mapping_atoms = len(json.loads(data.text))
                except Exception:
                    mapping_atoms = 0
        edges.append({"ligand_a": source, "ligand_b": target, "mcs_atoms": mapping_atoms, "tanimoto": None, "score": None})
    ligand_names = list(dict.fromkeys(node_names.values()))
    ref_original = original_name_map.get(reference_ligand, reference_ligand)
    return {"ligand_names": ligand_names, "reference_ligand": ref_original, "edges": edges}


def _add_ligand_similarity_to_network(network_dict: dict[str, Any], ligand_sdf: Path) -> None:
    """Annotate OpenFE graph edges with RDKit Tanimoto and a readable similarity score."""
    try:
        from rdkit import Chem, DataStructs
        from rdkit.Chem import rdFingerprintGenerator
    except Exception:
        return
    if not ligand_sdf.exists():
        return
    supplier = Chem.SDMolSupplier(str(ligand_sdf), removeHs=False)
    mols: dict[str, Any] = {}
    atom_counts: dict[str, int] = {}
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fps: dict[str, Any] = {}
    for mol in supplier:
        if mol is None:
            continue
        safe_name = mol.GetProp("_Name") if mol.HasProp("_Name") else ""
        original_name = mol.GetProp("OSLAB_ORIGINAL_NAME") if mol.HasProp("OSLAB_ORIGINAL_NAME") else safe_name
        if not original_name:
            continue
        heavy = Chem.RemoveHs(Chem.Mol(mol), sanitize=True)
        try:
            Chem.SanitizeMol(heavy)
        except Exception:
            pass
        mols[original_name] = heavy
        atom_counts[original_name] = heavy.GetNumHeavyAtoms()
        try:
            fps[original_name] = generator.GetFingerprint(heavy)
        except Exception:
            continue
    for edge in network_dict.get("edges", []) or []:
        a = edge.get("ligand_a")
        b = edge.get("ligand_b")
        if a not in fps or b not in fps:
            continue
        try:
            tanimoto = float(DataStructs.TanimotoSimilarity(fps[a], fps[b]))
        except Exception:
            continue
        mapped_atoms = int(edge.get("mcs_atoms") or 0)
        max_atoms = max(atom_counts.get(a, 0), atom_counts.get(b, 0), 1)
        score = 0.5 * tanimoto + 0.5 * min(1.0, mapped_atoms / max_atoms)
        edge["tanimoto"] = round(tanimoto, 3)
        edge["score"] = round(score, 3)
        edge["similarity_score"] = edge["score"]


def _run_streamed_command(
    cmd: list[str],
    *,
    cwd: Path,
    log_path: Path,
    progress_callback: ProgressCallback | None,
    env_extra: dict[str, str] | None,
    timeout_seconds: int | None = None,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if not (
            key == "PYTHONHOME"
            or key == "PYTHONPATH"
            or key.startswith("CONDA_")
            or key.startswith("MAMBA_")
        )
    }
    if env_extra:
        env.update(env_extra)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("$ " + " ".join(cmd) + "\n")
        log.flush()
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            start_new_session=True,
        )
        timed_out = {"value": False}
        kill_timer: threading.Timer | None = None

        def _kill_process_group(sig: int) -> None:
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                return
            except Exception:
                try:
                    proc.send_signal(sig)
                except Exception:
                    pass

        def _timeout_process() -> None:
            nonlocal kill_timer
            timed_out["value"] = True
            log.write(
                f"Command timed out after {timeout_seconds} seconds; sending SIGTERM: "
                + " ".join(cmd)
                + "\n"
            )
            log.flush()
            if progress_callback:
                progress_callback(
                    {
                        "message": (
                            f"OpenFE command timed out after {timeout_seconds} seconds; "
                            "terminating this transformation and continuing with the next one."
                        )
                    }
                )
            _kill_process_group(signal.SIGTERM)
            kill_timer = threading.Timer(60, lambda: _kill_process_group(signal.SIGKILL))
            kill_timer.daemon = True
            kill_timer.start()

        timeout_timer: threading.Timer | None = None
        if timeout_seconds and timeout_seconds > 0:
            timeout_timer = threading.Timer(timeout_seconds, _timeout_process)
            timeout_timer.daemon = True
            timeout_timer.start()
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                log.write(line)
                log.flush()
                text = line.strip()
                if text and progress_callback:
                    progress_callback({"message": text})
            code = proc.wait()
        finally:
            if timeout_timer is not None:
                timeout_timer.cancel()
            if kill_timer is not None:
                kill_timer.cancel()
        if timed_out["value"]:
            minutes = (timeout_seconds or 0) / 60.0
            raise OpenFEBackendError(f"Command timed out after {minutes:.1f} minutes: {' '.join(cmd)}")
        if code != 0:
            raise OpenFEBackendError(f"Command failed with exit code {code}: {' '.join(cmd)}")


def _pythonpath_env(repo_root: Path) -> dict[str, str]:
    src_path = (repo_root / "src").resolve()
    source_checkout = Path.home() / ".open-structure-lab" / "src" / "open-structure-lab" / "src"
    if not src_path.exists() and source_checkout.exists():
        src_path = source_checkout.resolve()
    src = str(src_path)
    # OpenFE runs in its own micromamba env, which may use a different Python
    # version than the dashboard/OSLAB env.  Do not inherit PYTHONPATH from the
    # parent process or the OpenFE interpreter can import another env's stdlib.
    return {"PYTHONPATH": src}


def _openfe_runner_script(repo_root: Path) -> Path:
    source_checkout = Path.home() / ".open-structure-lab" / "src" / "open-structure-lab" / "src" / "oslab" / "openfe_runner.py"
    if source_checkout.exists():
        return source_checkout.resolve()
    candidate = (repo_root / "src" / "oslab" / "openfe_runner.py").resolve()
    if candidate.exists():
        return candidate
    import oslab.openfe_runner as openfe_runner
    return Path(openfe_runner.__file__).resolve()


def _openfe_env(backend: OpenFEBackend, repo_root: Path | None = None) -> dict[str, str]:
    env = {
        "PATH": str(backend.openfe_bin.parent) + os.pathsep + os.environ.get("PATH", ""),
        "PYTHONWARNINGS": "ignore::DeprecationWarning",
    }
    if repo_root is not None:
        env.update(_pythonpath_env(repo_root))
    return env


def _openmm_platform() -> str:
    raw = os.environ.get("OSLAB_OPENMM_PLATFORM", "cpu").strip().lower()
    if raw in {"cpu", "opencl", "cuda", "auto", "fastest", "none"}:
        return raw
    return "cpu"


def _manifest_matches(path: Path, requested: dict[str, Any]) -> bool:
    try:
        existing = json.loads(path.read_text())
    except Exception:
        return False
    return all(existing.get(key) == value for key, value in requested.items())


def _normalize_openff_forcefield(forcefield: str) -> str:
    cleaned = (forcefield or "").strip()
    if cleaned == "openff-2.2.0":
        return "openff-2.2.0"
    if cleaned.startswith("openff-"):
        return cleaned
    return "openff-2.2.1"


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, "", "Error"):
            return None
        return float(value)
    except Exception:
        return None


def _openfe_result_completed(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except Exception:
        return False
    return data.get("estimate") is not None and data.get("uncertainty") is not None


def _unique_openfe_names(names: list[str]) -> dict[str, str]:
    used: set[str] = set()
    result: dict[str, str] = {}
    for index, name in enumerate(names, 1):
        base = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._-") or f"ligand_{index:03d}"
        safe = base[:80]
        suffix = 2
        while safe in used:
            tail = f"_{suffix}"
            safe = base[: 80 - len(tail)] + tail
            suffix += 1
        used.add(safe)
        result[name] = safe
    return result


def _prep_record_for_ligand(md_run: dict[str, Any] | None, ligand_name: str) -> dict[str, Any] | None:
    if not md_run:
        return None
    res = (md_run.get("ligand_results") or {}).get(ligand_name, {})
    for rec_key in ("prep_record", "simulation_record"):
        rec_path = res.get(rec_key)
        if not rec_path:
            continue
        try:
            rec = json.loads(Path(rec_path).read_text())
        except Exception:
            continue
        if isinstance(rec, dict):
            return rec
    return None


def _protein_pdb_source(md_run: dict[str, Any] | None, reference_ligand: str) -> Path | None:
    rec = _prep_record_for_ligand(md_run, reference_ligand)
    if not rec:
        return None
    for key in ("protein_pdb", "cropped_receptor_pdb", "receptor_pdb", "topology_pdb"):
        value = rec.get(key)
        if value and Path(value).exists():
            return Path(value)
    return None


def _write_protein_only_pdb(source: Path, dest: Path) -> None:
    lines: list[str] = []
    for line in source.read_text(errors="replace").splitlines():
        if line.startswith(("ATOM  ", "TER")):
            lines.append(line)
    if not lines:
        for line in source.read_text(errors="replace").splitlines():
            if line.startswith(("ATOM", "HETATM", "TER")) and line[17:20].strip() not in {"LIG", "MOL", "HOH", "WAT"}:
                lines.append(line)
    if not lines:
        raise OpenFEBackendError(f"No protein ATOM records found in {source}")
    lines.append("END")
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _protein_input_summary(protein_pdb: Path, source: Path) -> dict[str, Any]:
    residues: set[tuple[str, int, str]] = set()
    heavy_atoms = 0
    total_atoms = 0
    for line in protein_pdb.read_text(errors="replace").splitlines():
        if not line.startswith("ATOM"):
            continue
        total_atoms += 1
        try:
            residues.add((line[21], int(line[22:26]), line[17:20].strip()))
        except ValueError:
            pass
        element = line[76:78].strip()
        atom_name = line[12:16].strip()
        if element != "H" and not (not element and atom_name.startswith("H")):
            heavy_atoms += 1
    return {
        "protein_source": str(source),
        "protein_pdb": str(protein_pdb),
        "residue_count": len(residues),
        "atom_count": total_atoms,
        "heavy_atom_count": heavy_atoms,
        "source_is_cropped_md_prep": any(part in source.name for part in ("protein", "receptor_cropped")) or "md-optimization" in str(source),
    }


def _validate_bound_frame_ligands(mols: list[Any], protein_pdb: Path, max_min_contact_a: float = 8.0) -> list[dict[str, Any]]:
    """Fail early when ligand and receptor coordinates are clearly in different frames."""
    protein_points = _protein_heavy_atom_points(protein_pdb)
    if not protein_points:
        raise OpenFEBackendError(f"No protein heavy-atom coordinates found in {protein_pdb}")
    checks: list[dict[str, Any]] = []
    invalid: list[str] = []
    for mol in mols:
        name = mol.GetProp("_Name") if mol.HasProp("_Name") else "ligand"
        min_contact = _min_ligand_protein_distance(mol, protein_points)
        row = {
            "ligand": name,
            "min_protein_contact_a": round(min_contact, 3) if min_contact is not None else None,
            "status": "ok" if min_contact is not None and min_contact <= max_min_contact_a else "invalid-frame",
        }
        checks.append(row)
        if row["status"] != "ok":
            invalid.append(f"{name} ({min_contact:.1f} Å)" if min_contact is not None else f"{name} (no coordinates)")
    if invalid:
        raise OpenFEBackendError(
            "OpenFE input coordinate check failed: ligand and protein coordinates are not in the same bound frame. "
            f"Invalid ligands: {', '.join(invalid)}. "
            "Use MD/Optimization/docked ligand poses in the protein coordinate frame before FEP."
        )
    return checks


def _protein_heavy_atom_points(protein_pdb: Path) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    try:
        lines = protein_pdb.read_text(errors="replace").splitlines()
    except Exception:
        return points
    for line in lines:
        if not line.startswith("ATOM"):
            continue
        element = line[76:78].strip()
        atom_name = line[12:16].strip()
        if element == "H" or (not element and atom_name.startswith("H")):
            continue
        try:
            points.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
        except ValueError:
            continue
    return points


def _min_ligand_protein_distance(mol: Any, protein_points: list[tuple[float, float, float]]) -> float | None:
    if mol.GetNumConformers() == 0:
        return None
    conf = mol.GetConformer()
    min_sq: float | None = None
    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() <= 1:
            continue
        pos = conf.GetAtomPosition(atom.GetIdx())
        lx, ly, lz = float(pos.x), float(pos.y), float(pos.z)
        for px, py, pz in protein_points:
            dsq = (lx - px) ** 2 + (ly - py) ** 2 + (lz - pz) ** 2
            if min_sq is None or dsq < min_sq:
                min_sq = dsq
    return (min_sq ** 0.5) if min_sq is not None else None


def _collect_ligand_molecules(
    *,
    selected_ligands: list[str],
    ligand_smiles: dict[str, str],
    reference_ligand: str,
    md_run: dict[str, Any] | None,
    ligand_name_map: dict[str, str],
    progress_callback: ProgressCallback | None = None,
) -> list[Any]:
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdFMCS, rdMolAlign

    template = _md_ligand_mol(md_run, reference_ligand)
    mols: list[Any] = []
    mcs_timeout = max(1, int(os.environ.get("OSLAB_FEP_MCS_TIMEOUT_SECONDS", "8") or 8))
    for index, ligand in enumerate(selected_ligands, 1):
        if progress_callback:
            progress_callback({"message": f"OpenFE input prep: ligand {index}/{len(selected_ligands)} {ligand}"})
        mol = _md_ligand_mol(md_run, ligand)
        if mol is None:
            smiles = ligand_smiles.get(ligand)
            if not smiles:
                if progress_callback:
                    progress_callback({"message": f"OpenFE input prep: skipped {ligand}; no SMILES available"})
                continue
            mol = Chem.MolFromSmiles(smiles)
            if mol is None:
                if progress_callback:
                    progress_callback({"message": f"OpenFE input prep: skipped {ligand}; SMILES parse failed"})
                continue
            mol = Chem.AddHs(mol)
            set_rdkit_seed()
            params = AllChem.ETKDGv3()
            params.randomSeed = DEFAULT_RDKIT_SEED
            embed_status = AllChem.EmbedMolecule(mol, params)
            if embed_status != 0:
                if progress_callback:
                    progress_callback({"message": f"OpenFE input prep: skipped {ligand}; 3D embedding failed"})
                continue
            try:
                AllChem.MMFFOptimizeMolecule(mol)
            except Exception:
                pass
            if template is not None:
                try:
                    if progress_callback:
                        progress_callback({"message": f"OpenFE input prep: aligning {ligand} to reference with MCS timeout {mcs_timeout}s"})
                    mcs = rdFMCS.FindMCS(
                        [template, mol],
                        timeout=mcs_timeout,
                        atomCompare=rdFMCS.AtomCompare.CompareElements,
                        bondCompare=rdFMCS.BondCompare.CompareOrder,
                        ringMatchesRingOnly=True,
                        completeRingsOnly=True,
                    )
                    if getattr(mcs, "canceled", False):
                        if progress_callback:
                            progress_callback({"message": f"OpenFE input prep: skipped {ligand}; MCS alignment timed out"})
                        continue
                    pattern = Chem.MolFromSmarts(mcs.smartsString) if mcs.smartsString else None
                    if pattern is None:
                        if progress_callback:
                            progress_callback({"message": f"OpenFE input prep: skipped {ligand}; no common scaffold found for bound-frame alignment"})
                        continue
                    template_match = template.GetSubstructMatch(pattern)
                    mol_match = mol.GetSubstructMatch(pattern)
                    if not template_match or not mol_match:
                        if progress_callback:
                            progress_callback({"message": f"OpenFE input prep: skipped {ligand}; common scaffold could not be matched"})
                        continue
                    rdMolAlign.AlignMol(mol, template, atomMap=list(zip(mol_match, template_match)))
                except Exception as exc:
                    if progress_callback:
                        progress_callback({"message": f"OpenFE input prep: skipped {ligand}; bound-frame alignment failed: {exc}"})
                    continue
        mol = Chem.Mol(mol)
        mol.SetProp("_Name", ligand_name_map[ligand])
        mol.SetProp("OSLAB_ORIGINAL_NAME", ligand)
        if ligand in ligand_smiles:
            mol.SetProp("SMILES", ligand_smiles[ligand])
        mols.append(mol)
    return mols


def _md_ligand_mol(md_run: dict[str, Any] | None, ligand_name: str):
    from rdkit import Chem

    rec = _prep_record_for_ligand(md_run, ligand_name)
    if not rec:
        return None
    for key in ("ligand_sdf", "docked_ligand_sdf"):
        value = rec.get(key)
        if not value:
            continue
        path = Path(value)
        if not path.exists():
            continue
        supplier = Chem.SDMolSupplier(str(path), removeHs=False)
        mol = next((candidate for candidate in supplier if candidate is not None), None)
        if mol is not None and mol.GetNumConformers() > 0:
            return mol
    return None


def _write_multimol_sdf(mols: list[Any], path: Path) -> None:
    from rdkit import Chem

    writer = Chem.SDWriter(str(path))
    for mol in mols:
        writer.write(mol)
    writer.close()
    if not path.exists() or path.stat().st_size == 0:
        raise OpenFEBackendError(f"Could not write OpenFE ligand SDF: {path}")
