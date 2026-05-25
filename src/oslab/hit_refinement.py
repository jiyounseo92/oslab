from __future__ import annotations

import csv
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean, pstdev
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .docking import run_vina
from .hpc import export_slurm_hit_refinement
from .hpc_terminal import ask_hpc_execution, hpc_config, record_hpc_export
from .interactions import run_plip_analysis
from .reporting import summarize_vina_runs
from .schemas import DockingResultsSummary, VinaRunOptions


REFINEMENT_STEPS = [
    "select-run",
    "select-hits",
    "parameters",
    "redock",
    "plip",
    "report",
]

HIT_REFINEMENT_NEXT_STEPS_MESSAGE = 'Look for final report in the Reports tab and use the output in "MD and Optimization".'


def refine_hits_from_results(
    results_json: Path,
    output_dir: Path,
    top_n: int = 20,
    exhaustiveness: int = 16,
    num_modes: int = 3,
    cpu: int = 1,
    workers: int = 1,
    seeds: list[int] | None = None,
    run_plip: bool = True,
    plip_top_n: int | None = None,
    progress_json: Path | None = None,
) -> dict[str, Any]:
    """Re-dock top hits from an existing Vina results JSON with higher rigor."""
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    seeds = seeds or [1, 2, 3]
    workers = max(1, int(workers or 1))
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    progress = _new_refinement_progress(output_dir, progress_json, results_json)
    _merge_existing_progress(progress, progress_json)
    _write_progress(progress_json, progress)

    rows = _load_ranked_rows(results_json)
    clustered_input = _has_hit_clustering_metadata(rows)
    selected = _select_preclustered_rows(rows, top_n) if clustered_input else _deduplicate_by_scaffold(rows, top_n)
    if not selected:
        raise ValueError(f"no ligand rows found in {results_json}")
    if plip_top_n is None:
        plip_top_n = min(20, len(selected)) if run_plip else 0
    if plip_top_n < 0:
        raise ValueError("plip_top_n must be 0 or greater")
    plip_top_n = min(plip_top_n, len(selected)) if run_plip else 0
    progress["selections"].update(
        {
            "source_results_json": str(results_json.resolve()),
            "source_run_label": _run_label_from_results(results_json),
            "top_n": top_n,
            "hit_selection_method": "preclustered_input" if clustered_input else "scaffold_deduplication",
            "selected_ligands": [row.get("ligand", "") for row in selected],
        }
    )
    _complete(progress, "select-run", progress_json)
    _complete(progress, "select-hits", progress_json)

    progress["selections"]["refinement_parameters"] = {
        "exhaustiveness": exhaustiveness,
            "num_modes": num_modes,
            "cpu": cpu,
            "workers": workers,
            "seeds": seeds,
        "run_plip": run_plip,
        "plip_top_n": plip_top_n,
        "planned_redocks": len(selected) * len(seeds),
        "planned_plip_runs": plip_top_n,
        "plip_basis": "post-redocking composite ligand ranking",
        "output_dir": str(output_dir),
    }
    _complete(progress, "parameters", progress_json)

    vina_runs: list[Path] = []
    interaction_jsons: list[Path] = []
    total = len(selected) * len(seeds)
    total_plip = plip_top_n if run_plip else 0
    completed = 0
    progress["current_step"] = "redock"
    _write_progress(progress_json, progress)
    tasks: list[dict[str, Any]] = []
    for row in selected:
        ligand_name = str(row.get("ligand") or Path(str(row.get("ligand_pdbqt") or "ligand")).stem)
        binding_site = _binding_site_for_run(row)
        for seed in seeds:
            tasks.append(
                {
                    "row": row,
                    "ligand_name": ligand_name,
                    "seed": seed,
                    "binding_site": binding_site,
                    "run_dir": output_dir / "redocking" / _safe_name(ligand_name) / f"seed-{seed}",
                }
            )
    if workers == 1:
        for task in tasks:
            record_path = _redock_one_refinement_task(task, exhaustiveness=exhaustiveness, num_modes=num_modes, cpu=cpu)
            vina_runs.append(record_path)
            completed += 1
            _update_redock_progress(progress, progress_json, completed, total, total_plip, task, workers)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_task = {
                executor.submit(
                    _redock_one_refinement_task,
                    task,
                    exhaustiveness=exhaustiveness,
                    num_modes=num_modes,
                    cpu=cpu,
                ): task
                for task in tasks
            }
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                record_path = future.result()
                vina_runs.append(record_path)
                completed += 1
                _update_redock_progress(progress, progress_json, completed, total, total_plip, task, workers)

    refinement_report_context = _refinement_report_context(
        results_json=results_json,
        output_dir=output_dir,
        selected=selected,
        seeds=seeds,
        top_n=top_n,
        exhaustiveness=exhaustiveness,
        num_modes=num_modes,
        cpu=cpu,
        workers=workers,
        run_plip=run_plip,
        plip_top_n=plip_top_n,
    )
    summary = summarize_vina_runs(vina_runs, output_dir / "report", report_context=refinement_report_context)
    per_ligand_summary = _write_per_ligand_seed_summary(output_dir, summary, source_rows=selected)
    progress["selections"]["per_ligand_summary_json"] = str(per_ligand_summary["json"])
    progress["selections"]["per_ligand_summary_csv"] = str(per_ligand_summary["csv"])
    progress["selections"]["composite_ranking_json"] = str(per_ligand_summary["json"])
    progress["selections"]["composite_ranking_csv"] = str(per_ligand_summary["csv"])
    _write_progress(progress_json, progress)
    _complete(progress, "redock", progress_json)

    completed_plip = 0
    if run_plip and plip_top_n:
        progress["current_step"] = "plip"
        ranked_ligands = _load_composite_ranking(per_ligand_summary["json"])
        plip_targets = ranked_ligands[:plip_top_n]
        progress["selections"]["plip_ligands"] = [row["ligand"] for row in plip_targets]
        _write_progress(progress_json, progress)
        for ranked in plip_targets:
            ligand_name = str(ranked["ligand"])
            run_json = Path(str(ranked.get("best_run_json") or ""))
            if not run_json.exists():
                continue
            run_data = json.loads(run_json.read_text())
            interaction = run_plip_analysis(
                receptor_pdbqt=Path(str(run_data["receptor_pdbqt"])),
                docked_ligand_pdbqt=Path(str(run_data["output_pdbqt"])),
                output_dir=output_dir / "interactions" / _safe_name(ligand_name) / f"seed-{run_data.get('options', {}).get('seed', 'best')}",
            )
            if interaction.metadata_path:
                interaction_jsons.append(Path(interaction.metadata_path))
            completed_plip += 1
            progress["refinement_progress"] = {
                "completed_redocks": completed,
                "total_redocks": total,
                "completed_plip": completed_plip,
                "total_plip": plip_top_n,
                "progress_percent": 100,
                "current_ligand": ligand_name,
                "phase": "plip",
            }
            _write_progress(progress_json, progress)
    _complete(progress, "plip", progress_json)

    if interaction_jsons:
        summary = summarize_vina_runs(vina_runs, output_dir / "report", interaction_jsons, report_context=refinement_report_context)
        per_ligand_summary = _write_per_ligand_seed_summary(output_dir, summary, source_rows=selected)
    _append_composite_score_section(Path(summary.report_markdown), per_ligand_summary["json"])
    _write_refinement_summary(output_dir, results_json, summary, selected, seeds, plip_top_n, per_ligand_summary)

    _move_ligand_result_table_to_end(Path(summary.report_markdown))
    progress["selections"].update(
        {
            "final_report_markdown": summary.report_markdown,
            "final_results_json": summary.results_json,
            "final_results_csv": summary.results_csv,
            "per_ligand_summary_json": str(per_ligand_summary["json"]),
            "per_ligand_summary_csv": str(per_ligand_summary["csv"]),
        }
    )
    _complete(progress, "report", progress_json)
    progress["status"] = "completed"
    progress["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_progress(progress_json, progress)
    return {
        "status": "completed",
        "output_dir": str(output_dir),
        "summary_json": str(output_dir / "hit_refinement_summary.json"),
        "report_markdown": summary.report_markdown,
        "results_json": summary.results_json,
        "results_csv": summary.results_csv,
        "per_ligand_summary_json": str(per_ligand_summary["json"]),
        "per_ligand_summary_csv": str(per_ligand_summary["csv"]),
        "run_count": summary.run_count,
        "best_ligand": summary.best_ligand,
        "best_score": summary.best_score,
    }


def run_interactive_hit_refinement(root: Path, progress_json: Path | None = None) -> int:
    root = root.resolve()
    progress_json = (progress_json or root / "runs" / "hit-refinement-progress.json").resolve()
    progress = _new_interactive_progress(root, progress_json)
    _write_progress(progress_json, progress)
    runs = recent_docking_runs(root, limit=10)
    if not runs:
        progress["status"] = "failed"
        progress["error"] = "No completed docking reports with ligand results were found."
        _write_progress(progress_json, progress)
        print("No completed docking reports with ligand results were found.")
        return 1
    print("\nHit Refinement")
    print("Choose a completed docking run, then choose how many top ligands to re-dock.\n")
    chosen = _choose_row(
        "Recent docking runs",
        [
            (
                run,
                f"{run['name']} | {run.get('created_at') or 'unknown date'} | best {run.get('best_ligand') or ''} {run.get('best_score') or ''} | {run['results_json']}",
            )
            for run in runs
        ],
    )
    progress["selections"].update(
        {
            "source_run_label": chosen.get("name"),
            "source_results_json": chosen.get("results_json"),
            "source_best_ligand": chosen.get("best_ligand"),
            "source_best_score": chosen.get("best_score"),
            "source_run_count": chosen.get("run_count"),
        }
    )
    progress["current_step"] = "select-hits"
    progress.setdefault("events", []).append(_event("select-run", "Selected docking run for hit refinement."))
    _write_progress(progress_json, progress)
    default_top = min(50, int(chosen.get("run_count") or 20) or 20)
    top_n = _ask_int("Top ligands to refine", default=default_top, minimum=1)
    selected_preview = _deduplicate_by_scaffold(_load_ranked_rows(Path(chosen["results_json"])), top_n)
    if len(selected_preview) < top_n:
        print(f"Scaffold diversity filter selected {len(selected_preview)} ligands from the requested top {top_n}.")
    progress["selections"].update(
        {
            "top_n": top_n,
            "deduplicated_top_n": len(selected_preview),
            "selected_ligands": [row.get("ligand", "") for row in selected_preview],
        }
    )
    progress["current_step"] = "parameters"
    progress.setdefault("events", []).append(_event("select-hits", f"Selected top {top_n} ligands to refine."))
    _write_progress(progress_json, progress)
    exhaustiveness = _ask_int("Vina exhaustiveness for refinement", default=16, minimum=1)
    if exhaustiveness < 16:
        print("Warning: exhaustiveness < 16 gives limited improvement over the initial screen. Consider 16-32 for meaningful hit refinement.")
    if exhaustiveness < 8:
        print("At exhaustiveness < 8, re-docking results are unlikely to be more reliable than the original screen.")
    progress["selections"].setdefault("refinement_parameters", {})["exhaustiveness"] = exhaustiveness
    _write_progress(progress_json, progress)
    num_modes = _ask_int("Vina output poses per ligand", default=3, minimum=1)
    progress["selections"].setdefault("refinement_parameters", {})["num_modes"] = num_modes
    _write_progress(progress_json, progress)
    seeds = _ask_seed_list("Seeds, comma-separated", default="1,2,3")
    progress["selections"].setdefault("refinement_parameters", {})["seeds"] = seeds
    _write_progress(progress_json, progress)
    default_workers = max(1, min(8, os.cpu_count() or 1))
    workers = _ask_int("Parallel Vina jobs for hit refinement", default=default_workers, minimum=1)
    progress["selections"].setdefault("refinement_parameters", {})["workers"] = workers
    _write_progress(progress_json, progress)
    run_plip = (
        _choose(
            "After redocking and composite re-ranking, run Protein-Ligand Interaction Profiler (PLIP) analysis on the new top list?",
            [("yes", "recommended for final triage"), ("no", "Skip PLIP for faster result")],
            default=1,
        )
        == "yes"
    )
    plip_top_n = 0
    if run_plip:
        default_plip_top = min(20, top_n)
        plip_top_n = _ask_int("How many newly top-ranked ligands should get PLIP analysis", default=default_plip_top, minimum=1)
        plip_top_n = min(plip_top_n, top_n)
    progress["selections"].setdefault("refinement_parameters", {}).update(
        {
            "run_plip": run_plip,
            "plip_top_n": plip_top_n,
            "planned_redocks": top_n * len(seeds),
            "planned_plip_runs": plip_top_n if run_plip else 0,
            "plip_basis": "post-redocking composite ligand ranking",
            "parallelization": f"{workers} concurrent Vina jobs, each using 1 Vina CPU by default",
        }
    )
    _write_progress(progress_json, progress)
    default_out = root / "reports" / f"{Path(chosen['results_json']).parents[1].name}-hit-refinement"
    output_dir = Path(_ask("Output directory", default=str(default_out)))
    progress["selections"]["output_dir"] = str(output_dir)
    progress["selections"]["hit_refinement_started_message"] = HIT_REFINEMENT_NEXT_STEPS_MESSAGE
    progress.setdefault("events", []).append(_event("parameters", "Recorded refinement parameters and output directory."))
    _write_progress(progress_json, progress)

    execution = ask_hpc_execution(
        root=root,
        progress=progress,
        progress_json=progress_json,
        block="hit-refinement",
        local_label="This computer/server now",
        default_time="12:00:00",
        default_cpus=1,
        default_gres=None,
    )
    if execution["backend"] != "local":
        export = export_slurm_hit_refinement(
            results_json=Path(chosen["results_json"]),
            output_dir=output_dir,
            top_n=top_n,
            exhaustiveness=exhaustiveness,
            num_modes=num_modes,
            cpu=1,
            seeds=",".join(str(seed) for seed in seeds),
            run_plip=run_plip,
            plip_top_n=plip_top_n,
            config=hpc_config(execution, default_job_name="oslab-hit-refine", default_time="12:00:00"),
        )
        record_hpc_export(progress, progress_json, export, block="hit-refinement")
        print("\nCluster export created.")
        print(f"Submit on the cluster with: cd '{export.output_dir}' && sbatch submit.slurm")
        print("The dashboard will show progress/results after the cluster writes files into the shared workspace.")
        return 0

    progress.setdefault("events", []).append(_event("redock", HIT_REFINEMENT_NEXT_STEPS_MESSAGE))
    _write_progress(progress_json, progress)
    print(f"\n{HIT_REFINEMENT_NEXT_STEPS_MESSAGE}")
    result = refine_hits_from_results(
        results_json=Path(chosen["results_json"]),
        output_dir=output_dir,
        top_n=top_n,
        exhaustiveness=exhaustiveness,
        num_modes=num_modes,
        cpu=1,
        workers=workers,
        seeds=seeds,
        run_plip=run_plip,
        plip_top_n=plip_top_n,
        progress_json=progress_json,
    )
    print("\nHit refinement completed.")
    print(f"Report: {result['report_markdown']}")
    print(f"Results: {result['results_csv']}")
    return 0


def recent_docking_runs(root: Path, limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    summary_paths: list[Path] = []
    for base in [root / "reports", root / "runs"]:
        summary_paths.extend(base.glob("*/small_screen_summary.json"))
        summary_paths.extend(base.glob("*/report/docking_results_summary.json"))
        summary_paths.extend(base.glob("*/*/docking_results_summary.json"))
    for summary_path in sorted(set(summary_paths)):
        try:
            data = json.loads(summary_path.read_text())
        except Exception:
            continue
        results_json = data.get("results_json")
        if not results_json or not Path(results_json).exists():
            continue
        if _looks_like_hit_refinement_output(summary_path, data, results_json):
            continue
        rows.append(
            {
                "name": summary_path.parent.name if summary_path.name != "docking_results_summary.json" else summary_path.parent.parent.name,
                "summary_path": str(summary_path),
                "results_json": results_json,
                "results_csv": data.get("results_csv"),
                "report_markdown": data.get("report_markdown") or data.get("docking_report"),
                "best_ligand": data.get("best_ligand"),
                "best_score": data.get("best_score"),
                "run_count": data.get("run_count") or data.get("docked_ligands"),
                "created_at": data.get("created_at"),
            }
        )
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if row["results_json"] in seen:
            continue
        seen.add(row["results_json"])
        unique.append(row)
        if len(unique) >= limit:
            break
    return unique


def _looks_like_hit_refinement_output(summary_path: Path, data: dict[str, Any], results_json: str) -> bool:
    """Return True for outputs that are already Block 2 hit-refinement products."""
    markers = ("hit-refinement", "hit_refinement")
    values = [
        str(summary_path),
        str(data.get("output_dir") or ""),
        str(data.get("report_markdown") or data.get("docking_report") or ""),
        str(data.get("results_csv") or ""),
        str(results_json or ""),
    ]
    return any(marker in value.lower() for marker in markers for value in values)


def _load_ranked_rows(results_json: Path) -> list[dict[str, str]]:
    rows = json.loads(results_json.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"expected list of ligand rows in {results_json}")
    valid = [dict(row) for row in rows if isinstance(row, dict) and row.get("run_json") and row.get("ligand_pdbqt")]
    valid.sort(key=lambda row: float(row["best_score"]) if row.get("best_score") not in {None, ""} else float("inf"))
    return valid


def _binding_site_for_run(row: dict[str, str]) -> str:
    run_json = Path(str(row["run_json"]))
    data = json.loads(run_json.read_text())
    return str(data["binding_site_json"])


def _redock_one_refinement_task(
    task: dict[str, Any],
    *,
    exhaustiveness: int,
    num_modes: int,
    cpu: int,
) -> Path:
    row = task["row"]
    seed = int(task["seed"])
    options = VinaRunOptions(exhaustiveness=exhaustiveness, num_modes=num_modes, cpu=cpu, seed=seed)
    record = run_vina(
        receptor_pdbqt=Path(str(row["receptor_pdbqt"])),
        ligand_pdbqt=Path(str(row["ligand_pdbqt"])),
        binding_site_json=Path(str(task["binding_site"])),
        output_dir=Path(task["run_dir"]),
        options=options,
    )
    return Path(record.metadata_path)


def _update_redock_progress(
    progress: dict[str, Any],
    progress_json: Path | None,
    completed: int,
    total: int,
    total_plip: int,
    task: dict[str, Any],
    workers: int,
) -> None:
    progress["refinement_progress"] = {
        "completed_redocks": completed,
        "total_redocks": total,
        "completed_plip": 0,
        "total_plip": total_plip,
        "progress_percent": round((completed / total) * 100, 1) if total else 0,
        "current_ligand": str(task.get("ligand_name") or ""),
        "current_seed": int(task.get("seed") or 0),
        "workers": workers,
        "phase": "redock",
    }
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_progress(progress_json, progress)


def _write_per_ligand_seed_summary(
    output_dir: Path,
    summary: DockingResultsSummary,
    source_rows: list[dict[str, str]] | None = None,
) -> dict[str, Path]:
    rows = json.loads(Path(summary.results_json).read_text())
    source_rank = {str(row.get("ligand") or ""): index for index, row in enumerate(source_rows or [], start=1)}
    source_metadata = {
        str(row.get("ligand") or ""): _ligand_metadata_fields(row)
        for row in (source_rows or [])
        if row.get("ligand")
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        ligand = str(row.get("ligand") or "")
        if not ligand:
            continue
        groups.setdefault(ligand, []).append(row)

    summary_rows: list[dict[str, Any]] = []
    for ligand, ligand_rows in groups.items():
        scores = [_score(row) for row in ligand_rows]
        scores = [score for score in scores if score is not None]
        seed_count = len({str(row.get("seed") or "") for row in ligand_rows if row.get("seed") not in {None, ""}})
        score_std = pstdev(scores) if len(scores) > 1 else 0.0
        best_row = min(ligand_rows, key=lambda row: _score(row) if _score(row) is not None else float("inf"))
        best_score = min(scores) if scores else None
        mean_score = mean(scores) if scores else None
        rank = source_rank.get(ligand, len(source_rank) + 1)
        composite_score = _composite_hit_score(
            best_score=best_score,
            mean_score=mean_score,
            score_std=score_std if scores else None,
            initial_rank=rank,
            seed_count=seed_count or len(ligand_rows),
        )
        summary_row = {
            "ligand": ligand,
            "composite_rank": 0,
            "composite_score": f"{composite_score:.3f}",
            "best_score": "" if best_score is None else f"{best_score:.3f}",
            "mean_score": "" if mean_score is None else f"{mean_score:.3f}",
            "score_std": "" if not scores else f"{score_std:.3f}",
            "seed_count": seed_count or len(ligand_rows),
            "consistent": bool(scores) and score_std < 1.0,
            "initial_refinement_rank": rank,
            "best_seed": str(best_row.get("seed") or ""),
            "best_run_json": str(best_row.get("run_json") or ""),
            "best_output_pdbqt": str(best_row.get("output_pdbqt") or ""),
        }
        metadata = source_metadata.get(ligand, {})
        metadata.update({key: value for key, value in _ligand_metadata_fields(best_row).items() if value and key not in metadata})
        summary_row.update(metadata)
        summary_rows.append(summary_row)
    summary_rows.sort(
        key=lambda row: (
            -float(row["composite_score"]) if row["composite_score"] not in {None, ""} else float("inf"),
            float(row["mean_score"]) if row["mean_score"] not in {None, ""} else float("inf"),
        )
    )
    for index, row in enumerate(summary_rows, start=1):
        row["composite_rank"] = index

    report_dir = output_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "per_ligand_seed_summary.json"
    csv_path = report_dir / "per_ligand_seed_summary.csv"
    json_path.write_text(json.dumps(summary_rows, indent=2) + "\n")
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "composite_rank",
                "ligand",
                "composite_score",
                "best_score",
                "mean_score",
                "score_std",
                "seed_count",
                "consistent",
                "initial_refinement_rank",
                "best_seed",
                "best_run_json",
                "best_output_pdbqt",
                "smiles",
                "canonical_smiles",
                "isomeric_smiles",
                "zinc_id",
                "chembl_id",
                "is_active",
                "class",
                "dude_class",
                "ligand_pdbqt",
                "input_pdbqt",
            ],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(summary_rows)
    return {"json": json_path, "csv": csv_path}


def _ligand_metadata_fields(row: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in (
        "smiles",
        "canonical_smiles",
        "isomeric_smiles",
        "zinc_id",
        "chembl_id",
        "is_active",
        "class",
        "dude_class",
        "ligand_pdbqt",
        "input_pdbqt",
    ):
        value = row.get(key)
        if value not in {None, ""}:
            metadata[key] = value
    return metadata


def _load_composite_ranking(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict) and row.get("ligand")]


def _composite_hit_score(
    best_score: float | None,
    mean_score: float | None,
    score_std: float | None,
    initial_rank: int,
    seed_count: int,
) -> float:
    if best_score is None or mean_score is None:
        return float("-inf")
    consistency_bonus = max(0.0, 1.0 - float(score_std or 0.0))
    initial_rank_bonus = 1.0 / max(1, initial_rank)
    seed_bonus = min(seed_count, 5) * 0.05
    return (-mean_score) + (0.25 * -best_score) + consistency_bonus + initial_rank_bonus + seed_bonus


def _append_composite_score_section(report_path: Path, ranking_json: Path) -> None:
    header = "## Composite Hit Ranking"
    report = report_path.read_text() if report_path.exists() else "# Docking Report\n"
    if header in report:
        report = report[: report.index(header)].rstrip()
    rows = _load_composite_ranking(ranking_json)[:20]
    lines = [
        "",
        header,
        "",
        "The composite score is a practical triage score used after hit refinement. It is not a physical binding energy and should not be compared across unrelated targets or workflows.",
        "",
        "Formula:",
        "",
        "`composite_score = (-mean_score) + 0.25 * (-best_score) + max(0, 1 - score_std) + (1 / initial_refinement_rank) + 0.05 * min(seed_count, 5)`",
        "",
        "Interpretation:",
        "",
        "- `mean_score`: average refined Vina score across seeds. Because Vina scores are negative and more negative is better, the formula uses `-mean_score` so better ligands receive larger positive values.",
        "- `best_score`: best refined Vina score observed for the ligand; it has lower weight than the mean so one unusually good seed does not dominate.",
        "- `score_std`: variability across seeds; lower variability increases the consistency bonus.",
        "- `initial_refinement_rank`: preserves a small amount of information from the first-pass docking rank.",
        "- `seed_count`: small bonus for ligands assessed across multiple seeds, capped at five seeds.",
        "- `consistent`: marked true when `score_std < 1.0`; treat score differences below about 1 kcal/mol cautiously.",
        "",
        "Use this ranking to prioritize visual inspection and follow-up, not as proof of binding.",
        "",
    ]
    if rows:
        lines.extend(
            [
                "| Rank | Ligand | Composite score | Mean score | Best score | Score SD | Seeds | Consistent |",
                "| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row in rows:
            lines.append(
                f"| {row.get('composite_rank', '')} | {row.get('ligand', '')} | {row.get('composite_score', '')} | {row.get('mean_score', '')} | {row.get('best_score', '')} | {row.get('score_std', '')} | {row.get('seed_count', '')} | {row.get('consistent', '')} |"
            )
    report_path.write_text(report.rstrip() + "\n" + "\n".join(lines).rstrip() + "\n")


def _score(row: dict[str, Any]) -> float | None:
    try:
        return float(row.get("best_score"))
    except (TypeError, ValueError):
        return None


def _deduplicate_by_scaffold(rows: list[dict[str, str]], max_n: int) -> list[dict[str, str]]:
    if max_n < 1:
        return []
    try:
        from rdkit import Chem
        from rdkit.Chem import DataStructs, rdFingerprintGenerator
        from rdkit.Chem.Scaffolds import MurckoScaffold
    except Exception:
        return rows[:max_n]

    selected: list[dict[str, str]] = []
    selected_fps: list[Any] = []
    morgan_generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    for row in rows:
        if len(selected) >= max_n:
            break
        mol = _mol_for_scaffold_dedup(row, Chem)
        if mol is None:
            selected.append(row)
            continue
        scaffold = MurckoScaffold.GetScaffoldForMol(mol)
        fp_mol = scaffold if scaffold is not None and scaffold.GetNumAtoms() else mol
        fp = morgan_generator.GetFingerprint(fp_mol)
        if all(DataStructs.TanimotoSimilarity(fp, prior) < 0.7 for prior in selected_fps):
            selected.append(row)
            selected_fps.append(fp)
    return selected


def _has_hit_clustering_metadata(rows: list[dict[str, str]]) -> bool:
    return any(
        row.get("cluster_id")
        or row.get("cluster_method")
        or row.get("cluster_selection_reason")
        for row in rows
    )


def _select_preclustered_rows(rows: list[dict[str, str]], max_n: int) -> list[dict[str, str]]:
    if max_n < 1:
        return []
    return rows[:max_n]


def _mol_for_scaffold_dedup(row: dict[str, str], chem: Any) -> Any | None:
    smiles = _smiles_for_row(row)
    if smiles:
        mol = chem.MolFromSmiles(smiles)
        if mol is not None:
            return mol
    ligand_path = Path(str(row.get("ligand_pdbqt") or ""))
    if not ligand_path.exists():
        return None
    try:
        return chem.MolFromPDBFile(str(ligand_path), sanitize=False, removeHs=False)
    except Exception:
        return None


def _smiles_for_row(row: dict[str, str]) -> str:
    for key in ["smiles", "canonical_smiles", "isomeric_smiles"]:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    ligand_path = Path(str(row.get("ligand_pdbqt") or ""))
    if not ligand_path.exists():
        return ""
    for line in ligand_path.read_text(errors="ignore").splitlines():
        if line.startswith("REMARK SMILES "):
            return line.removeprefix("REMARK SMILES ").strip()
    return ""


def _write_refinement_summary(
    output_dir: Path,
    source_results_json: Path,
    summary: DockingResultsSummary,
    selected_rows: list[dict[str, str]],
    seeds: list[int],
    plip_top_n: int = 0,
    per_ligand_summary: dict[str, Path] | None = None,
) -> None:
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_results_json": str(source_results_json.resolve()),
        "output_dir": str(output_dir),
        "selected_ligands": [row.get("ligand", "") for row in selected_rows],
        "seeds": seeds,
        "plip_top_n": plip_top_n,
        "plip_run_count": plip_top_n,
        "plip_basis": "post-redocking composite ligand ranking",
        "results_json": summary.results_json,
        "results_csv": summary.results_csv,
        "per_ligand_summary_json": str(per_ligand_summary["json"]) if per_ligand_summary else None,
        "per_ligand_summary_csv": str(per_ligand_summary["csv"]) if per_ligand_summary else None,
        "composite_ranking_json": str(per_ligand_summary["json"]) if per_ligand_summary else None,
        "composite_ranking_csv": str(per_ligand_summary["csv"]) if per_ligand_summary else None,
        "report_markdown": summary.report_markdown,
        "run_count": summary.run_count,
        "best_ligand": summary.best_ligand,
        "best_score": summary.best_score,
        "notes": "Hit refinement re-docked top ligands from a previous docking report with higher exhaustiveness and multiple seeds.",
    }
    (output_dir / "hit_refinement_summary.json").write_text(json.dumps(payload, indent=2) + "\n")


def _refinement_report_context(
    *,
    results_json: Path,
    output_dir: Path,
    selected: list[dict[str, str]],
    seeds: list[int],
    top_n: int,
    exhaustiveness: int,
    num_modes: int,
    cpu: int,
    workers: int,
    run_plip: bool,
    plip_top_n: int,
) -> dict[str, object]:
    first = selected[0] if selected else {}
    return {
        "target": "same target as source docking report",
        "target_identifier": _source_target_identifier(first),
        "target_structure": _source_target_structure(first),
        "receptor_pdbqt": first.get("receptor_pdbqt", ""),
        "binding_site_json": _source_binding_site(first),
        "ligand_library_label": f"Top {top_n} ligands from prior docking report",
        "ligand_source": "hit refinement input",
        "ligand_goal": "post-screen hit refinement",
        "ligand_input": str(results_json.resolve()),
        "requested_max_ligands": top_n,
        "prepared_ligands": len(selected),
        "docked_ligands": len(selected) * len(seeds),
        "output_dir": str(output_dir),
        "run_plip": run_plip,
        "docking_parameters": {
            "workflow": "hit refinement",
            "top_n": top_n,
            "seeds": ",".join(str(seed) for seed in seeds),
            "exhaustiveness": exhaustiveness,
            "num_modes": num_modes,
            "cpu": cpu,
            "workers": workers,
            "plip_top_n": plip_top_n,
            "plip_basis": "post-redocking composite ligand ranking",
            "output_dir": str(output_dir),
        },
    }


def _source_binding_site(row: dict[str, str]) -> str:
    try:
        return _binding_site_for_run(row)
    except Exception:
        return ""


def _source_target_structure(row: dict[str, str]) -> str:
    binding_site = _source_binding_site(row)
    if not binding_site:
        return ""
    try:
        return str(json.loads(Path(binding_site).read_text()).get("structure_path") or "")
    except Exception:
        return ""


def _source_target_identifier(row: dict[str, str]) -> str:
    structure = _source_target_structure(row)
    return Path(structure).stem if structure else ""


def _move_ligand_result_table_to_end(report_path: Path) -> None:
    header = "## Ligand Result Table"
    if not report_path.exists():
        return
    report = report_path.read_text()
    start = report.find(header)
    if start < 0:
        return
    section_start = report.rfind("\n", 0, start)
    section_start = section_start if section_start >= 0 else start
    next_section = report.find("\n## ", start + len(header))
    section_end = next_section if next_section >= 0 else len(report)
    section = report[section_start:section_end].strip()
    remaining = (report[:section_start] + report[section_end:]).rstrip()
    report_path.write_text(remaining + "\n\n" + section + "\n")


def _new_refinement_progress(output_dir: Path, progress_json: Path | None, results_json: Path) -> dict[str, Any]:
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "current_step": "select-run",
        "progress_json": str(progress_json) if progress_json else "",
        "steps": [{"key": step, "status": "pending"} for step in REFINEMENT_STEPS],
        "selections": {
            "output_dir": str(output_dir),
            "source_results_json": str(results_json.resolve()),
        },
        "events": [],
        "notes": [
            "Hit refinement re-docks top ligands from an existing report with higher Vina rigor.",
            "The dashboard reads this progress file in the Hit Refinement monitor.",
        ],
    }


def _new_interactive_progress(root: Path, progress_json: Path) -> dict[str, Any]:
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "current_step": "select-run",
        "progress_json": str(progress_json),
        "steps": [{"key": step, "status": "pending"} for step in REFINEMENT_STEPS],
        "selections": {"root": str(root)},
        "events": [_event("start", "Started interactive hit refinement terminal.")],
        "notes": [
            "Hit refinement re-docks selected top ligands with more rigorous Vina settings.",
            "PLIP can be limited to a smaller number of top ligands to save time.",
        ],
    }


def _complete(progress: dict[str, Any], step: str, progress_json: Path | None) -> None:
    progress["current_step"] = step
    for row in progress["steps"]:
        if row["key"] == step:
            row["status"] = "completed"
        elif row["status"] == "pending":
            break
    progress.setdefault("events", []).append(_event(step, "Completed"))
    _write_progress(progress_json, progress)


def _event(step: str, message: str) -> dict[str, str]:
    return {"time": datetime.now(timezone.utc).isoformat(), "step": step, "message": message}


def _write_progress(progress_json: Path | None, progress: dict[str, Any]) -> None:
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    if progress_json:
        progress_json.parent.mkdir(parents=True, exist_ok=True)
        progress_json.write_text(json.dumps(progress, indent=2) + "\n")


def _read_progress(progress_json: Path | None) -> dict[str, Any] | None:
    if not progress_json or not progress_json.exists():
        return None
    try:
        progress = json.loads(progress_json.read_text())
    except Exception:
        return None
    return progress if isinstance(progress, dict) else None


def _merge_existing_progress(progress: dict[str, Any], progress_json: Path | None) -> None:
    existing = _read_progress(progress_json)
    if not existing:
        return
    existing_events = existing.get("events") if isinstance(existing.get("events"), list) else []
    progress_events = progress.get("events") if isinstance(progress.get("events"), list) else []
    existing_selections = existing.get("selections") if isinstance(existing.get("selections"), dict) else {}
    progress_selections = progress.get("selections") if isinstance(progress.get("selections"), dict) else {}
    progress["events"] = existing_events + progress_events
    progress["selections"] = {**existing_selections, **progress_selections}


def _run_label_from_results(results_json: Path) -> str:
    parts = results_json.resolve().parts
    return "/".join(parts[-4:])


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)[:120] or "ligand"


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
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


def _parse_seed_list(value: str) -> list[int]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise ValueError("at least one seed is required")
    return [int(part) for part in parts]


def _ask_seed_list(prompt: str, default: str = "1,2,3") -> list[int]:
    while True:
        value = _ask(prompt, default)
        try:
            return _parse_seed_list(value)
        except ValueError:
            print("Enter comma-separated whole numbers, for example 1,2,3.")


def _choose(prompt: str, choices: list[tuple[str, str]], default: int = 1) -> str:
    return str(_choose_row(prompt, choices, default=default))


def _choose_row(prompt: str, rows: list[tuple[Any, str]], default: int = 1) -> Any:
    if not rows:
        raise RuntimeError(f"No options available for {prompt}")
    print(f"\n{prompt}")
    for index, (_value, label) in enumerate(rows, start=1):
        marker = " [default]" if index == default else ""
        print(f"  {index}. {label}{marker}")
    while True:
        value = _ask("Select number", str(default))
        try:
            index = int(value)
        except ValueError:
            print("Enter a number.")
            continue
        if 1 <= index <= len(rows):
            return rows[index - 1][0]
        print(f"Enter a number from 1 to {len(rows)}.")
