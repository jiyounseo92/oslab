from __future__ import annotations

import json
import shutil
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .binding_sites import box_from_fpocket, run_fpocket
from .dashboard import (
    _combine_downloaded_ligands,
    _dashboard_ligand_starter_libraries,
    _download_ligand_url,
    _is_vina_ready_ligand_input,
    _ligand_goal_count,
    _local_ligand_count,
    _search_targets,
)
from .docking import prepare_receptor_for_vina
from .hpc_terminal import ask_hpc_execution
from .hit_refinement import refine_hits_from_results
from .ligand_filtering import filter_ligands
from .ligand_prep import prepare_ligands_for_vina
from .jobs import campaign_context, job_progress_path, new_job_id, runtime_provenance
from .protein import prepare_protein
from .schemas import LigandPrepOptions, ProteinPrepOptions
from .structures import fetch_alphafold_structure, fetch_pdb_structure, list_structure_records
from .visualization import render_binding_site_html, render_pockets_html


STEPS = [
    "target",
    "target-prep",
    "binding-site",
    "ligands",
    "ligand-prep",
    "docking",
    "report",
]

DOCKING_NEXT_STEPS_MESSAGE = "After docking completes, look for results in the Reports tab or use in the Hit Refinement tab."

_ACTIVE_PROGRESS: dict[str, Any] | None = None
_ACTIVE_PROGRESS_JSON: Path | None = None


def run_terminal_orchestration(root: Path, progress_json: Path | None = None) -> int:
    root = root.resolve()
    progress_json = (progress_json or job_progress_path(root, "terminal-orchestration", new_job_id("workflow"))).resolve()
    try:
        return _run_terminal_orchestration_impl(root, progress_json)
    except Exception as exc:
        progress = _read_progress(progress_json) or _new_progress(root, progress_json)
        progress["status"] = "failed"
        progress["error"] = str(exc)
        progress["failed_at"] = datetime.now(timezone.utc).isoformat()
        progress.setdefault("events", []).append(
            {"time": datetime.now(timezone.utc).isoformat(), "step": progress.get("current_step", "unknown"), "message": f"Failed: {exc}"}
        )
        _write_progress(progress_json, progress)
        print(f"\nOrchestration failed: {exc}")
        print(f"Progress JSON: {progress_json}")
        return 1


def _run_terminal_orchestration_impl(root: Path, progress_json: Path) -> int:
    root = root.resolve()
    progress = _new_progress(root, progress_json)
    selections = progress["selections"]
    global _ACTIVE_PROGRESS, _ACTIVE_PROGRESS_JSON
    _ACTIVE_PROGRESS = progress
    _ACTIVE_PROGRESS_JSON = progress_json
    _write_progress(progress_json, progress)

    print("\nOSLabLambda guided orchestration")
    print(f"Project root: {root}")
    print(f"Progress JSON: {progress_json}")
    print("\nType the target gene symbol, then choose numbered options. Press Enter for defaults.\n")

    workflow_mode = _choose(
        "Workflow mode",
        [
            ("full-docking", "full target, binding-site, ligand, prep, and docking workflow"),
            ("zinc-download-only", "download and merge a ZINC ligand library only"),
        ],
        default=1,
    )
    selections["workflow_mode"] = workflow_mode
    _write_progress(progress_json, progress)
    if workflow_mode == "zinc-download-only":
        ligand_input = _download_zinc_only(root, selections, progress, progress_json)
        selections["final_ligand_library"] = str(ligand_input)
        for row in progress["steps"]:
            if row["key"] == "ligands":
                row["status"] = "completed"
            elif row["status"] == "pending":
                row["status"] = "skipped"
        progress["current_step"] = "ligands"
        progress["status"] = "completed"
        progress["finished_at"] = datetime.now(timezone.utc).isoformat()
        _log_event(progress, "ligands", "ZINC-only download workflow completed.", ligand_input=str(ligand_input))
        _write_progress(progress_json, progress)
        print(f"\nZINC download workflow complete.\nLibrary: {ligand_input}\n")
        return 0

    target = _select_target(root, selections, progress, progress_json)
    _complete(progress, "target", progress_json)

    prep = _select_or_prepare_target(root, target, selections, progress, progress_json)
    _complete(progress, "target-prep", progress_json)

    site = _select_binding_site(root, target, prep, selections, progress, progress_json)
    _complete(progress, "binding-site", progress_json)

    ligand_input = _select_ligand_library(root, selections, progress, progress_json)
    _complete(progress, "ligands", progress_json)

    ligand_prep_future = _select_or_prepare_ligands(root, ligand_input, selections, progress, progress_json)
    if ligand_prep_future is None:
        _complete(progress, "ligand-prep", progress_json)

    _select_docking_options(root, selections, progress, progress_json)

    run_now = _choose(
        "Launch docking now?",
        [
            ("yes", "Run the docking now"),
            ("no", "Record the command only"),
        ],
        default=1,
    )
    selections["launch_requested"] = run_now == "yes"
    if ligand_prep_future is not None:
        print("\nLigand prep is running. Docking will start automatically after prep finishes.")
        _finish_ligand_prep_future(ligand_prep_future, selections, progress, progress_json)
        _complete(progress, "ligand-prep", progress_json)
    _complete(progress, "docking", progress_json)
    selections["report_context_json"] = str(_write_report_context(selections, Path(str(selections.get("output_dir") or root / "reports" / "screen"))))
    command = _screen_command(selections)
    selections["screen_command"] = command
    _log_event(progress, "docking", "Docking launch choice recorded.", launch_requested=selections["launch_requested"], command=command)
    _write_progress(progress_json, progress)
    if run_now == "yes":
        selections["docking_started_message"] = DOCKING_NEXT_STEPS_MESSAGE
        _log_event(progress, "docking", DOCKING_NEXT_STEPS_MESSAGE)
        _write_progress(progress_json, progress)
        print(f"\n{DOCKING_NEXT_STEPS_MESSAGE}")
        print("\nStarting docking command:\n" + command + "\n")
        result = subprocess.run(command, cwd=root, shell=True, check=False)
        selections["screen_returncode"] = result.returncode
        if result.returncode != 0:
            progress["status"] = "failed"
            progress["error"] = f"Docking command exited with status {result.returncode}"
            _write_progress(progress_json, progress)
            return result.returncode
    else:
        print("\nSaved command for later:\n" + command)

    _complete(progress, "report", progress_json)
    progress["status"] = "completed"
    progress["finished_at"] = datetime.now(timezone.utc).isoformat()
    output_dir = Path(str(selections.get("output_dir") or ""))
    if output_dir and selections.get("execution_backend") != "local":
        export_dir = output_dir / "slurm-docking"
        selections["hpc_export"] = {
            "block": "docking",
            "output_dir": str(export_dir),
            "submit_script": str(export_dir / "submit.slurm"),
            "run_script": str(export_dir / "run_one_ligand.sh"),
            "metadata_path": str(export_dir / "slurm_docking_export.json"),
            "submit_command": f"cd {shlex_quote(str(export_dir))} && sbatch submit.slurm",
        }
        selections["docking_started_message"] = "SLURM export is ready. No docking jobs have run yet; submit the generated script on the cluster, then collect results."
        _log_event(progress, "report", "SLURM export paths recorded.", **selections["hpc_export"])
    elif output_dir:
        selections["final_report_markdown"] = str(output_dir / "report" / "docking_report.md")
        selections["final_results_json"] = str(output_dir / "vina_results.json")
        selections["final_results_csv"] = str(output_dir / "vina_results.csv")
        _log_event(progress, "report", "Final report paths recorded.", report=selections["final_report_markdown"])
        if run_now == "yes" and Path(selections["final_results_json"]).exists():
            refine_now = _choose(
                "Docking is complete. Refine top hits with higher exhaustiveness now?",
                [
                    ("no", "Finish now; refine later from the dashboard Hit Refinement section"),
                    ("yes", "Run hit refinement now"),
                ],
                default=1,
            )
            selections["hit_refinement_requested"] = refine_now == "yes"
            if refine_now == "yes":
                top_n = _ask_int("Top ligands to refine", default=min(50, int(selections.get("max_ligands") or 20)), minimum=1)
                refinement_exhaustiveness = _ask_int("Refinement exhaustiveness", default=16, minimum=1)
                seed_text = _ask("Refinement seeds", default="1,2,3")
                seeds = [int(part.strip()) for part in seed_text.split(",") if part.strip()]
                refinement_out = root / "reports" / f"{Path(str(output_dir)).name}-hit-refinement"
                refinement_progress = root / "runs" / f"hit-refinement-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}" / "progress.json"
                result = refine_hits_from_results(
                    results_json=Path(selections["final_results_json"]),
                    output_dir=refinement_out,
                    top_n=top_n,
                    exhaustiveness=refinement_exhaustiveness,
                    num_modes=3,
                    cpu=1,
                    seeds=seeds,
                    run_plip=True,
                    progress_json=refinement_progress,
                )
                selections["hit_refinement"] = result
                _log_event(progress, "report", "Hit refinement completed.", report=result.get("report_markdown"))
    _write_progress(progress_json, progress)
    print(f"\nOrchestration selections saved: {progress_json}")
    return 0


def _select_target(root: Path, selections: dict[str, Any], progress: dict[str, Any], progress_json: Path) -> dict[str, Any]:
    gene = _ask("Target gene symbol", default=selections.get("target_gene", ""))
    selections["target_gene"] = gene.upper()
    _write_progress(progress_json, progress)

    source = _choose(
        "Target structure source",
        [
            ("alphafold", "AlphaFold DB prediction; best when no good experimental structure is available"),
            ("pdb", "RCSB PDB experimental structures; best for known ligand-bound structures"),
            ("cached", "Use an already cached local structure"),
        ],
        default=1,
    )
    selections["target_source"] = source

    if source == "cached":
        cached = list_structure_records(root)
        if not cached:
            print("No cached structures found. Falling back to AlphaFold search.")
            source = "alphafold"
        else:
            record = _choose_row(
                "Cached structures",
                [(record, f"{record.key} | {record.structure_type} | {record.cached_path}") for record in cached],
            )
            selections["target_structure"] = record.cached_path
            selections["target_identifier"] = record.identifier
            selections["target_source"] = record.source
            selections["target_label"] = record.key
            selections["target_download_reused"] = True
            _log_event(progress, "target", "Selected cached target structure.", structure_path=record.cached_path, label=record.key)
            _write_progress(progress_json, progress)
            return {"structure_path": Path(record.cached_path), "label": record.key}

    matches = _search_targets({"gene": gene, "organism_id": "9606", "size": 8})
    rows = matches["alphafold"] if source == "alphafold" else matches["pdb"]
    if not rows:
        raise RuntimeError(f"No {source} matches found for {gene}")
    chosen = _choose_row(
        f"{source.upper()} matches for {gene}",
        [(row, _target_match_label(row)) for row in rows],
    )
    selections["target_identifier"] = chosen["identifier"]
    selections["target_match_title"] = chosen.get("title", "")
    selections["target_label"] = f"{gene.upper()} {source}:{chosen['identifier']}"
    print("\nFetching selected structure...")
    if source == "alphafold":
        record = fetch_alphafold_structure(chosen["identifier"], root=root, overwrite=False)
    else:
        record = fetch_pdb_structure(chosen["identifier"], root=root, file_format=chosen.get("fetch", {}).get("format", "cif"))
    selections["target_structure"] = record.cached_path
    selections["target_download_reused"] = Path(record.cached_path).exists()
    _log_event(
        progress,
        "target",
        "Fetched or reused selected target structure.",
        source=source,
        identifier=chosen["identifier"],
        structure_path=record.cached_path,
        title=chosen.get("title", ""),
    )
    _write_progress(progress_json, progress)
    return {"structure_path": Path(record.cached_path), "label": record.key}


def _select_or_prepare_target(
    root: Path,
    target: dict[str, Any],
    selections: dict[str, Any],
    progress: dict[str, Any],
    progress_json: Path,
) -> dict[str, Any]:
    structure = Path(target["structure_path"]).resolve()
    existing = _prepared_targets_for_structure(root, structure)
    if existing:
        chosen = _choose_row(
            "Prepared target found",
            [(row, f"reuse {row['receptor_pdbqt']}") for row in existing]
            + [("prepare-new", "prepare a new receptor instead")],
        )
        if chosen != "prepare-new":
            selections["receptor_pdbqt"] = chosen["receptor_pdbqt"]
            selections["target_prep_reused"] = True
            selections["target_prep_output_dir"] = chosen.get("output_dir", "")
            _log_event(progress, "target-prep", "Reused existing prepared receptor.", receptor_pdbqt=chosen["receptor_pdbqt"])
            _write_progress(progress_json, progress)
            return chosen

    print("\nPreparing target for docking with default conservative settings...")
    output_dir = root / "runs" / f"target-prep-{structure.stem}"
    prep = prepare_protein(
        structure,
        output_dir,
        ProteinPrepOptions(ph=7.4, keep_water=False, minimize=False),
    )
    receptor = prepare_receptor_for_vina(Path(prep.prepared_path), output_dir, allow_bad_residues=True)
    selections["protein_prep_json"] = prep.metadata_path
    selections["receptor_pdbqt"] = receptor.receptor_pdbqt
    selections["target_prep_reused"] = False
    selections["target_prep_output_dir"] = str(output_dir)
    selections["target_prep_parameters"] = {"ph": 7.4, "keep_water": False, "minimize": False, "allow_bad_residues": True}
    _log_event(progress, "target-prep", "Prepared target and receptor for docking.", receptor_pdbqt=receptor.receptor_pdbqt)
    _write_progress(progress_json, progress)
    return {"receptor_pdbqt": receptor.receptor_pdbqt, "output_dir": str(output_dir)}


def _select_binding_site(
    root: Path,
    target: dict[str, Any],
    prep: dict[str, Any],
    selections: dict[str, Any],
    progress: dict[str, Any],
    progress_json: Path,
) -> dict[str, Any]:
    structure = Path(target["structure_path"]).resolve()
    existing = _binding_sites_for_structure(root, structure)
    choices: list[tuple[Any, str]] = [("fpocket", "find pockets with fpocket and choose one")]
    choices.extend((row, f"reuse {row['key']} | {row['binding_site_json']}") for row in existing)
    chosen = _choose_row("Binding site", choices)
    if chosen != "fpocket":
        selections["binding_site_json"] = chosen["binding_site_json"]
        selections["binding_site_label"] = chosen["key"]
        selections["binding_site_reused"] = True
        html_path = Path(chosen["binding_site_json"]).parent / "binding_site.html"
        if html_path.exists():
            selections["binding_site_visualization_html"] = str(html_path)
        else:
            try:
                html_path = render_binding_site_html(structure, Path(chosen["binding_site_json"]), html_path)
                selections["binding_site_visualization_html"] = str(html_path)
            except Exception:
                pass
        _log_event(progress, "binding-site", "Reused saved binding site.", binding_site_json=chosen["binding_site_json"])
        _write_progress(progress_json, progress)
        return chosen

    top_n = _ask_int("How many pockets should fpocket show?", default=8, minimum=1)
    min_spheres = _ask_int("Minimum alpha spheres for a pocket", default=15, minimum=1)
    selections["fpocket_parameters"] = {"top_n": top_n, "min_spheres": min_spheres, "padding": 6.0, "minimum_size": 12.0}
    fpocket_dir = root / "runs" / f"fpocket-{structure.stem}"
    result = run_fpocket(structure, fpocket_dir, top_n=top_n, min_spheres=min_spheres, padding=6.0, minimum_size=12.0)
    pockets = result.get("pockets", [])
    if not pockets:
        raise RuntimeError("fpocket did not find any pockets with the selected settings")
    pockets_html = render_pockets_html(structure, pockets, fpocket_dir / "fpocket_pockets.html", title=f"{structure.name} fpocket Pockets")
    selections["pocket_visualization_html"] = str(pockets_html)
    selections["fpocket_output_dir"] = str(fpocket_dir)
    selections["fpocket_pocket_count"] = len(pockets)
    _log_event(progress, "binding-site", "fpocket found candidate pockets.", pocket_count=len(pockets), visualization_html=str(pockets_html))
    _write_progress(progress_json, progress)
    pocket = _choose_row(
        "fpocket pockets",
        [
            (
                pocket,
                f"Pocket {pocket.get('pocket_id')} | score {pocket.get('score')} | druggability {pocket.get('druggability_score')} | volume {pocket.get('volume')} | spheres {pocket.get('alpha_spheres')}",
            )
            for pocket in pockets
        ],
    )
    site_dir = root / "runs" / f"binding-site-{structure.stem}-pocket-{pocket.get('pocket_id')}"
    site = box_from_fpocket(structure, pocket, site_dir, padding=6.0, minimum_size=12.0)
    html_path = render_binding_site_html(structure, Path(site.metadata_path), site_dir / "binding_site.html")
    selections["binding_site_json"] = site.metadata_path
    selections["binding_site_label"] = f"Pocket {pocket.get('pocket_id')}"
    selections["binding_site_reused"] = False
    selections["binding_site_visualization_html"] = str(html_path)
    selections["binding_site_parameters"] = {"padding": 6.0, "minimum_size": 12.0, "selected_pocket": pocket}
    _log_event(progress, "binding-site", "Selected fpocket pocket and created docking box.", binding_site_json=site.metadata_path, label=selections["binding_site_label"])
    _write_progress(progress_json, progress)
    return site.model_dump(mode="json")


def _select_ligand_library(
    root: Path,
    selections: dict[str, Any],
    progress: dict[str, Any],
    progress_json: Path,
) -> Path:
    mode = _choose(
        "Ligand source",
        [
            ("download", "download a ligand library from a provider"),
            ("local", "use a ligand file already on this computer"),
        ],
        default=1,
    )
    selections["ligand_source_mode"] = mode
    _write_progress(progress_json, progress)

    if mode == "local":
        readiness = _choose(
            "Local ligand file type",
            [
                ("ready", "ready for docking: PDBQT or a filtered SDF with existing ligand prep"),
                ("needs-prep", "needs preparation: SMILES/SDF without validated RDKit/Meeko prep"),
            ],
            default=1,
        )
        selections["local_ligand_readiness"] = readiness
        local_rows = _local_ligand_choices(root, readiness)
        if not local_rows:
            print("\nNo matching local ligand libraries were found in the OS lab ligand catalog.")
            print(f"Expected user libraries under: {root / 'data-cache' / 'ligands'}")
            manual = _ask("Enter a local ligand file path", default="")
            if not manual:
                raise RuntimeError("No local ligand file selected.")
            ligand_path = Path(manual).expanduser().resolve()
        else:
            print(f"\nFound {len(local_rows)} matching local ligand libraries in {root / 'data-cache' / 'ligands'} and curated run outputs.")
            chosen = _choose_row("Local ligand files", local_rows)
            ligand_path = Path(chosen["path"]).resolve()
            if chosen.get("prepared"):
                selections["ligand_prepared"] = True
                selections["ligand_prep_reused"] = True
                selections["ligand_prep_json"] = chosen.get("prep_json", "")
                selections["ligand_prepared_count"] = chosen.get("prepared_count", 0)
            selections["ligand_library_label"] = chosen.get("label", ligand_path.name)
            selections["ligand_local_count"] = chosen.get("count", 0)
            selections["ligand_local_catalog"] = str(_local_ligand_catalog_path(root))
        selections.setdefault("ligand_library_label", ligand_path.name)
        selections["ligand_input"] = str(ligand_path)
        selections["ligand_download_reused"] = True
        _write_progress(progress_json, progress)
        return ligand_path

    source = "zinc3d-pdbqt"
    selections["download_ligand_source"] = source
    print("\nLoading ZINC library goals and provider counts. This may take a moment...")
    _set_ligand_source_status(
        selections,
        progress,
        progress_json,
        status="loading-zinc-goals",
        label="Loading ZINC library goals and provider counts...",
    )
    goals = _dashboard_ligand_starter_libraries()
    source_goals = [goal for goal in goals if goal["source_key"] == source]
    rows: list[tuple[Any, str]] = []
    for goal in source_goals:
        count_note = _safe_goal_count(goal["key"], root)
        rows.append((goal, f"{goal['name']} | {goal['goal']} | {count_note} | prep {goal['prep']} | {goal['download_count']} files"))
    _set_ligand_source_status(
        selections,
        progress,
        progress_json,
        status="zinc-goals-loaded",
        label=f"Loaded {len(rows)} ZINC download goals with provider counts.",
    )

    chosen = _choose_row("ZINC download goals", rows)
    return _download_ligand_goal(root, chosen, selections, progress, progress_json)

def _download_zinc_only(
    root: Path,
    selections: dict[str, Any],
    progress: dict[str, Any],
    progress_json: Path,
) -> Path:
    selections["ligand_source_mode"] = "download"
    selections["download_ligand_source"] = "zinc3d-pdbqt"
    for row in progress["steps"]:
        if row["key"] == "ligands":
            row["status"] = "running"
        elif row["status"] == "pending":
            row["status"] = "skipped"
    progress["current_step"] = "ligands"
    _set_ligand_source_status(
        selections,
        progress,
        progress_json,
        status="loading-zinc-goals",
        label="Loading ZINC library goals and provider counts...",
    )
    goals = [goal for goal in _dashboard_ligand_starter_libraries() if goal["source_key"] == "zinc3d-pdbqt"]
    rows: list[tuple[Any, str]] = []
    for goal in goals:
        count_note = _safe_goal_count(goal["key"], root)
        rows.append((goal, f"{goal['name']} | {goal['goal']} | {count_note} | prep {goal['prep']} | {goal['download_count']} files"))
    _set_ligand_source_status(
        selections,
        progress,
        progress_json,
        status="zinc-goals-loaded",
        label=f"Loaded {len(rows)} ZINC download goals with provider counts.",
    )
    chosen = _choose_row("ZINC download goals", rows)
    return _download_ligand_goal(root, chosen, selections, progress, progress_json)


def _download_ligand_goal(
    root: Path,
    goal: dict[str, Any],
    selections: dict[str, Any],
    progress: dict[str, Any],
    progress_json: Path,
) -> Path:
    metadata = _ligand_goal_count({"key": goal["key"]}, root)
    out_dir = root / "data-cache" / "ligands" / "downloads"
    planned = Path(metadata["planned_output_path"])
    selections["ligand_library_label"] = goal["name"]
    selections["ligand_goal_key"] = goal["key"]
    selections["ligand_expected_count"] = metadata["ligand_count"]
    selections["ligand_expected_size"] = metadata["total_size"]
    selections["ligand_input"] = str(planned)

    if planned.exists() and planned.stat().st_size > 0:
        print(f"\nReusing downloaded ligand file: {planned}")
        selections["ligand_download_reused"] = True
        selections["ligand_download_status"] = "reused"
        selections["ligand_download_progress_label"] = f"Reusing existing local library: {planned.name}"
        _log_event(progress, "ligands", "Reusing existing downloaded ligand library.", ligand_input=str(planned))
        _write_progress(progress_json, progress)
        return planned

    print(f"\nSelected: {goal['name']}")
    print(f"Provider records: {metadata['ligand_count']} across {metadata['file_count']} files; size {metadata['total_size']}.")
    download = _choose(
        "Download and merge now?",
        [("yes", "download now"), ("no", "record planned path only")],
        default=1,
    )
    if download == "no":
        selections["ligand_download_status"] = "planned"
        selections["ligand_download_progress_label"] = f"Planned download path recorded: {planned.name}"
        _log_event(progress, "ligands", "Recorded ligand download plan without downloading.", planned_output_path=str(planned))
        _write_progress(progress_json, progress)
        return planned

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, url in enumerate(metadata["urls"], start=1):
        selections["ligand_download_status"] = "downloading"
        selections["ligand_download_progress_label"] = f"Downloading file {index}/{len(metadata['urls'])}: {Path(url).name}"
        _log_event(progress, "ligands", "Downloading ligand source file.", index=index, total=len(metadata["urls"]), url=url)
        _write_progress(progress_json, progress)
        print(f"Downloading {index}/{len(metadata['urls'])}: {url}")
        paths.append(_download_ligand_url(url, out_dir, max_mb=500))
    final_path = _combine_downloaded_ligands(paths, out_dir, goal["output_name"])
    selections["ligand_input"] = str(final_path)
    selections["ligand_download_reused"] = False
    selections["ligand_local_count"] = _local_ligand_count(final_path)
    selections["ligand_download_status"] = "completed"
    selections["ligand_download_progress_label"] = f"Downloaded and merged {selections['ligand_local_count']} ligands into {final_path.name}"
    _log_event(progress, "ligands", "Downloaded and merged ligand library.", ligand_input=str(final_path), ligand_count=selections["ligand_local_count"])
    _write_progress(progress_json, progress)
    return final_path


def _select_or_prepare_ligands(
    root: Path,
    ligand_input: Path,
    selections: dict[str, Any],
    progress: dict[str, Any],
    progress_json: Path,
) -> Future | None:
    ligand_input = ligand_input.resolve()
    if selections.get("ligand_prepared") and selections.get("ligand_prep_reused"):
        print(f"\nUsing prepared ligand library: {selections.get('ligand_prepared_count', 'known')} prepared ligands")
        _write_progress(progress_json, progress)
        return None
    existing = _existing_ligand_prep_for_input(root, ligand_input)
    if existing:
        selections["ligand_prepared"] = True
        selections["ligand_prep_reused"] = True
        selections["ligand_prep_json"] = existing["metadata_path"]
        selections["ligand_prepared_count"] = existing["prepared_count"]
        print(f"\nReusing existing ligand prep: {existing['prepared_count']} PDBQT files")
        _write_progress(progress_json, progress)
        return None

    if _is_vina_ready_ligand_input(ligand_input):
        selections["ligand_prepared"] = True
        selections["ligand_prep_reused"] = True
        selections["ligand_prep_json"] = ""
        selections["ligand_prepared_count"] = _local_ligand_count(ligand_input) or 1
        print("\nLigand input is PDBQT/Vina-ready; skipping RDKit/Meeko prep.")
        _write_progress(progress_json, progress)
        return None

    print("\nThis ligand input is not PDBQT, so RDKit/Meeko prep is needed before Vina docking.")
    prepare = _choose(
        "Prepare ligands now?",
        [("yes", "filter and prepare now"), ("no", "record prep-needed status only")],
        default=1,
    )
    selections["ligand_prep_needed"] = True
    if prepare == "no":
        _write_progress(progress_json, progress)
        return None

    workers = _ask_int("Ligand-prep workers", default=4, minimum=1)
    output_dir = root / "runs" / f"ligand-prep-{ligand_input.stem}"
    selections["ligand_prep_output_dir"] = str(output_dir)
    selections["ligand_prep_workers"] = workers
    selections["ligand_prep_status"] = "running"
    _log_event(progress, "ligand-prep", "Started ligand preparation in background.", output_dir=str(output_dir), workers=workers)
    _write_progress(progress_json, progress)
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_run_ligand_prep_background, ligand_input, output_dir, workers)
    setattr(future, "_oslab_executor", executor)
    return future


def _run_ligand_prep_background(ligand_input: Path, output_dir: Path, workers: int) -> dict[str, Any]:
    filter_summary = filter_ligands(ligand_input, output_dir / "filtered", "drug_like")
    prep = prepare_ligands_for_vina(
        Path(filter_summary.included_sdf),
        output_dir / "vina-prep",
        LigandPrepOptions(workers=workers, generate_3d=True),
    )
    return {
        "ligand_input": filter_summary.included_sdf,
        "ligand_prepared": True,
        "ligand_prep_reused": False,
        "ligand_prep_json": prep.metadata_path,
        "ligand_prepared_count": prep.prepared_count,
    }


def _finish_ligand_prep_future(
    future: Future,
    selections: dict[str, Any],
    progress: dict[str, Any],
    progress_json: Path,
) -> None:
    try:
        result = future.result()
        selections.update(result)
        selections["ligand_prep_status"] = "completed"
        _log_event(
            progress,
            "ligand-prep",
            "Ligand preparation completed.",
            ligand_prep_json=selections.get("ligand_prep_json"),
            prepared_count=selections.get("ligand_prepared_count"),
        )
        _write_progress(progress_json, progress)
    finally:
        executor = getattr(future, "_oslab_executor", None)
        if executor:
            executor.shutdown(wait=False)


def _select_docking_options(
    root: Path,
    selections: dict[str, Any],
    progress: dict[str, Any],
    progress_json: Path,
) -> None:
    execution = ask_hpc_execution(
        root=root,
        progress=progress,
        progress_json=progress_json,
        block="docking",
        local_label="This computer/server now",
        default_time="04:00:00",
        default_cpus=1,
        default_gres=None,
    )
    backend = execution["backend"]
    selections["execution_backend"] = backend
    selections["max_ligands"] = _ask_int("Max ligands to dock", default=20, minimum=1)
    selections["exhaustiveness"] = _ask_int("Vina exhaustiveness", default=1 if backend == "local" else 4, minimum=1)
    selections["docking_workers"] = _ask_int("Parallel docking workers", default=1 if backend == "local" else 8, minimum=1)
    default_out = root / "reports" / f"{selections.get('target_gene', 'target').lower()}-{selections.get('ligand_goal_key', 'screen')}"
    selections["output_dir"] = _ask("Output directory", default=str(default_out))
    selections["docking_parameters"] = {
        "execution_backend": backend,
        "max_ligands": selections["max_ligands"],
        "exhaustiveness": selections["exhaustiveness"],
        "docking_workers": selections["docking_workers"],
        "output_dir": selections["output_dir"],
        "vina_num_modes": 1,
        "vina_cpu": 1,
        "vina_seed": 1,
    }
    if backend != "local":
        hpc = selections.get("hpc") or {}
        selections["docking_parameters"].update(
            {
                "slurm_job_name": hpc.get("job_name") or "oslab-vina",
                "slurm_cpus_per_task": hpc.get("cpus_per_task") or 1,
                "slurm_array_concurrency": _ask_int(
                    "Max simultaneous array jobs (how many ligand tasks SLURM may run at once; 100-500 is typical, lower if your cluster asks you to be gentle)",
                    default=500,
                    minimum=1,
                ),
                "slurm_time": hpc.get("time") or "04:00:00",
                "slurm_partition": hpc.get("partition") or "",
                "slurm_account": hpc.get("account") or "",
                "slurm_gres": hpc.get("gres") or "",
                "slurm_setup_command": hpc.get("setup_command") or "",
            }
        )
    _log_event(progress, "docking", "Recorded docking parameters.", **selections["docking_parameters"])
    _write_progress(progress_json, progress)


def _new_progress(root: Path, progress_json: Path) -> dict[str, Any]:
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "job_id": progress_json.parent.name.removeprefix("terminal-orchestration-"),
        **campaign_context(),
        "status": "running",
        "root": str(root),
        "current_step": "target",
        "progress_json": str(progress_json),
        "steps": [{"key": step, "status": "pending"} for step in STEPS],
        "total_items": 0,
        "completed_items": 0,
        "failed_items": 0,
        "next_block_ready": False,
        "selections": {},
        "provenance": runtime_provenance(forcefields={"vina": "CLI"}, structures={}),
        "events": [],
        "notes": [
            "Terminal orchestration uses numbered menus and deterministic tools.",
            "The dashboard reads this progress file as the orchestration monitor artifact.",
        ],
    }


def _target_match_label(row: dict[str, Any]) -> str:
    info = row.get("organism") or row.get("experimental_method") or ""
    title = row.get("title") or ""
    return f"{row['identifier']} | {title[:80]} | {info}"


def _prepared_targets_for_structure(root: Path, structure: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for prep_json in sorted((root / "runs").glob("**/protein_prep.json")):
        try:
            prep = json.loads(prep_json.read_text())
        except json.JSONDecodeError:
            continue
        if Path(str(prep.get("input_path") or "")).resolve() != structure:
            continue
        receptor_json = prep_json.parent / "receptor_prep.json"
        if not receptor_json.exists():
            continue
        receptor = json.loads(receptor_json.read_text())
        rows.append({"receptor_pdbqt": receptor.get("receptor_pdbqt", ""), "output_dir": str(prep_json.parent)})
    return rows


def _binding_sites_for_structure(root: Path, structure: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for site_json in sorted((root / "runs").glob("**/binding_site.json")):
        try:
            site = json.loads(site_json.read_text())
        except json.JSONDecodeError:
            continue
        if Path(str(site.get("structure_path") or "")).resolve() != structure:
            continue
        rows.append({"key": site_json.parent.name, "binding_site_json": str(site_json), "method": site.get("method", "")})
    return rows


def _safe_goal_count(key: str, root: Path) -> str:
    try:
        data = _ligand_goal_count({"key": key}, root)
    except Exception as exc:
        return f"count unavailable: {exc}"
    return f"{data['ligand_count']} records, {data['total_size']}"


def _set_ligand_source_status(
    selections: dict[str, Any],
    progress: dict[str, Any],
    progress_json: Path,
    *,
    status: str,
    label: str,
) -> None:
    selections["ligand_source_status"] = status
    selections["ligand_source_progress_label"] = label
    _log_event(progress, "ligands", label, status=status)
    _write_progress(progress_json, progress)


def _download_source_label(source_key: str, goals: list[dict[str, Any]]) -> str:
    count = sum(1 for goal in goals if goal["source_key"] == source_key)
    return f"{_source_display_name(source_key)} | {count} curated download goal{'s' if count != 1 else ''}"


def _source_display_name(source_key: str) -> str:
    names = {
        "zinc3d-pdbqt": "ZINC",
        "chembl": "ChEMBL",
        "pubchem": "PubChem",
        "enamine-sdf": "Enamine",
        "virtualflow-enamine-real": "VirtualFlow / Enamine REAL",
    }
    return names.get(source_key, source_key)


def _local_ligand_choices(root: Path, readiness: str) -> list[tuple[dict[str, Any], str]]:
    rows: list[tuple[dict[str, Any], str]] = []
    for path in _local_ligand_files(root):
        existing = _existing_ligand_prep_for_input(root, path)
        vina_ready = _is_vina_ready_ligand_input(path)
        prepared = bool(existing)
        if readiness == "ready" and not (vina_ready or prepared):
            continue
        if readiness == "needs-prep" and (vina_ready or prepared):
            continue
        count = _local_ligand_count(path)
        size = _human_file_size(path)
        source = _local_library_source(root, path)
        short_path = _short_local_path(root, path)
        if prepared:
            label = (
                f"prepared library | {path.name} | {existing['prepared_count']} PDBQT ligands | "
                f"input records {count or 'unknown'} | {size} | {source} | {short_path}"
            )
        elif vina_ready:
            label = f"Vina-ready PDBQT | {path.name} | records {count or 'trusted'} | {size} | {source} | {short_path}"
        else:
            label = f"needs prep | {path.name} | records {count or 'unknown'} | {size} | {source} | {short_path}"
        rows.append(
            (
                {
                    "path": str(path),
                    "label": path.name,
                    "count": count,
                    "size": size,
                    "source": source,
                    "readiness": readiness,
                    "prepared": prepared,
                    "prep_json": existing.get("metadata_path", "") if existing else "",
                    "prepared_count": existing.get("prepared_count", 0) if existing else 0,
                    "vina_ready": vina_ready,
                },
                label,
            )
        )
    rows.sort(key=lambda item: _local_ligand_sort_key(item[0]))
    _write_local_ligand_catalog(root, [row for row, _label in rows])
    return rows


def _local_ligand_files(root: Path) -> list[Path]:
    suffixes = {".smi", ".smiles", ".sdf", ".pdbqt"}
    allowed_paths = _catalog_allowed_paths(root)
    prepared_inputs = {path.resolve() for path in _prepared_ligand_inputs(root)}
    roots = [
        root / "data-cache" / "ligands",
        root / "data-cache" / "validation",
    ]
    files: list[Path] = []
    for scan_root in roots:
        if scan_root.exists():
            files.extend(path for path in scan_root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes)
    files.extend(prepared_inputs)
    candidates = {path.resolve() for path in files if _is_ligand_candidate(path)}
    if allowed_paths is not None:
        candidates = {path for path in candidates if str(path) in allowed_paths or path in prepared_inputs}
    return sorted(candidates)


def _is_ligand_candidate(path: Path) -> bool:
    skip_parts = {"docking", "interactions", "repair-unique-sdf", "prepared-mols"}
    if "receptor.pdbqt" == path.name:
        return False
    return not any(part in skip_parts for part in path.parts)


def _prepared_ligand_inputs(root: Path) -> list[Path]:
    inputs: list[Path] = []
    metadata_paths = [
        *(root / "runs").glob("ligand-prep-*/vina-prep/ligand_prep.json"),
        *(root / "runs").glob("*/ligand-vina-prep/ligand_prep.json"),
        *(root / "reports").glob("*/ligand-vina-prep/ligand_prep.json"),
    ]
    for path in metadata_paths:
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        input_sdf = Path(str(data.get("input_sdf") or ""))
        if input_sdf.exists():
            inputs.append(input_sdf.resolve())
    return inputs


def _catalog_allowed_paths(root: Path) -> set[str] | None:
    catalog = _local_ligand_catalog_path(root)
    if not catalog.exists():
        return None
    try:
        data = json.loads(catalog.read_text())
    except json.JSONDecodeError:
        return None
    if not data.get("curated_only"):
        return None
    return {str(row.get("path")) for row in data.get("libraries", []) if row.get("path")}


def _local_library_source(root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return "outside OS lab"
    parts = relative.parts
    if len(parts) >= 3 and parts[:3] == ("data-cache", "ligands", "downloads"):
        return "downloaded ligand library"
    if len(parts) >= 2 and parts[:2] == ("data-cache", "ligands"):
        return "local ligand library"
    if len(parts) >= 2 and parts[:2] == ("data-cache", "validation"):
        return "validation/test library"
    if parts and parts[0] in {"runs", "reports"}:
        return "prepared workflow output"
    return "local file"


def _short_local_path(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _human_file_size(path: Path) -> str:
    try:
        size = float(path.stat().st_size)
    except OSError:
        return "unknown size"
    units = ["B", "KB", "MB", "GB", "TB"]
    unit = 0
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{size:.1f} {units[unit]}" if unit else f"{int(size)} {units[unit]}"


def _local_ligand_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    name = str(row.get("label") or row.get("path") or "").lower()
    count = int(row.get("count") or 0)
    zinc_priority = 0 if "zinc_drug_like" in name or "zinc_neutral" in name else 1
    ready_priority = 0 if row.get("prepared") or row.get("vina_ready") else 1
    return (ready_priority + zinc_priority, -count, name)


def _write_local_ligand_catalog(root: Path, rows: list[dict[str, Any]]) -> None:
    catalog = _local_ligand_catalog_path(root)
    catalog.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[str, dict[str, Any]] = {}
    curated_only = False
    if catalog.exists():
        try:
            existing = json.loads(catalog.read_text())
            curated_only = bool(existing.get("curated_only"))
            for row in existing.get("libraries", []):
                if isinstance(row, dict) and row.get("path"):
                    merged[str(row["path"])] = row
        except json.JSONDecodeError:
            merged = {}
    for row in rows:
        merged[str(row["path"])] = row
    libraries = sorted(merged.values(), key=_local_ligand_sort_key)
    catalog.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "root": str(root),
                "curated_only": curated_only,
                "notes": "Local ligand libraries discovered for terminal orchestration. User-selectable source libraries live under data-cache/ligands; prepared workflow outputs are listed when validated ligand prep metadata exists.",
                "libraries": libraries,
            },
            indent=2,
        )
        + "\n"
    )


def _local_ligand_catalog_path(root: Path) -> Path:
    return root / "data-cache" / "ligands" / "catalog" / "local_library_catalog.json"


def _existing_ligand_prep_for_input(root: Path, ligand_input: Path) -> dict[str, Any] | None:
    candidates = [
        ligand_input.parent.parent / "vina-prep" / "ligand_prep.json",
        ligand_input.parent.parent / "ligand-vina-prep" / "ligand_prep.json",
        ligand_input.parent / "ligand_prep.json",
    ]
    candidates.extend((root / "runs").glob("ligand-prep-*/vina-prep/ligand_prep.json"))
    candidates.extend((root / "runs").glob("*/ligand-vina-prep/ligand_prep.json"))
    candidates.extend((root / "reports").glob("*/ligand-vina-prep/ligand_prep.json"))
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if Path(str(data.get("input_sdf") or "")).resolve() != ligand_input:
            continue
        pdbqt_files = data.get("pdbqt_files") or []
        sample_step = max(1, len(pdbqt_files) // 10) if pdbqt_files else 1
        sampled_files = pdbqt_files[::sample_step][:10]
        if pdbqt_files and sampled_files and all(Path(p).exists() for p in sampled_files):
            return {
                "metadata_path": str(path),
                "prepared_count": int(data.get("prepared_count") or len(pdbqt_files)),
            }
    return None


def _screen_command(selections: dict[str, Any]) -> str:
    oslab = shutil.which("oslab") or "oslab"
    context_arg = (
        f" --report-context-json {shlex_quote(str(selections['report_context_json']))}"
        if selections.get("report_context_json")
        else ""
    )
    params = selections.get("docking_parameters", {})
    slurm_args = ""
    if selections.get("execution_backend") and selections.get("execution_backend") != "local":
        slurm_args += " --execution-backend slurm-export"
        slurm_args += f" --slurm-job-name {shlex_quote(str(params.get('slurm_job_name') or 'oslab-vina'))}"
        slurm_args += f" --slurm-cpus-per-task {int(params.get('slurm_cpus_per_task') or 1)}"
        if params.get("slurm_array_concurrency"):
            slurm_args += f" --slurm-array-concurrency {int(params.get('slurm_array_concurrency'))}"
        slurm_args += f" --slurm-time {shlex_quote(str(params.get('slurm_time') or '04:00:00'))}"
        if params.get("slurm_partition"):
            slurm_args += f" --slurm-partition {shlex_quote(str(params.get('slurm_partition')))}"
        if params.get("slurm_account"):
            slurm_args += f" --slurm-account {shlex_quote(str(params.get('slurm_account')))}"
        if params.get("slurm_gres"):
            slurm_args += f" --slurm-gres {shlex_quote(str(params.get('slurm_gres')))}"
        if params.get("slurm_setup_command"):
            slurm_args += f" --slurm-setup-command {shlex_quote(str(params.get('slurm_setup_command')))}"
    return (
        f"{oslab} screen small "
        f"--ligands {shlex_quote(str(selections.get('ligand_input') or '<ligands>'))} "
        f"--receptor {shlex_quote(str(selections.get('receptor_pdbqt') or '<receptor.pdbqt>'))} "
        f"--binding-site {shlex_quote(str(selections.get('binding_site_json') or '<binding_site.json>'))} "
        f"--out {shlex_quote(str(selections.get('output_dir') or '<output_dir>'))} "
        f"--max-ligands {int(selections.get('max_ligands') or 20)} "
        f"--exhaustiveness {int(selections.get('exhaustiveness') or 1)} "
        f"--seed {int(selections.get('vina_seed') or selections.get('docking_parameters', {}).get('vina_seed') or 1)} "
        f"--num-modes {int(selections.get('vina_num_modes') or selections.get('docking_parameters', {}).get('vina_num_modes') or 1)} "
        f"--docking-workers {int(selections.get('docking_workers') or 1)}"
        f"{slurm_args}"
        f"{context_arg}"
    )


def _write_report_context(selections: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    context_path = output_dir / "report_context.json"
    keys = [
        "target_gene",
        "target_source",
        "target_identifier",
        "target_match_title",
        "target_structure",
        "receptor_pdbqt",
        "binding_site_label",
        "binding_site_json",
        "ligand_source_mode",
        "download_ligand_source",
        "ligand_library_label",
        "ligand_goal_key",
        "ligand_expected_count",
        "ligand_expected_size",
        "ligand_input",
        "ligand_prepared_count",
        "execution_backend",
        "max_ligands",
        "exhaustiveness",
        "docking_workers",
        "output_dir",
    ]
    context = {key: selections.get(key) for key in keys if selections.get(key) is not None}
    context["docking_parameters"] = selections.get("docking_parameters", {})
    context_path.write_text(json.dumps(context, indent=2) + "\n")
    return context_path


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    _record_awaiting_input(prompt, default=default)
    value = input(f"{prompt}{suffix}: ").strip()
    result = value or default
    _clear_awaiting_input()
    return result


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


def _choose(prompt: str, choices: list[tuple[str, str]], default: int = 1) -> str:
    return str(_choose_row(prompt, choices, default=default))


def _choose_row(prompt: str, rows: list[tuple[Any, str]], default: int = 1) -> Any:
    if not rows:
        raise RuntimeError(f"No options available for {prompt}")
    page_size = 12
    page = max(0, min((default - 1) // page_size, (len(rows) - 1) // page_size))
    while True:
        start = page * page_size
        end = min(start + page_size, len(rows))
        print(f"\n{prompt} ({start + 1}-{end} of {len(rows)})")
        for index in range(start, end):
            _value, label = rows[index]
            marker = " [default]" if index + 1 == default else ""
            print(f"  {index + 1}. {label}{marker}")
        navigation = []
        if start > 0:
            navigation.append("p=previous")
        if end < len(rows):
            navigation.append("n=next")
        navigation_text = f" ({', '.join(navigation)})" if navigation else ""
        _record_awaiting_input(
            prompt,
            default=str(default),
            choices=[{"index": index + 1, "label": rows[index][1]} for index in range(start, end)],
            page={"start": start + 1, "end": end, "total": len(rows)},
            navigation=navigation,
        )
        raw = input(f"Select 1-{len(rows)} [{default}]{navigation_text}: ").strip().lower()
        if not raw:
            _clear_awaiting_input()
            return rows[default - 1][0]
        if raw in {"n", "next"} and end < len(rows):
            page += 1
            continue
        if raw in {"p", "prev", "previous"} and start > 0:
            page -= 1
            continue
        if raw in {"q", "quit"}:
            raise KeyboardInterrupt("selection cancelled")
        try:
            index = int(raw)
        except ValueError:
            print("Enter a number, or use n/p to move through the list.")
            continue
        if 1 <= index <= len(rows):
            _clear_awaiting_input()
            return rows[index - 1][0]
        print(f"Choose a number from 1 to {len(rows)}.")


def _record_awaiting_input(
    prompt: str,
    *,
    default: str = "",
    choices: list[dict[str, Any]] | None = None,
    page: dict[str, Any] | None = None,
    navigation: list[str] | None = None,
) -> None:
    if _ACTIVE_PROGRESS is None or _ACTIVE_PROGRESS_JSON is None:
        return
    _ACTIVE_PROGRESS["awaiting_input"] = {
        "prompt": prompt,
        "default": default,
        "choices": choices or [],
        "page": page or {},
        "navigation": navigation or [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_progress(_ACTIVE_PROGRESS_JSON, _ACTIVE_PROGRESS)


def _clear_awaiting_input() -> None:
    if _ACTIVE_PROGRESS is None or _ACTIVE_PROGRESS_JSON is None:
        return
    if "awaiting_input" in _ACTIVE_PROGRESS:
        _ACTIVE_PROGRESS.pop("awaiting_input", None)
        _write_progress(_ACTIVE_PROGRESS_JSON, _ACTIVE_PROGRESS)


def _complete(progress: dict[str, Any], step: str, progress_json: Path) -> None:
    progress["current_step"] = step
    for row in progress["steps"]:
        if row["key"] == step:
            row["status"] = "completed"
    for row in progress["steps"]:
        if row["status"] == "pending":
            row["status"] = "running"
            progress["current_step"] = row["key"]
            break
    else:
        progress["current_step"] = step
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    progress["next_block_ready"] = step == "report"
    _write_progress(progress_json, progress)


def _log_event(progress: dict[str, Any], step: str, message: str, **fields: Any) -> None:
    events = progress.setdefault("events", [])
    events.append(
        {
            "time": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "message": message,
            "fields": fields,
        }
    )
    progress["current_step"] = step
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()


def _write_progress(path: Path, progress: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(progress, indent=2) + "\n")


def _read_progress(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
