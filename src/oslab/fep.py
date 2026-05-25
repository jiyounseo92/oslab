"""FEP Pipeline Orchestrator — Block 4.

Interactive workflow:
    1. Select a completed MD optimization run
    2. Choose top-N ligands or generate a close analog library
    3. Validate bound-frame protein and ligand coordinates
    4. Plan an official OpenFE relative hybrid-topology RBFE network
    5. Run OpenFE quickrun transformations with resume support
    6. Gather OpenFE ΔΔG values
    7. Generate ranked report

Progress JSON location: root/runs/fep-{session_id}/progress.json
Output dir:            root/reports/fep-{session_id}/
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analog_library import generate_analogs
from .fep_analysis import build_fep_report
from .gpu import resolve_gpu_plan
from .hit_refinement import _ask, _ask_int, _choose_row
from .jobs import campaign_context, job_progress_path, new_job_id, runtime_provenance
from .openfe_backend import (
    OpenFEBackendError,
    find_openfe_backend,
    gather_openfe_results,
    plan_openfe_network,
    prepare_openfe_inputs,
    run_openfe_transformations,
)
from .hpc import export_slurm_fep
from .hpc_terminal import ask_hpc_execution, hpc_config, record_hpc_export


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

_ACTIVE_PROGRESS: dict[str, Any] | None = None
_ACTIVE_PROGRESS_JSON: Path | None = None

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_progress(progress_json: Path, progress: dict[str, Any]) -> None:
    """Atomically write the progress JSON.

    Uses ``write → fsync → rename`` to ensure the dashboard never observes a
    half-written or truncated file even if the process crashes mid-write.
    """
    import os
    progress["updated_at"] = _now()
    progress_json.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(progress, indent=2) + "\n"
    tmp_path = progress_json.with_name(f".{progress_json.name}.tmp.{os.getpid()}")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            # Some filesystems don't support fsync; best-effort.
            pass
    os.replace(tmp_path, progress_json)


def _event(key: str, message: str) -> dict[str, Any]:
    return {"time": _now(), "key": key, "message": message}


def _log(progress: dict[str, Any], key: str, message: str) -> None:
    progress.setdefault("events", []).append(_event(key, message))
    print(message, flush=True)


def _set_active_progress(progress: dict[str, Any], progress_json: Path) -> None:
    global _ACTIVE_PROGRESS, _ACTIVE_PROGRESS_JSON
    _ACTIVE_PROGRESS = progress
    _ACTIVE_PROGRESS_JSON = progress_json


def _record_awaiting_input(
    prompt: str,
    *,
    default: str = "",
    choices: list[tuple[int, str]] | None = None,
) -> None:
    if _ACTIVE_PROGRESS is None or _ACTIVE_PROGRESS_JSON is None:
        return
    _ACTIVE_PROGRESS["awaiting_input"] = {
        "prompt": prompt,
        "default": default,
        "choices": [{"index": index, "label": label} for index, label in (choices or [])],
        "updated_at": _now(),
    }
    _write_progress(_ACTIVE_PROGRESS_JSON, _ACTIVE_PROGRESS)


def _clear_awaiting_input() -> None:
    if _ACTIVE_PROGRESS is None or _ACTIVE_PROGRESS_JSON is None:
        return
    if "awaiting_input" in _ACTIVE_PROGRESS:
        _ACTIVE_PROGRESS.pop("awaiting_input", None)
        _write_progress(_ACTIVE_PROGRESS_JSON, _ACTIVE_PROGRESS)


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    _record_awaiting_input(prompt, default=default)
    value = input(f"{prompt}{suffix}: ").strip()
    _clear_awaiting_input()
    return value or default


def _ask_int(prompt: str, default: int, minimum: int = 1) -> int:
    while True:
        value = _ask(prompt, str(default))
        try:
            parsed = int(value)
        except ValueError:
            print("Enter a number.")
            continue
        if parsed < minimum:
            print(f"Enter a number >= {minimum}.")
            continue
        return parsed


def _choose_row(prompt: str, rows: list[tuple[Any, str]], default: int = 1) -> Any:
    if not rows:
        raise RuntimeError(f"No options available for {prompt}")
    print(f"\n{prompt}")
    choices = []
    for index, (_value, label) in enumerate(rows, start=1):
        marker = " [default]" if index == default else ""
        print(f"  {index}. {label}{marker}")
        choices.append((index, label))
    while True:
        _record_awaiting_input(prompt, default=str(default), choices=choices)
        value = input(f"Select number [{default}]: ").strip() or str(default)
        _clear_awaiting_input()
        try:
            index = int(value)
        except ValueError:
            print("Enter a number.")
            continue
        if 1 <= index <= len(rows):
            return rows[index - 1][0]
        print(f"Enter a number from 1 to {len(rows)}.")


def _mark_current_step_failed(progress: dict[str, Any]) -> None:
    current = progress.get("current_step")
    for step in progress.get("steps", []):
        if step.get("key") == current:
            step["status"] = "failed"
            return


def _set_next_pending_step(progress: dict[str, Any]) -> None:
    for step in progress.get("steps", []):
        if step.get("status") == "pending":
            step["status"] = "running"
            progress["current_step"] = step.get("key", progress.get("current_step"))
            return


def _transformation_stem_for_edge(ligand_a: str, ligand_b: str, leg: str) -> tuple[str, str]:
    return (
        f"rbfe_{ligand_a}_{leg}_{ligand_b}_{leg}",
        f"rbfe_{ligand_b}_{leg}_{ligand_a}_{leg}",
    )


def _record_fep_item_counts(progress: dict[str, Any]) -> None:
    transforms = progress.get("openfe_transformations") or []
    edge_status = progress.get("edge_status") or {}
    progress["total_items"] = len(transforms) or sum(2 for _ in edge_status)
    progress["completed_items"] = len(
        [row for row in transforms if row.get("status") in {"completed", "skipped-existing"}]
    )
    progress["failed_items"] = len([row for row in transforms if row.get("status") in {"failed", "timed_out"}])
    if edge_status:
        completed_edges = [row for row in edge_status.values() if row.get("analysis") == "completed"]
        failed_edges = [row for row in edge_status.values() if row.get("run") == "failed" or row.get("analysis") == "failed"]
        progress["fep_edge_progress"] = {
            "total_edges": len(edge_status),
            "completed_edges": len(completed_edges),
            "failed_edges": len(failed_edges),
        }


def _sync_openfe_edge_status(
    progress: dict[str, Any],
    *,
    run_records: list[dict[str, Any]] | None = None,
    edge_results: list[dict[str, Any]] | None = None,
) -> None:
    """Reconcile OpenFE transformation/result files into edge-level progress.

    OpenFE runs one complex and one solvent Transformation per ligand edge. The
    dashboard should show an edge as completed only after both legs exist and
    gather analysis produced a usable ΔΔG row.
    """
    network_plan = progress.get("network_plan") if isinstance(progress.get("network_plan"), dict) else {}
    edges = network_plan.get("edges") or []
    edge_status = progress.setdefault("edge_status", {})
    transform_status: dict[str, str] = {}
    for row in progress.get("openfe_transformations") or []:
        name = str(row.get("name") or "")
        if name:
            transform_status[name] = str(row.get("status") or "pending")
    for rec in run_records or []:
        stem = Path(str(rec.get("transformation") or "")).stem
        if stem:
            transform_status[stem] = str(rec.get("status") or "unknown")

    result_status: dict[str, str] = {}
    for row in edge_results or []:
        a = str(row.get("ligand_a") or "")
        b = str(row.get("ligand_b") or "")
        if a and b:
            status = str(row.get("status") or "unknown")
            result_status[f"{a}__{b}"] = status
            result_status[f"{b}__{a}"] = status

    for edge in edges:
        a = str(edge.get("ligand_a") or "")
        b = str(edge.get("ligand_b") or "")
        if not a or not b:
            continue
        key = f"{a}__{b}"
        row = edge_status.setdefault(key, {"prep": "completed", "run": "pending", "analysis": "pending"})
        leg_states: dict[str, str] = {}
        for leg in ("complex", "solvent"):
            stems = _transformation_stem_for_edge(a, b, leg)
            statuses = [transform_status.get(stem) for stem in stems if transform_status.get(stem)]
            leg_states[leg] = statuses[0] if statuses else "pending"
            row[f"{leg}_leg"] = leg_states[leg]
        if all(status in {"completed", "skipped-existing"} for status in leg_states.values()):
            row["run"] = "completed"
        elif any(status in {"failed", "timed_out"} for status in leg_states.values()):
            row["run"] = "failed"
        elif any(status in {"completed", "skipped-existing"} for status in leg_states.values()):
            row["run"] = "partial"
        else:
            row["run"] = "pending"
        if key in result_status:
            row["analysis"] = result_status[key]
        elif row["run"] == "failed":
            row["analysis"] = "failed"
        elif row["run"] == "completed":
            row["analysis"] = "pending"
    _record_fep_item_counts(progress)


def _show_openfe_event_in_dashboard(message: str) -> bool:
    """Keep the dashboard event stream readable while preserving full logs on disk."""
    text = message.strip()
    if not text:
        return False
    noisy_prefixes = (
        "INFO:",
        "WARNING:py.warnings:",
        "warnings.warn(",
        "Preset charges applied",
        "Element change in mapping",
        "No mass scaling is attempted",
        "Generating charges:",
    )
    if text.startswith(noisy_prefixes):
        return False
    important_fragments = (
        "OS Lab OpenFE",
        "molecules:",
        "protein:",
        "output:",
        "adjusted ",
        "protocol:",
        "repeats:",
        "lambdas:",
        "OpenMM platform:",
        "forcefield:",
        "charge method:",
        "Assigning ligand partial charges",
        "Planning OpenFE",
        "OpenFE network",
        "Current directory:",
        "Loading transformation",
        "results will be written",
        "Attempting to resume",
        "Starting the simulations",
        "Done with all simulations",
        "Here is the result",
        "Error:",
        "failed",
        "completed",
        "No completed OpenFE",
        "Non-CUDA platform",
    )
    return any(fragment in text for fragment in important_fragments)


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------

def recent_md_optimization_runs(root: Path, limit: int = 10) -> list[dict[str, Any]]:
    """Return recently completed MD optimization runs under root/runs/."""
    runs: list[dict[str, Any]] = []
    for progress_path in sorted(
        (root / "runs").glob("md-optimization-*/progress.json"), reverse=True
    ):
        try:
            data = json.loads(progress_path.read_text())
        except Exception:
            continue
        if data.get("status") != "completed":
            continue
        ligand_results = data.get("ligand_results") or {}
        if not ligand_results:
            continue
        sel = data.get("selections") or {}
        runs.append(
            {
                "name": progress_path.parent.name,
                "progress_json": str(progress_path),
                "output_dir": sel.get("output_dir", ""),
                "created_at": data.get("started_at", ""),
                "ligand_results": ligand_results,
                "selections": sel,
                "ligand_count": len(ligand_results),
                "best_ligand": _best_ligand(ligand_results),
                "best_ddg": _best_ddg(ligand_results),
            }
        )
        if len(runs) >= limit:
            break
    return runs


def _best_ligand(ligand_results: dict[str, Any]) -> str:
    ranked = _ranked_ligands(ligand_results)
    return ranked[0][0] if ranked else ""


def _best_ddg(ligand_results: dict[str, Any]) -> float | None:
    ranked = _ranked_ligands(ligand_results)
    if not ranked:
        return None
    ddg = ranked[0][1]
    return round(float(ddg), 2) if ddg is not None else None


def _ranked_ligands(ligand_results: dict[str, Any]) -> list[tuple[str, float | None]]:
    """Return FEP candidates.

    New MD-gated runs advance only ``pass`` ligands, preserving Block 2 rank
    order.  Legacy MD runs without gate metadata keep the previous MMGBSA sort
    so old completed sessions remain inspectable.
    """
    has_gate_metadata = any(_md_gate_status(res) for res in ligand_results.values() if isinstance(res, dict))
    pairs: list[tuple[str, float | None, int, int]] = []
    for index, (name, res) in enumerate(ligand_results.items(), start=1):
        if not isinstance(res, dict):
            continue
        gate_status = _md_gate_status(res)
        if has_gate_metadata and gate_status != "pass":
            continue
        ddg = res.get("mean_ddg_kcal")
        try:
            ddg_value = float(ddg) if ddg is not None else None
        except (TypeError, ValueError):
            ddg_value = None
        if has_gate_metadata:
            rank_key = _md_block2_rank(res, index)
            pairs.append((name, ddg_value, rank_key, index))
        else:
            rank_key = 0 if ddg_value is not None else 1
            ddg_sort = ddg_value if ddg_value is not None else 0.0
            pairs.append((name, ddg_value, rank_key, int(ddg_sort * 1000)))
    if has_gate_metadata:
        pairs.sort(key=lambda row: (row[2], row[3], row[0]))
    else:
        pairs.sort(key=lambda row: (row[2], row[3], row[0]))
    return [(name, ddg) for name, ddg, _rank, _index in pairs]


def _md_gate_status(md_result: dict[str, Any]) -> str:
    gate = md_result.get("md_gate")
    if isinstance(gate, dict):
        status = gate.get("gate_status") or gate.get("status")
        if status:
            return str(status).strip().lower()
    status = md_result.get("md_gate_status")
    return str(status).strip().lower() if status else ""


def _md_block2_rank(md_result: dict[str, Any], fallback_rank: int) -> int:
    gate = md_result.get("md_gate")
    candidates = []
    if isinstance(gate, dict):
        candidates.extend([gate.get("block2_rank"), gate.get("composite_rank"), gate.get("initial_refinement_rank")])
    candidates.extend([md_result.get("block2_rank"), md_result.get("composite_rank"), md_result.get("initial_refinement_rank")])
    for value in candidates:
        if value is None:
            continue
        try:
            rank = int(float(value))
        except (TypeError, ValueError):
            continue
        if rank > 0:
            return rank
    return fallback_rank


def _md_gate_summary(ligand_results: dict[str, Any]) -> dict[str, int]:
    summary = {"pass": 0, "review": 0, "fail": 0, "unclassified": 0}
    for res in ligand_results.values():
        if not isinstance(res, dict):
            summary["unclassified"] += 1
            continue
        status = _md_gate_status(res)
        if status in summary:
            summary[status] += 1
        else:
            summary["unclassified"] += 1
    return summary


def _ligand_smiles_from_md_run(run: dict[str, Any]) -> dict[str, str]:
    """Extract SMILES for each ligand from prep/simulation records in the MD run."""
    smiles_map: dict[str, str] = {}
    for name, res in (run.get("ligand_results") or {}).items():
        for rec_key in ("prep_record", "simulation_record"):
            rec_path = res.get(rec_key)
            if not rec_path:
                continue
            try:
                rec = json.loads(Path(rec_path).read_text())
                smiles = rec.get("ligand_smiles") or rec.get("smiles") or ""
                if smiles:
                    smiles_map[name] = smiles
                    break
            except Exception:
                pass
    return smiles_map


def _receptor_pdb_from_md_run(run: dict[str, Any], ligand_name: str) -> str | None:
    """Find a cropped receptor PDB for the given ligand from an MD run."""
    res = (run.get("ligand_results") or {}).get(ligand_name, {})
    for rec_key in ("prep_record", "simulation_record"):
        rec_path = res.get(rec_key)
        if not rec_path:
            continue
        try:
            rec = json.loads(Path(rec_path).read_text())
            for pdb_key in ("protein_pdb", "cropped_receptor_pdb", "receptor_pdb", "topology_pdb"):
                p = rec.get(pdb_key)
                if p and Path(p).exists():
                    return p
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Input-mode helpers (MD-pass Block 2 order vs. analog library)
# ---------------------------------------------------------------------------

def _select_topn_ligands(
    *,
    ranked: list[tuple[str, float | None]],
    md_smiles_map: dict[str, str],
    progress: dict[str, Any],
    progress_json: Path,
    preset_top_n: int | None = None,
) -> tuple[list[str], dict[str, str], str]:
    """Top-N mode: pick MD-pass hits in Block 2 rank order and a reference."""
    if not ranked:
        print("ERROR: No MD gate pass ligands are available for FEP.")
        progress["status"] = "failed"
        progress["error"] = "No MD gate pass ligands are available for FEP."
        progress.setdefault("selections", {})["md_gate_filter"] = "pass_only"
        progress["selections"]["fep_ligand_rank_basis"] = "block2_rank_after_md_gate"
        _write_progress(progress_json, progress)
        return [], {}, ""

    print("\nMD-pass ligands ranked by Block 2 order for FEP:")
    for i, (name, ddg) in enumerate(ranked, 1):
        ddg_str = f"{ddg:.2f}" if ddg is not None else "n/a"
        print(f"  {i}. {name}  MMGBSA ΔG annotation = {ddg_str} kcal/mol")

    max_n = len(ranked)
    if max_n < 2:
        print("ERROR: Need at least 2 MD-pass ligands to run top-N FEP.")
        progress["status"] = "failed"
        progress["error"] = "Fewer than 2 MD-pass ligands are available for top-N FEP."
        progress.setdefault("selections", {})["md_gate_filter"] = "pass_only"
        progress["selections"]["fep_ligand_rank_basis"] = "block2_rank_after_md_gate"
        _write_progress(progress_json, progress)
        return [], {}, ""
    default_top_n = preset_top_n if preset_top_n else min(3, max_n)
    top_n = _ask_int(
        f"How many top ligands for FEP (1-{max_n})?",
        default=max(2, min(default_top_n, max_n)),
        minimum=2,
    )
    if top_n > max_n:
        top_n = max_n
    selected = [name for name, _ in ranked[:top_n]]
    print(f"Selected: {', '.join(selected)}")

    smiles_map = dict(md_smiles_map)
    missing = [l for l in selected if l not in smiles_map]
    if missing:
        print(f"\nWARNING: Could not find SMILES for: {', '.join(missing)}")
        print("Enter SMILES manually (or press Enter to skip the ligand):")
        for lig in missing:
            smi = _ask(f"  SMILES for {lig}", default="")
            if smi:
                smiles_map[lig] = smi
    selected = [l for l in selected if l in smiles_map]
    if len(selected) < 2:
        print("ERROR: Need at least 2 ligands with SMILES to run FEP.")
        progress["status"] = "failed"
        progress["error"] = "Fewer than 2 ligands have SMILES."
        _write_progress(progress_json, progress)
        return [], {}, ""

    progress["selections"]["top_n"] = top_n
    progress["selections"]["selected_ligands"] = selected
    progress["selections"]["md_gate_filter"] = "pass_only"
    progress["selections"]["fep_ligand_rank_basis"] = "block2_rank_after_md_gate"
    _log(progress, "select-ligands", f"Selected {len(selected)} ligands: {', '.join(selected)}")
    _write_progress(progress_json, progress)

    reference = _choose_row(
        "Choose the reference ligand for the perturbation network",
        [(name, f"{name}  MMGBSA ΔG annotation = {ddg:.2f}" if ddg is not None else name)
         for name, ddg in ranked if name in selected],
        default=1,
    )
    progress["selections"]["reference_ligand"] = reference
    _log(progress, "select-reference", f"Reference ligand: {reference}")
    _write_progress(progress_json, progress)
    return selected, {k: v for k, v in smiles_map.items() if k in selected}, reference


def _select_analog_library(
    *,
    ranked: list[tuple[str, float | None]],
    md_smiles_map: dict[str, str],
    progress: dict[str, Any],
    progress_json: Path,
    output_dir_root: Path,
    preset_parent: str | None = None,
    preset_n_analogs: int | None = None,
) -> tuple[list[str], dict[str, str], str, dict[str, Any] | None]:
    """Analog-library mode: pick a parent hit, generate ~30 close analogs.

    Returns ``(ligand_names, smiles_map, reference_ligand, analog_library_dict)``.
    The reference is always the parent (analogs are reported relative to it).
    """
    candidates = [(name, ddg) for name, ddg in ranked if name in md_smiles_map]
    if not candidates:
        print("ERROR: No MD-pass ranked ligand has a SMILES on file in the MD run.")
        progress["status"] = "failed"
        progress["error"] = "No SMILES available for any MD-pass ranked ligand."
        progress.setdefault("selections", {})["md_gate_filter"] = "pass_only"
        progress["selections"]["fep_ligand_rank_basis"] = "block2_rank_after_md_gate"
        _write_progress(progress_json, progress)
        return [], {}, "", None

    # If the dashboard pre-selected a parent that is in the candidate list,
    # use that as the default (1-indexed) for _choose_row.
    parent_default = 1
    if preset_parent:
        for idx, (name, _) in enumerate(candidates, 1):
            if name == preset_parent:
                parent_default = idx
                break
    parent_name = _choose_row(
        "Choose the parent hit to build analogs around",
        [(name, f"{name}  MMGBSA ΔG annotation = {ddg:.2f}" if ddg is not None else name)
         for name, ddg in candidates],
        default=parent_default,
    )
    parent_smiles = md_smiles_map[parent_name]

    library_size = _ask_int(
        "Number of analogs to generate (after filtering)",
        default=preset_n_analogs if preset_n_analogs and preset_n_analogs >= 2 else 20,
        minimum=2,
    )
    print(
        f"\nBuilding analog library for {parent_name} (SMILES: {parent_smiles})\n"
        f"  • R-group enumeration via rdMMPA single cuts × ~30 substituents\n"
        f"  • Filters: druglikeness (QED, Lipinski), PAINS/Brenk/NIH alerts,\n"
        f"    Tanimoto 0.5–0.95 to parent, MW 200–500\n"
    )
    library = generate_analogs(
        parent_smiles,
        parent_name=parent_name,
        n_max=library_size,
    )
    if not library.analogs:
        print(
            f"ERROR: 0 analogs survived filtering "
            f"(rejected: {library.rejected_summary}). Loosen filters or pick a "
            "different parent."
        )
        progress["status"] = "failed"
        progress["error"] = "Analog library empty after filtering."
        _write_progress(progress_json, progress)
        return [], {}, "", None

    print(f"\nGenerated {library.n_filtered} analogs (raw: {library.n_raw}; "
          f"rejected by reason: {library.rejected_summary}):\n")
    for a in library.analogs[:20]:
        print(f"  {a.name:<14} {a.substituent_label:<14} "
              f"Tc={a.tanimoto_to_parent:.2f}  MW={a.mw:.0f}  "
              f"QED={a.qed:.2f}  {a.smiles}")
    if library.n_filtered > 20:
        print(f"  ... ({library.n_filtered - 20} more not shown)")

    library_dict = library.to_dict()
    progress["selections"]["input_mode"] = "analog"
    progress["selections"]["analog_parent"] = parent_name
    progress["selections"]["analog_parent_smiles"] = parent_smiles
    progress["selections"]["analog_library_size"] = library.n_filtered
    progress["selections"]["selected_ligands"] = [parent_name] + [a.name for a in library.analogs]
    progress["selections"]["reference_ligand"] = parent_name
    progress["selections"]["md_gate_filter"] = "pass_only"
    progress["selections"]["fep_ligand_rank_basis"] = "block2_rank_after_md_gate"
    progress["analog_library"] = library_dict
    _log(progress, "analog-library",
         f"Generated {library.n_filtered} analogs of {parent_name} "
         f"(raw {library.n_raw}, rejected {sum(library.rejected_summary.values())})")
    _write_progress(progress_json, progress)

    smiles_map = library.smiles_map()
    return list(smiles_map.keys()), smiles_map, parent_name, library_dict


# ---------------------------------------------------------------------------
# Interactive workflow
# ---------------------------------------------------------------------------

def run_interactive_fep(root: Path, progress_json: Path | None = None) -> int:
    """Interactive FEP wizard. Run from a terminal opened by the dashboard."""
    root = root.resolve()
    session_id = new_job_id("fep")
    if not progress_json:
        progress_json = job_progress_path(root, "fep", session_id)
    progress_json = progress_json.resolve()

    # If the dashboard wrote pre-set defaults, pick them up so the form
    # values it sent show up as Enter-to-accept defaults at each prompt.
    dashboard_defaults: dict[str, Any] = {}
    if progress_json.exists():
        try:
            existing = json.loads(progress_json.read_text())
            dashboard_defaults = existing.get("dashboard_defaults") or {}
        except Exception:
            dashboard_defaults = {}

    progress: dict[str, Any] = {
        "started_at": _now(),
        "updated_at": _now(),
        "job_id": session_id,
        **campaign_context(),
        "status": "running",
        "current_step": "select-inputs",
        "session_id": session_id,
        "progress_json": str(progress_json),
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
        "provenance": runtime_provenance(forcefields={"rbfe_backend": "OpenFE"}, structures={}),
        "events": [],
        "notes": ["FEP pipeline. Dashboard monitors this progress JSON."],
    }
    if dashboard_defaults:
        progress["dashboard_defaults"] = dashboard_defaults
    _set_active_progress(progress, progress_json)
    _write_progress(progress_json, progress)

    print("\nFEP — Relative Binding Free Energy\n")
    print("Block 4: Official OpenFE relative hybrid-topology RBFE\n")

    # --- Step 1: Select MD optimization run ---
    md_runs = recent_md_optimization_runs(root, limit=10)
    if not md_runs:
        print("ERROR: No completed MD and Optimization runs found under", root / "runs")
        print("Complete Block 3 first, then return here.")
        progress["status"] = "failed"
        progress["error"] = "No completed MD optimization runs found."
        _write_progress(progress_json, progress)
        return 1

    chosen_run = _choose_row(
        "Choose a completed MD and Optimization run",
        [
            (
                run,
                f"{run['name']} | {run['ligand_count']} ligands | best ΔG {run['best_ddg']} kcal/mol | {run['created_at'][:10] if run['created_at'] else '?'}",
            )
            for run in md_runs
        ],
    )
    progress["selections"]["md_run_name"] = chosen_run["name"]
    progress["selections"]["md_progress_json"] = chosen_run["progress_json"]
    _log(progress, "select-run", f"Selected MD run: {chosen_run['name']}")
    _write_progress(progress_json, progress)

    # --- Step 1.5: Input mode (top-N MMGBSA vs. auto-generated analog library) ---
    print(
        "\nFEP input mode:\n"
        "  • Top-N MD-pass: perturb across MD gate pass hits, preserving Block 2 rank order.\n"
        "    Use when you want to compare diverse leads. Errors are larger when\n"
        "    the hits are not chemically related (Tanimoto < 0.5).\n"
        "  • Analog library: pick one MD-pass parent hit, auto-generate ~30 close analogs\n"
        "    by R-group substitution, then FEP within that scaffold family.\n"
        "    Best for lead optimisation — every edge is high-similarity, so\n"
        "    MBAR overlap is good and ΔΔG errors are small.\n"
    )
    input_mode = _choose_row(
        "Choose FEP input mode",
        [
            ("analog", "Analog library (recommended for lead optimisation)"),
            ("topn",   "Top-N MD-pass hits in Block 2 order (cross-scaffold comparison)"),
        ],
        default=1,
    )
    progress["selections"]["input_mode"] = input_mode
    _log(progress, "select-mode", f"FEP input mode: {input_mode}")
    _write_progress(progress_json, progress)

    ranked = _ranked_ligands(chosen_run["ligand_results"])
    md_smiles_map = _ligand_smiles_from_md_run(chosen_run)

    if input_mode == "analog":
        selected_ligands, smiles_map, reference_ligand, analog_lib_dict = _select_analog_library(
            ranked=ranked,
            md_smiles_map=md_smiles_map,
            progress=progress,
            progress_json=progress_json,
            output_dir_root=root / "reports",
            preset_parent=str(dashboard_defaults.get("analog_parent") or "") or None,
            preset_n_analogs=int(dashboard_defaults.get("n_analogs") or 0) or None,
        )
        if not selected_ligands:
            return 1
    else:
        selected_ligands, smiles_map, reference_ligand = _select_topn_ligands(
            ranked=ranked,
            md_smiles_map=md_smiles_map,
            progress=progress,
            progress_json=progress_json,
            preset_top_n=int(dashboard_defaults.get("top_n") or 0) or None,
        )
        if not selected_ligands:
            return 1
        analog_lib_dict = None

    # --- Step 4: Simulation parameters ---
    print("\nFEP Simulation Parameters")
    n_lambda = _ask_int(
        "Lambda windows per leg",
        default=int(dashboard_defaults.get("n_lambda") or 11),
        minimum=5,
    )
    n_steps = _ask_int(
        "MD steps per lambda window",
        default=int(dashboard_defaults.get("n_steps_per_window") or 25_000),
        minimum=1_000,
    )
    n_equil = _ask_int(
        "Equilibration steps per window",
        default=int(dashboard_defaults.get("n_equilibration_steps") or 5_000),
        minimum=0,
    )
    temperature_k = float(_ask(
        "Temperature (K)",
        default=str(dashboard_defaults.get("temperature_k") or "300"),
    ))

    print("\nForce field options:")
    ff_choices = [
        ("openff-2.2.1", "openff-2.2.1 (OpenFE default Sage) — recommended"),
        ("openff-2.2.0", "openff-2.2.0 (Sage)"),
        ("openff-2.1.0", "openff-2.1.0"),
        ("openff-2.0.0", "openff-2.0.0"),
    ]
    default_forcefield = str(dashboard_defaults.get("forcefield") or "openff-2.2.1")
    ff_default_index = next(
        (idx for idx, (value, _) in enumerate(ff_choices, start=1) if value == default_forcefield),
        1,
    )
    forcefield = _choose_row("SMIRNOFF force field for ligands", ff_choices, default=ff_default_index)
    max_minutes_per_transformation = float(
        _ask(
            "Maximum minutes per OpenFE transformation before marking it timed out",
            default=str(dashboard_defaults.get("max_minutes_per_transformation") or "240"),
        )
    )

    # Receptor PDB: use the one from the reference ligand's MD run
    receptor_pdb = _receptor_pdb_from_md_run(chosen_run, reference_ligand)
    if not receptor_pdb:
        receptor_pdb = _ask("Receptor PDB path (cropped, from MD prep)", default="")
    if receptor_pdb:
        print(f"  Receptor: {receptor_pdb}")
    else:
        print("  WARNING: No receptor PDB found — solvent-only FEP will run (no complex leg).")

    progress["selections"].update(
        {
            "n_lambda_windows": n_lambda,
            "n_steps_per_window": n_steps,
            "n_equilibration_steps": n_equil,
            "temperature_k": temperature_k,
            "forcefield": forcefield,
            "max_minutes_per_transformation": max_minutes_per_transformation,
            "receptor_pdb": receptor_pdb or "",
        }
    )
    _write_progress(progress_json, progress)

    # --- Confirm ---
    print("\nSummary:")
    print(f"  MD run:          {chosen_run['name']}")
    print(f"  Ligands:         {', '.join(selected_ligands)}")
    print(f"  Reference:       {reference_ligand}")
    print(f"  Lambda windows:  {n_lambda}")
    print(f"  Steps/window:    {n_steps:,}")
    print(f"  Temperature:     {temperature_k} K")
    print(f"  Force field:     {forcefield}")
    print(f"  Edge time limit: {max_minutes_per_transformation:g} minutes per transformation")
    if receptor_pdb:
        print(f"  Receptor:        {receptor_pdb}")

    est_ns = (n_steps * n_lambda * 2 * 2e-3 / 1000)  # 2 legs × 2 lig × 2fs per step
    print(f"  Estimated total MD time: ~{est_ns:.1f} ns across all edges")

    confirm = _choose_row(
        "Start FEP pipeline?",
        [("yes", "Yes, run now"), ("no", "Cancel")],
        default=1,
    )
    if confirm != "yes":
        print("Cancelled.")
        progress["status"] = "cancelled"
        _write_progress(progress_json, progress)
        return 0

    # --- Default output dir ---
    default_out = root / "reports" / f"fep-{session_id}"
    output_dir = Path(_ask("Output directory", default=str(dashboard_defaults.get("output_dir") or default_out)))
    output_dir.mkdir(parents=True, exist_ok=True)
    progress["selections"]["output_dir"] = str(output_dir)
    _write_progress(progress_json, progress)

    execution = ask_hpc_execution(
        root=root,
        progress=progress,
        progress_json=progress_json,
        block="fep",
        local_label="This computer/server now",
        default_time="48:00:00",
        default_cpus=4,
        default_gres="gpu:1",
    )
    if execution["backend"] != "local":
        export = export_slurm_fep(
            root=root,
            md_progress_json=Path(chosen_run["progress_json"]),
            output_dir=output_dir,
            top_n=len(selected_ligands),
            n_lambda=n_lambda,
            n_steps_per_window=n_steps,
            n_equilibration_steps=n_equil,
            temperature_k=temperature_k,
            forcefield=forcefield,
            input_mode=str(progress.get("selections", {}).get("input_mode") or "topn"),
            analog_parent=str(progress.get("selections", {}).get("analog_parent") or "") or None,
            n_analogs=int(progress.get("selections", {}).get("analog_library_size") or len(selected_ligands)),
            progress_json=progress_json,
            config=hpc_config(execution, default_job_name="oslab-fep", default_time="48:00:00", default_cpus=4, default_gres="gpu:1"),
        )
        record_hpc_export(progress, progress_json, export, block="fep")
        print("\nCluster export created.")
        print(f"Submit on the cluster with: cd '{export.output_dir}' && sbatch submit.slurm")
        print("The dashboard will show progress/results after the cluster writes files into the shared workspace.")
        return 0

    # Persist the analog library inside the FEP output dir for reproducibility.
    if analog_lib_dict is not None:
        (output_dir / "analog_library.json").write_text(
            json.dumps(analog_lib_dict, indent=2)
        )

    return run_fep_pipeline(
        root=root,
        progress_json=progress_json,
        selected_ligands=selected_ligands,
        ligand_smiles={k: v for k, v in smiles_map.items() if k in selected_ligands},
        reference_ligand=reference_ligand,
        receptor_pdb=receptor_pdb,
        output_dir=output_dir,
        n_lambda=n_lambda,
        n_steps_per_window=n_steps,
        n_equilibration_steps=n_equil,
        temperature_k=temperature_k,
        forcefield=forcefield,
        md_run=chosen_run,
        progress=progress,
        analog_library=analog_lib_dict,
        max_minutes_per_transformation=max_minutes_per_transformation,
    )


# ---------------------------------------------------------------------------
# Main pipeline (called by interactive wizard and by CLI --non-interactive)
# ---------------------------------------------------------------------------

def run_fep_pipeline(
    *,
    root: Path,
    progress_json: Path,
    selected_ligands: list[str],
    ligand_smiles: dict[str, str],
    reference_ligand: str,
    receptor_pdb: str | None,
    output_dir: Path,
    n_lambda: int = 11,
    n_steps_per_window: int = 25_000,
    n_equilibration_steps: int = 5_000,
    temperature_k: float = 300.0,
    forcefield: str = "openff-2.2.1",
    md_run: dict[str, Any] | None = None,
    progress: dict[str, Any] | None = None,
    analog_library: dict[str, Any] | None = None,
    max_minutes_per_transformation: float | None = None,
    gpu_mode: str = "auto",
    gpu_devices: str = "",
    gpu_jobs_per_device: int = 1,
    require_gpu: bool = False,
) -> int:
    """Run the full FEP pipeline and write results. Returns 0 on success."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if progress is not None:
        progress.setdefault("selections", {})["md_gate_filter"] = "pass_only"
        progress["selections"]["fep_ligand_rank_basis"] = "block2_rank_after_md_gate"

    # Make the analog library visible in the progress JSON for the dashboard.
    if progress is not None and analog_library is not None:
        progress["analog_library"] = analog_library
        progress.setdefault("selections", {})["input_mode"] = "analog"
        progress["selections"]["analog_parent"] = analog_library.get("parent_name")
        progress["selections"]["analog_parent_smiles"] = analog_library.get("parent_smiles")
        progress["selections"]["analog_library_size"] = analog_library.get("n_filtered")

    if progress is None:
        progress_json_path = progress_json
        try:
            progress = json.loads(progress_json_path.read_text())
        except Exception:
            progress = {
                "started_at": _now(),
                "updated_at": _now(),
                "job_id": progress_json.parent.name.removeprefix("fep-"),
                **campaign_context(),
                "status": "running",
                "progress_json": str(progress_json),
                "steps": [],
                "edge_status": {},
                "edge_results": {},
                "network_plan": {},
                "ligand_ranking": [],
                "selections": {
                    "selected_ligands": selected_ligands,
                    "reference_ligand": reference_ligand,
                    "n_lambda_windows": n_lambda,
                    "output_dir": str(output_dir),
                },
                "provenance": runtime_provenance(forcefields={"ligand": forcefield, "rbfe_backend": "OpenFE"}, structures={"receptor_pdb": receptor_pdb or ""}),
                "events": [],
            }
    progress.setdefault("job_id", progress_json.parent.name.removeprefix("fep-"))
    progress.update({key: progress.get(key) or value for key, value in campaign_context().items()})
    progress.setdefault("selections", {})["md_gate_filter"] = "pass_only"
    progress["selections"]["fep_ligand_rank_basis"] = "block2_rank_after_md_gate"
    progress.setdefault(
        "provenance",
        runtime_provenance(forcefields={"ligand": forcefield, "rbfe_backend": "OpenFE"}, structures={"receptor_pdb": receptor_pdb or ""}),
    )
    if max_minutes_per_transformation is None:
        raw_limit = os.environ.get("OSLAB_OPENFE_MAX_MINUTES_PER_TRANSFORMATION", "240")
        try:
            max_minutes_per_transformation = float(raw_limit)
        except (TypeError, ValueError):
            max_minutes_per_transformation = 240.0
    if max_minutes_per_transformation is not None and max_minutes_per_transformation <= 0:
        max_minutes_per_transformation = None

    try:
        gpu_plan = resolve_gpu_plan(
            task_count=max(1, len(selected_ligands) - 1),
            task_labels=[f"fep-transform-{i + 1}" for i in range(max(1, len(selected_ligands) - 1))],
            gpu_mode=gpu_mode,
            gpu_devices=gpu_devices,
            jobs_per_device=gpu_jobs_per_device,
            require_gpu=require_gpu,
        )
    except Exception as exc:
        message = f"GPU discovery/assignment failed: {exc}"
        progress["status"] = "failed"
        progress["error"] = message
        _log(progress, "gpu-discovery", message)
        _write_progress(progress_json, progress)
        return 1
    os.environ["OSLAB_OPENMM_PLATFORM"] = str(gpu_plan.get("openmm_platform") or "CPU")
    progress.setdefault("selections", {})["gpu_plan"] = gpu_plan
    if gpu_plan.get("selected_devices"):
        labels = ", ".join(f"{row.get('cuda_visible_devices')} ({row.get('name')})" for row in gpu_plan.get("selected_devices", []))
        _log(progress, "gpu-plan", f"Using CUDA device(s) {labels}; jobs/device={gpu_plan.get('jobs_per_device')}")
    else:
        _log(progress, "gpu-plan", f"Using OpenMM platform {gpu_plan.get('openmm_platform')}")
    for warning in gpu_plan.get("warnings", []):
        _log(progress, "gpu-plan-warning", str(warning))
    _write_progress(progress_json, progress)

    def _step(key: str, status: str) -> None:
        for step in progress.get("steps", []):
            if step["key"] == key:
                step["status"] = status
                break
        else:
            progress.setdefault("steps", []).append({"key": key, "status": status})
        progress["current_step"] = key
        _write_progress(progress_json, progress)

    repo_root = Path(__file__).resolve().parents[2]
    backend = find_openfe_backend(repo_root)
    if backend is None:
        message = (
            "FEP execution is blocked because the official OpenFE backend is not installed or not discoverable. "
            "Install OpenFE in the active environment, put openfe on PATH, or set OSLAB_OPENFE_BIN to the official openfe executable."
        )
        progress["status"] = "failed"
        progress["error"] = message
        progress.setdefault("selections", {})["fep_engine_status"] = "blocked: OpenFE backend not available"
        _log(progress, "fep-blocked", message)
        _step("fep-run", "failed")
        _write_progress(progress_json, progress)
        return 1

    progress.setdefault("selections", {}).update(
        {
            "fep_backend": "OpenFE",
            "fep_backend_version": backend.version,
            "openfe_bin": str(backend.openfe_bin),
            "openfe_python": str(backend.python_bin),
            "openmm_platform": os.environ.get("OSLAB_OPENMM_PLATFORM", "cpu"),
            "max_minutes_per_transformation": max_minutes_per_transformation,
        }
    )
    _write_progress(progress_json, progress)

    def _openfe_cb(evt: dict[str, Any]) -> None:
        message = str(evt.get("message") or "").strip()
        if message:
            print(message, flush=True)
            if _show_openfe_event_in_dashboard(message):
                progress.setdefault("events", []).append(_event("openfe", message[:500]))
                progress["events"] = progress.get("events", [])[-120:]
        if evt.get("completed_transformations") is not None:
            progress["fep_run_progress"] = {
                "completed_transformations": evt.get("completed_transformations"),
                "total_transformations": evt.get("total_transformations"),
            }
        _write_progress(progress_json, progress)

    try:
        # -------------------------------------------------------------------
        # Step: OpenFE input preparation + network planning
        # -------------------------------------------------------------------
        _step("network-planning", "running")
        _log(progress, "openfe-inputs", "Preparing bound-frame ligand SDF and protein PDB for OpenFE")
        prepared = prepare_openfe_inputs(
            output_dir=output_dir,
            selected_ligands=selected_ligands,
            ligand_smiles={k: v for k, v in ligand_smiles.items() if k in selected_ligands},
            reference_ligand=reference_ligand,
            receptor_pdb=receptor_pdb,
            md_run=md_run,
            progress_callback=_openfe_cb,
        )
        progress["selections"].update(
            {
                "openfe_input_ligands_sdf": str(prepared.ligand_sdf),
                "openfe_input_protein_pdb": str(prepared.protein_pdb),
                "openfe_input_manifest": str(prepared.manifest_json),
                "openfe_settings_yaml": str(prepared.settings_yaml),
                "openfe_ligand_name_map": prepared.ligand_name_map,
                "openfe_coordinate_checks": prepared.coordinate_checks,
                "openfe_protein_summary": prepared.protein_summary,
                "openfe_charge_method": (json.loads(prepared.manifest_json.read_text()).get("partial_charge_method") if prepared.manifest_json.exists() else ""),
                "openfe_charge_backend": (json.loads(prepared.manifest_json.read_text()).get("partial_charge_backend") if prepared.manifest_json.exists() else ""),
            }
        )
        protein_summary = prepared.protein_summary
        contact_summary = "; ".join(
            f"{row.get('ligand')}: {row.get('min_protein_contact_a')} Å"
            for row in prepared.coordinate_checks
        )
        _log(
            progress,
            "openfe-frame-check",
            "OpenFE input uses protein source "
            f"{protein_summary.get('protein_source')} "
            f"({protein_summary.get('residue_count')} residues, "
            f"{protein_summary.get('heavy_atom_count')} heavy atoms); "
            f"closest ligand contacts: {contact_summary}",
        )
        _write_progress(progress_json, progress)

        _log(progress, "network", f"Planning official OpenFE RBFE network for {len(selected_ligands)} ligands")
        openfe_plan_cores = max(1, min(int(os.environ.get("OSLAB_OPENFE_PLAN_CORES", "1") or 1), 8))
        progress["selections"]["openfe_plan_cores"] = openfe_plan_cores
        _write_progress(progress_json, progress)
        plan = plan_openfe_network(
            backend=backend,
            repo_root=repo_root,
            prepared=prepared,
            reference_ligand=reference_ligand,
            output_dir=output_dir,
            n_lambda=n_lambda,
            n_steps_per_window=n_steps_per_window,
            n_equilibration_steps=n_equilibration_steps,
            temperature_k=temperature_k,
            forcefield=forcefield,
            n_protocol_repeats=1,
            n_cores=openfe_plan_cores,
            progress_callback=_openfe_cb,
        )
        network_dict = plan.network_dict
        progress["network_plan"] = network_dict
        progress["selections"]["openfe_network_dir"] = str(plan.network_dir)
        progress["selections"]["openfe_graphml"] = str(plan.graphml)
        progress["selections"]["openfe_transformation_count"] = len(plan.transformations)
        progress["selections"]["openmm_platform"] = network_dict.get("openmm_platform", progress["selections"].get("openmm_platform", "cpu"))
        progress["openfe_transformations"] = [
            {"name": p.stem, "path": str(p), "status": "pending"} for p in plan.transformations
        ]
        progress["edge_status"] = {
            f"{edge.get('ligand_a')}__{edge.get('ligand_b')}": {
                "prep": "completed",
                "run": "pending",
                "analysis": "pending",
            }
            for edge in network_dict.get("edges", [])
        }
        _log(progress, "network-done", f"OpenFE network: {len(network_dict.get('edges', []))} ligand edges, {len(plan.transformations)} transformations")
        _record_fep_item_counts(progress)
        progress["next_block_ready"] = False
        _step("network-planning", "completed")

        # OpenFE writes Transformation JSONs during network planning, so this
        # step is complete once those files exist.
        _step("edge-prep", "completed")

        # -------------------------------------------------------------------
        # Step: OpenFE quickrun transformations
        # -------------------------------------------------------------------
        _step("fep-run", "running")
        gpu_plan = resolve_gpu_plan(
            task_count=len(plan.transformations),
            task_labels=[p.stem for p in plan.transformations],
            gpu_mode=gpu_mode,
            gpu_devices=gpu_devices,
            jobs_per_device=gpu_jobs_per_device,
            require_gpu=require_gpu,
        )
        os.environ["OSLAB_OPENMM_PLATFORM"] = str(gpu_plan.get("openmm_platform") or "CPU")
        progress["selections"]["gpu_plan"] = gpu_plan
        _write_progress(progress_json, progress)
        run_records = run_openfe_transformations(
            backend=backend,
            transformations=plan.transformations,
            output_dir=output_dir,
            progress_callback=_openfe_cb,
            max_minutes_per_transformation=max_minutes_per_transformation,
            gpu_plan=gpu_plan,
        )
        progress["openfe_run_records"] = run_records
        for row in progress.get("openfe_transformations", []):
            rec = next((r for r in run_records if Path(str(r.get("transformation", ""))).stem == row.get("name")), None)
            if rec:
                row["status"] = rec.get("status", "unknown")
                row["result_json"] = rec.get("result_json", "")
        _sync_openfe_edge_status(progress, run_records=run_records)
        _write_progress(progress_json, progress)
        failed_runs = [r for r in run_records if r.get("status") in {"failed", "timed_out"}]
        if failed_runs and len(failed_runs) == len(run_records):
            _step("fep-run", "failed")
            report_path, fep_summary = build_fep_report(
                output_dir=output_dir,
                network_plan=network_dict,
                edge_results=[],
                ligand_smiles=ligand_smiles,
                md_results={k: v for k, v in md_run.get("ligand_results", {}).items() if k in selected_ligands} if md_run else None,
                run_status="failed",
                status_note=(
                    "All OpenFE transformations failed before gather/analysis. "
                    "This diagnostic report contains setup and network information only."
                ),
            )
            progress["selections"]["fep_report"] = str(report_path)
            progress["selections"]["fep_results_json"] = str(output_dir / "fep_results.json")
            _write_progress(progress_json, progress)
            raise OpenFEBackendError(
                "All OpenFE transformations failed before analysis. "
                "Most recent error: " + str(failed_runs[-1].get("error") or "see openfe/openfe_quickrun.log")
            )
        _step("fep-run", "completed")

        # -------------------------------------------------------------------
        # Step: OpenFE gather
        # -------------------------------------------------------------------
        _step("analysis", "running")
        try:
            gathered = gather_openfe_results(
                backend=backend,
                output_dir=output_dir,
                original_name_map=prepared.original_name_map,
                progress_callback=_openfe_cb,
            )
        except OpenFEBackendError as exc:
            report_path, fep_summary = build_fep_report(
                output_dir=output_dir,
                network_plan=network_dict,
                edge_results=[],
                ligand_smiles=ligand_smiles,
                md_results={k: v for k, v in md_run.get("ligand_results", {}).items() if k in selected_ligands} if md_run else None,
                run_status="failed",
                status_note=(
                    "OpenFE gather failed before producing usable ΔΔG rows. "
                    "This diagnostic report documents inputs, network setup, and transformation status only."
                ),
            )
            progress["selections"]["fep_report"] = str(report_path)
            progress["selections"]["fep_results_json"] = str(output_dir / "fep_results.json")
            progress["ligand_ranking"] = fep_summary.get("ligand_ranking", [])
            _sync_openfe_edge_status(progress, run_records=run_records, edge_results=[])
            _step("analysis", "failed")
            _write_progress(progress_json, progress)
            raise exc
        all_edge_results = gathered.get("edge_results", [])
        progress["selections"]["openfe_ddg_tsv"] = gathered.get("ddg_tsv", "")
        progress["selections"]["openfe_raw_tsv"] = gathered.get("raw_tsv", "")
        progress["edge_results"] = {
            f"{row.get('ligand_a')}__{row.get('ligand_b')}": {
                "ddG_bind_kcal": row.get("ddG_bind_kcal"),
                "ddG_bind_err_kcal": row.get("ddG_bind_err_kcal"),
                "status": row.get("status"),
                "backend": "OpenFE",
            }
            for row in all_edge_results
        }
        _sync_openfe_edge_status(progress, run_records=run_records, edge_results=all_edge_results)
        completed_rbfe_edges = [
            row for row in all_edge_results
            if row.get("status") == "completed" and row.get("ddG_bind_kcal") is not None
        ]
        if not completed_rbfe_edges:
            report_path, fep_summary = build_fep_report(
                output_dir=output_dir,
                network_plan=network_dict,
                edge_results=all_edge_results,
                ligand_smiles=ligand_smiles,
                md_results={k: v for k, v in md_run.get("ligand_results", {}).items() if k in selected_ligands} if md_run else None,
                run_status="failed",
                status_note=(
                    "OpenFE gather completed but produced no usable ΔΔG edge. "
                    "Do not interpret this run as an RBFE result."
                ),
            )
            progress["selections"]["fep_report"] = str(report_path)
            progress["selections"]["fep_results_json"] = str(output_dir / "fep_results.json")
            progress["ligand_ranking"] = fep_summary.get("ligand_ranking", [])
            _write_progress(progress_json, progress)
            _step("analysis", "failed")
            raise OpenFEBackendError(
                "OpenFE completed no usable RBFE edges after gather; no ΔΔG values were produced. "
                "Check openfe/openfe_quickrun.log and the transformation result folders before interpreting this run."
            )
        _log(progress, "analysis", f"OpenFE gathered {len(all_edge_results)} RBFE edge results")
        _step("analysis", "completed")

        # -------------------------------------------------------------------
        # Step: report
        # -------------------------------------------------------------------
        _step("report", "running")
        md_results: dict[str, Any] | None = None
        if md_run:
            md_results = {k: v for k, v in md_run.get("ligand_results", {}).items() if k in selected_ligands}

        report_path, fep_summary = build_fep_report(
            output_dir=output_dir,
            network_plan=network_dict,
            edge_results=all_edge_results,
            ligand_smiles=ligand_smiles,
            md_results=md_results,
            run_status=(
                "completed"
                if len(completed_rbfe_edges) == len(network_dict.get("edges", []) or completed_rbfe_edges)
                else "partial"
            ),
            status_note=(
                ""
                if len(completed_rbfe_edges) == len(network_dict.get("edges", []) or completed_rbfe_edges)
                else "Only a subset of the planned perturbation edges produced usable ΔΔG values. "
                "Treat rankings as provisional until the full network is complete."
            ),
        )
        progress["selections"]["fep_report"] = str(report_path)
        progress["selections"]["fep_results_json"] = str(output_dir / "fep_results.json")
        progress["ligand_ranking"] = fep_summary.get("ligand_ranking", [])
        _log(progress, "report", f"FEP report written: {report_path}")

        _step("report", "completed")
        progress["status"] = fep_summary.get("status") or "completed"
        progress["next_block_ready"] = progress["status"] == "completed"
        progress["finished_at"] = _now()
        _write_progress(progress_json, progress)

        if progress["status"] == "completed":
            print("\nOpenFE RBFE pipeline completed.")
        else:
            print("\nOpenFE RBFE pipeline produced a partial report; do not interpret missing edges as final ΔΔG results.")
        print(f"Report: {progress['selections'].get('fep_report', '')}")
        print(f"Results JSON: {progress['selections'].get('fep_results_json', '')}")
        return 0 if progress["status"] == "completed" else 2
    except OpenFEBackendError as exc:
        progress["status"] = "failed"
        progress["error"] = str(exc)
        _mark_current_step_failed(progress)
        _log(progress, "openfe-failed", str(exc))
        _write_progress(progress_json, progress)
        return 1
    except Exception as exc:
        progress["status"] = "failed"
        progress["error"] = f"OpenFE pipeline failed: {exc}"
        _mark_current_step_failed(progress)
        _log(progress, "openfe-failed", f"OpenFE pipeline failed: {exc}")
        _write_progress(progress_json, progress)
        return 1
