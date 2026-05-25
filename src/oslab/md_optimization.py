"""Block 3 MD pipeline: prep → simulation → interactions → MMGBSA for top ligands."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hpc import export_slurm_md_optimization
from .hpc_terminal import ask_hpc_execution, hpc_config, record_hpc_export
from .gpu import gpu_assignment_for_task, gpu_environment, resolve_gpu_plan
from .jobs import campaign_context, runtime_provenance
from .md_prep import prepare_md_system, smiles_from_pdbqt
from .md_simulation import run_md
from .md_interactions import analyze_trajectory
from .mmgbsa import estimate_mmgbsa
from .schemas import MdPrepOptions, MdSimulationOptions, MmgbsaOptions


DEFAULT_CROP_RADIUS_ANGSTROM = 15.0
DEFAULT_MAX_SOLVATED_ATOMS = 200_000

MD_NEXT_STEPS_MESSAGE = 'Look for final report in the Reports tab and use the output in "FEP".'

MD_GATE_LIGAND_RMSD_REVIEW_ANGSTROM = 3.0
MD_GATE_LIGAND_RMSD_FAIL_ANGSTROM = 5.0
MD_GATE_STABLE_CONTACT_OCCUPANCY = 0.30
MD_GATE_REVIEW_CONTACT_OCCUPANCY = 0.10
MD_GATE_MIN_STABLE_CONTACTS_PASS = 1


def run_interactive_md_optimization(root: Path, progress_json: Path | None = None) -> int:
    root = root.resolve()
    session_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    progress_json = (progress_json or root / "runs" / f"md-optimization-{session_id}" / "progress.json").resolve()
    progress = _new_interactive_progress(root, progress_json)
    dashboard_defaults = progress.get("dashboard_defaults") or {}
    progress["status"] = "running"
    progress["current_step"] = "select-inputs"
    _write_progress(progress_json, progress)

    runs = _recent_md_input_runs(root)
    default_results = str(dashboard_defaults.get("results_json") or "")
    if default_results and Path(default_results).exists() and not any(row["results_json"] == default_results for row in runs):
        runs.insert(
            0,
            {
                "name": "dashboard selection",
                "results_json": default_results,
                "created_at": "",
                "run_count": "",
                "best_ligand": "",
                "best_score": "",
            },
        )
    if not runs:
        progress["status"] = "failed"
        progress["error"] = "No docking or hit-refinement result tables were found."
        _write_progress(progress_json, progress)
        print("No docking or hit-refinement result tables were found.")
        return 1

    print("\nMD and Optimization")
    print("Choose a completed docking or hit-refinement result table, then select MD settings.\n")
    chosen = _choose_row(
        "Input result tables",
        [
            (
                row,
                f"{row['name']} | {row.get('created_at') or 'unknown date'} | best {row.get('best_ligand') or ''} {row.get('best_score') or ''} | {row['results_json']}",
            )
            for row in runs
        ],
    )
    results_json = Path(chosen["results_json"])
    progress["selections"].update(
        {
            "source_run_label": chosen.get("name"),
            "results_json": str(results_json),
            "source_best_ligand": chosen.get("best_ligand"),
            "source_best_score": chosen.get("best_score"),
            "source_run_count": chosen.get("run_count"),
        }
    )
    _set_step_status(progress, "select-inputs", "running")
    _write_progress(progress_json, progress)

    top_n = _ask_int("Top ligands for MD", default=int(dashboard_defaults.get("top_n") or 3), minimum=1)
    ph = float(_ask("pH", default=str(dashboard_defaults.get("ph") or "7.4")))
    water_padding_nm = float(_ask("Water padding (nm)", default=str(dashboard_defaults.get("water_padding_nm") or "1.2")))
    ionic_strength_m = float(_ask("Ionic strength (M)", default=str(dashboard_defaults.get("ionic_strength_m") or "0.15")))
    temperature_k = float(_ask("Temperature (K)", default=str(dashboard_defaults.get("temperature_k") or "300")))
    minimization_steps = _ask_int("Minimization steps", default=int(dashboard_defaults.get("minimization_steps") or 1000), minimum=0)
    smirnoff_forcefield = _ask("SMIRNOFF force field", default=str(dashboard_defaults.get("smirnoff_forcefield") or "openff-2.2.0"))
    production_ns = float(_ask("Production time (ns)", default=str(dashboard_defaults.get("production_ns") or "1.0")))
    nvt_ns = float(_ask("NVT equilibration (ns)", default=str(dashboard_defaults.get("nvt_ns") or "0.1")))
    npt_ns = float(_ask("NPT equilibration (ns)", default=str(dashboard_defaults.get("npt_ns") or "0.1")))
    timestep_fs = float(_ask("Timestep (fs)", default=str(dashboard_defaults.get("timestep_fs") or "2.0")))
    n_frames = _ask_int("MMGBSA frames to sample", default=int(dashboard_defaults.get("n_frames") or 50), minimum=1)
    crop_radius = float(_ask("Crop radius around ligand (angstrom; 0 disables)", default=str(dashboard_defaults.get("crop_radius_angstrom") or "15")))
    max_atoms = _ask_int("Max solvated atoms", default=int(dashboard_defaults.get("max_solvated_atoms") or DEFAULT_MAX_SOLVATED_ATOMS), minimum=1000)
    output_default = dashboard_defaults.get("output_dir") or root / "reports" / f"md-optimization-{session_id}"
    output_dir = Path(_ask("Output directory", default=str(output_default)))

    prep_options = MdPrepOptions(
        ph=ph,
        water_padding_nm=water_padding_nm,
        ionic_strength_m=ionic_strength_m,
        temperature_k=temperature_k,
        minimization_steps=minimization_steps,
        smirnoff_forcefield=smirnoff_forcefield,
    )
    sim_options = MdSimulationOptions(
        timestep_fs=timestep_fs,
        temperature_k=temperature_k,
        nvt_equilibration_ns=nvt_ns,
        npt_equilibration_ns=npt_ns,
        production_ns=production_ns,
    )
    mmgbsa_options = MmgbsaOptions(n_frames=n_frames, smirnoff_forcefield=smirnoff_forcefield)
    progress["selections"].update(
        {
            "top_n": top_n,
            "output_dir": str(output_dir),
            "prep_options": prep_options.model_dump(),
            "sim_options": sim_options.model_dump(),
            "mmgbsa_options": mmgbsa_options.model_dump(),
            "crop_radius_angstrom": crop_radius,
            "max_solvated_atoms": max_atoms,
            "md_started_message": MD_NEXT_STEPS_MESSAGE,
        }
    )
    _write_progress(progress_json, progress)

    execution = ask_hpc_execution(
        root=root,
        progress=progress,
        progress_json=progress_json,
        block="md-optimization",
        local_label="This computer (local OpenMM run)",
        default_time="24:00:00",
        default_cpus=4,
        default_gres="gpu:1",
    )
    if execution["backend"] != "local":
        export = export_slurm_md_optimization(
            root=root,
            results_json=results_json,
            output_dir=output_dir,
            top_n=top_n,
            progress_json=progress_json,
            ph=ph,
            water_padding_nm=water_padding_nm,
            ionic_strength_m=ionic_strength_m,
            temperature_k=temperature_k,
            minimization_steps=minimization_steps,
            smirnoff_forcefield=smirnoff_forcefield,
            timestep_fs=timestep_fs,
            nvt_ns=nvt_ns,
            npt_ns=npt_ns,
            production_ns=production_ns,
            n_frames=n_frames,
            crop_radius_angstrom=crop_radius,
            max_solvated_atoms=max_atoms,
            config=hpc_config(execution, default_job_name="oslab-md", default_time="24:00:00", default_cpus=4, default_gres="gpu:1"),
        )
        record_hpc_export(progress, progress_json, export, block="md-optimization")
        print("\nCluster export created.")
        print(f"Submit on the cluster with: cd '{export.output_dir}' && sbatch submit.slurm")
        print("The dashboard will show progress/results after the cluster writes files into the shared workspace.")
        return 0

    print(f"\n{MD_NEXT_STEPS_MESSAGE}")
    return run_md_optimization(
        root=root,
        progress_json=progress_json,
        results_json=results_json,
        output_dir=output_dir,
        top_n=top_n,
        prep_options=prep_options,
        sim_options=sim_options,
        mmgbsa_options=mmgbsa_options,
        crop_radius_angstrom=crop_radius,
        max_solvated_atoms=max_atoms,
    )


def run_md_optimization(
    root: Path,
    progress_json: Path,
    results_json: Path,
    output_dir: Path,
    top_n: int = 3,
    ligand_names: list[str] | None = None,
    prep_options: MdPrepOptions | None = None,
    sim_options: MdSimulationOptions | None = None,
    mmgbsa_options: MmgbsaOptions | None = None,
    crop_radius_angstrom: float = DEFAULT_CROP_RADIUS_ANGSTROM,
    max_solvated_atoms: int = DEFAULT_MAX_SOLVATED_ATOMS,
    gpu_mode: str = "auto",
    gpu_devices: str = "",
    gpu_jobs_per_device: int = 1,
    require_gpu: bool = False,
) -> int:
    """Run the full MD Block 3 pipeline for top ligands from a docking/hit-refinement results JSON.

    Chains md-prep → md-simulation → md-interactions → mmgbsa for each selected ligand.
    Writes a progress JSON throughout and a final markdown report with AI commentary.
    """
    prep_options = prep_options or MdPrepOptions()
    sim_options = sim_options or MdSimulationOptions()
    mmgbsa_options = mmgbsa_options or MmgbsaOptions()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = _select_ligands_for_md(results_json, top_n=top_n, ligand_names=ligand_names)
    if not selected:
        _write_progress(progress_json, {
            "started_at": _now(), "updated_at": _now(), "status": "failed",
            "current_step": "select-inputs",
            "steps": [{"key": "select-inputs", "status": "failed"}],
            "events": [{"time": _now(), "message": f"No valid ligands found in {results_json}"}],
        })
        print(f"ERROR: No valid ligands found in {results_json}", file=sys.stderr)
        return 1

    selected_names = [str(row.get("ligand") or "") for row in selected]
    try:
        gpu_plan = resolve_gpu_plan(
            task_count=len(selected),
            task_labels=selected_names,
            gpu_mode=gpu_mode,
            gpu_devices=gpu_devices,
            jobs_per_device=gpu_jobs_per_device,
            require_gpu=require_gpu,
        )
    except Exception as exc:
        _write_progress(progress_json, {
            "started_at": _now(), "updated_at": _now(), "status": "failed",
            "current_step": "gpu-discovery",
            "steps": [{"key": "gpu-discovery", "status": "failed"}],
            "events": [{"time": _now(), "message": f"GPU discovery/assignment failed: {exc}"}],
        })
        print(f"ERROR: GPU discovery/assignment failed: {exc}", file=sys.stderr)
        return 1
    progress: dict[str, Any] = {
        "started_at": _now(),
        "updated_at": _now(),
        "job_id": progress_json.parent.name.removeprefix("md-optimization-"),
        **campaign_context(),
        "status": "running",
        "current_step": "select-inputs",
        "current_ligand": "",
        "steps": [
            {"key": "select-inputs", "status": "completed"},
            {"key": "md-prep", "status": "pending"},
            {"key": "md-simulation", "status": "pending"},
            {"key": "md-interactions", "status": "pending"},
            {"key": "mmgbsa", "status": "pending"},
            {"key": "report", "status": "pending"},
        ],
        "ligand_status": {
            name: {"prep": "pending", "simulation": "pending", "interactions": "pending", "mmgbsa": "pending"}
            for name in selected_names
        },
        "ligand_results": {},
        "md_gate_results": {},
        "ligand_progress": {
            "completed_ligands": 0,
            "total_ligands": len(selected),
            "current_ligand": "",
            "current_stage": "",
        },
        "selections": {
            "results_json": str(results_json),
            "output_dir": str(output_dir),
            "top_n": top_n,
            "selected_ligands": selected_names,
            "prep_options": prep_options.model_dump(),
            "sim_options": sim_options.model_dump(),
            "mmgbsa_options": mmgbsa_options.model_dump(),
            "crop_radius_angstrom": crop_radius_angstrom,
            "max_solvated_atoms": max_solvated_atoms,
            "gpu_plan": gpu_plan,
            "md_gate_policy": _md_gate_policy(),
            "block4_filter": "Only MD gate pass ligands advance to Block 4; pass ligands retain Block 2 rank order.",
        },
        "provenance": runtime_provenance(
            forcefields={
                "protein": "amber14-all.xml",
                "water": "amber14/tip3pfb.xml",
                "ligand": prep_options.smirnoff_forcefield,
                "mmgbsa_ligand": mmgbsa_options.smirnoff_forcefield,
            },
            structures={"results_json": str(results_json)},
        ),
        "events": [{"time": _now(), "message": f"Selected {len(selected)} ligands: {', '.join(selected_names[:5])}{'...' if len(selected_names) > 5 else ''}"}],
        "notes": ["MD pipeline runs automatically. The dashboard monitors this progress JSON."],
    }
    if gpu_plan.get("selected_devices"):
        labels = ", ".join(f"{row.get('cuda_visible_devices')} ({row.get('name')})" for row in gpu_plan.get("selected_devices", []))
        _log_event(progress, f"GPU plan: using CUDA device(s) {labels}; jobs/device={gpu_plan.get('jobs_per_device')}")
    else:
        _log_event(progress, f"GPU plan: using OpenMM platform {gpu_plan.get('openmm_platform')}")
    for warning in gpu_plan.get("warnings", []):
        _log_event(progress, f"GPU plan warning: {warning}")
    _write_progress(progress_json, progress)

    for ligand_idx, row in enumerate(selected, start=1):
        ligand = str(row.get("ligand") or "")
        gpu_assignment = gpu_assignment_for_task(gpu_plan, ligand_idx - 1)
        ligand_md_dir = output_dir / ligand
        ligand_md_dir.mkdir(parents=True, exist_ok=True)
        if gpu_assignment and gpu_assignment.get("cuda_visible_devices"):
            progress["ligand_status"][ligand]["gpu"] = {
                "cuda_visible_devices": gpu_assignment.get("cuda_visible_devices"),
                "openmm_device_index": gpu_assignment.get("openmm_device_index"),
                "gpu_name": gpu_assignment.get("gpu_name"),
            }
            _log_event(
                progress,
                f"{ligand}: assigned CUDA_VISIBLE_DEVICES={gpu_assignment.get('cuda_visible_devices')} "
                f"(OpenMM DeviceIndex {gpu_assignment.get('openmm_device_index')})",
            )
        else:
            progress["ligand_status"][ligand]["gpu"] = {"openmm_platform": gpu_plan.get("openmm_platform")}

        receptor_pdbqt, docked_pdbqt, ligand_pdbqt_path = _resolve_pdbqts(row, results_json.parent)
        if not receptor_pdbqt or not docked_pdbqt:
            progress["ligand_status"][ligand]["prep"] = "failed"
            _mark_ligand_downstream_skipped(progress, ligand)
            _record_md_gate(
                progress,
                ligand,
                _classify_md_gate(
                    row=row,
                    fallback_rank=ligand_idx,
                    ligand_status=progress["ligand_status"][ligand],
                    failure_reason="could not resolve receptor or docked PDBQT paths",
                ),
            )
            _log_event(progress, f"SKIP {ligand}: could not resolve receptor or docked PDBQT paths")
            _write_progress(progress_json, progress)
            continue

        smiles = _resolve_smiles(row, docked_pdbqt, ligand_pdbqt_path)
        if not smiles:
            progress["ligand_status"][ligand]["prep"] = "failed"
            _mark_ligand_downstream_skipped(progress, ligand)
            _record_md_gate(
                progress,
                ligand,
                _classify_md_gate(
                    row=row,
                    fallback_rank=ligand_idx,
                    ligand_status=progress["ligand_status"][ligand],
                    failure_reason="no SMILES available for MD preparation",
                ),
            )
            _log_event(progress, f"SKIP {ligand}: no SMILES available — add a REMARK SMILES line to the PDBQT or include smiles in results JSON")
            _write_progress(progress_json, progress)
            continue

        vina_score = _parse_float(row.get("best_score") or row.get("score"))
        progress["current_ligand"] = ligand
        progress["ligand_progress"]["current_ligand"] = ligand
        _write_progress(progress_json, progress)

        # Stage 1: MD Prep
        print(f"[{ligand_idx}/{len(selected)}] {ligand}: MD prep ...", flush=True)
        progress["current_step"] = "md-prep"
        progress["ligand_status"][ligand]["prep"] = "running"
        progress["ligand_progress"]["current_stage"] = "md-prep"
        _set_step_status(progress, "md-prep", "running")
        _write_progress(progress_json, progress)

        prep_dir = ligand_md_dir / "prep"
        prep_dir.mkdir(parents=True, exist_ok=True)
        protein_pdb_arg: Path | None = None
        if crop_radius_angstrom and crop_radius_angstrom > 0:
            try:
                cropped_pdb = prep_dir / "receptor_cropped.pdb"
                crop_info = _crop_receptor_around_ligand(
                    receptor_pdbqt=receptor_pdbqt,
                    docked_pdbqt=docked_pdbqt,
                    output_pdb=cropped_pdb,
                    radius_angstrom=crop_radius_angstrom,
                )
                protein_pdb_arg = cropped_pdb
                _log_event(
                    progress,
                    f"{ligand}: cropped receptor to {crop_info['kept_residues']}/{crop_info['total_residues']} "
                    f"residues covering {crop_info.get('contact_residues', crop_info['kept_residues'])} contact residues "
                    f"within {crop_radius_angstrom} Å of ligand "
                    f"(estimated solvated atoms ≈ {crop_info['estimated_atoms']:,})"
                )
                if crop_info["estimated_atoms"] > max_solvated_atoms:
                    raise RuntimeError(
                        f"Even after cropping, the solvated system is estimated at "
                        f"{crop_info['estimated_atoms']:,} atoms (budget {max_solvated_atoms:,}). "
                        f"Reduce crop_radius_angstrom or water_padding_nm, or trim the receptor."
                    )
            except Exception as exc:
                progress["ligand_status"][ligand]["prep"] = "failed"
                _mark_ligand_downstream_skipped(progress, ligand)
                _record_md_gate(
                    progress,
                    ligand,
                    _classify_md_gate(
                        row=row,
                        fallback_rank=ligand_idx,
                        ligand_status=progress["ligand_status"][ligand],
                        failure_reason=f"receptor cropping failed: {exc}",
                    ),
                )
                _log_event(progress, f"{ligand} receptor cropping failed: {exc}")
                _write_progress(progress_json, progress)
                continue
        try:
            with gpu_environment(gpu_plan, gpu_assignment):
                prep_record = prepare_md_system(
                    receptor_pdbqt=receptor_pdbqt,
                    docked_ligand_pdbqt=docked_pdbqt,
                    ligand_smiles=smiles,
                    output_dir=prep_dir,
                    options=prep_options,
                    protein_pdb=protein_pdb_arg,
                )
        except Exception as exc:
            progress["ligand_status"][ligand]["prep"] = "failed"
            _mark_ligand_downstream_skipped(progress, ligand)
            _record_md_gate(
                progress,
                ligand,
                _classify_md_gate(
                    row=row,
                    fallback_rank=ligand_idx,
                    ligand_status=progress["ligand_status"][ligand],
                    failure_reason=f"MD preparation failed: {exc}",
                ),
            )
            _log_event(progress, f"{ligand} prep failed: {exc}")
            _write_progress(progress_json, progress)
            continue

        progress["ligand_status"][ligand]["prep"] = "completed"
        _set_step_status(progress, "md-prep", "completed")
        _log_event(progress, f"{ligand}: MD prep done")
        _write_progress(progress_json, progress)

        # Stage 2: MD Simulation
        print(f"[{ligand_idx}/{len(selected)}] {ligand}: MD simulation ({sim_options.production_ns} ns) ...", flush=True)
        progress["current_step"] = "md-simulation"
        progress["ligand_status"][ligand]["simulation"] = "running"
        progress["ligand_progress"]["current_stage"] = "md-simulation"
        _set_step_status(progress, "md-simulation", "running")
        _write_progress(progress_json, progress)

        sim_dir = ligand_md_dir / "simulation"
        try:
            def _simulation_progress(update: dict[str, Any]) -> None:
                phase = str(update.get("phase") or "simulation")
                percent = update.get("percent")
                stage = f"md-simulation {phase}"
                if percent is not None:
                    stage = f"{stage} {percent}%"
                progress["current_step"] = "md-simulation"
                progress["ligand_progress"]["current_stage"] = stage
                progress["ligand_progress"]["simulation_phase"] = phase
                progress["ligand_progress"]["simulation_completed_steps"] = update.get("completed_steps")
                progress["ligand_progress"]["simulation_total_steps"] = update.get("total_steps")
                progress["ligand_progress"]["simulation_percent"] = percent
                _write_progress(progress_json, progress)

            with gpu_environment(gpu_plan, gpu_assignment):
                sim_record = run_md(
                    topology_pdb=prep_record.topology_pdb,
                    system_xml=prep_record.system_xml,
                    output_dir=str(sim_dir),
                    options=sim_options,
                    progress_callback=_simulation_progress,
                )
        except Exception as exc:
            progress["ligand_status"][ligand]["simulation"] = "failed"
            for key in ("interactions", "mmgbsa"):
                if progress["ligand_status"][ligand].get(key) in {None, "", "pending"}:
                    progress["ligand_status"][ligand][key] = "skipped"
            _record_md_gate(
                progress,
                ligand,
                _classify_md_gate(
                    row=row,
                    fallback_rank=ligand_idx,
                    ligand_status=progress["ligand_status"][ligand],
                    failure_reason=f"MD simulation failed: {exc}",
                ),
            )
            _log_event(progress, f"{ligand} simulation failed: {exc}")
            _write_progress(progress_json, progress)
            continue

        progress["ligand_status"][ligand]["simulation"] = "completed"
        _log_event(progress, f"{ligand}: MD simulation done")
        _write_progress(progress_json, progress)

        # Stage 3: MD Interactions
        print(f"[{ligand_idx}/{len(selected)}] {ligand}: ProLIF interactions ...", flush=True)
        progress["current_step"] = "md-interactions"
        progress["ligand_status"][ligand]["interactions"] = "running"
        progress["ligand_progress"]["current_stage"] = "md-interactions"
        _set_step_status(progress, "md-interactions", "running")
        _write_progress(progress_json, progress)

        interactions_dir = ligand_md_dir / "interactions"
        interactions_record = None
        try:
            interactions_record = analyze_trajectory(
                topology_pdb=sim_record.topology_pdb,
                trajectory_dcd=sim_record.trajectory_dcd,
                output_dir=str(interactions_dir),
            )
            progress["ligand_status"][ligand]["interactions"] = "completed"
            _log_event(progress, f"{ligand}: ProLIF interactions done ({interactions_record.n_frames_analyzed} frames)")
        except Exception as exc:
            progress["ligand_status"][ligand]["interactions"] = "failed"
            _log_event(progress, f"{ligand} interactions failed: {exc}")
        _write_progress(progress_json, progress)

        # Stage 4: MMGBSA
        print(f"[{ligand_idx}/{len(selected)}] {ligand}: MMGBSA ...", flush=True)
        progress["current_step"] = "mmgbsa"
        progress["ligand_status"][ligand]["mmgbsa"] = "running"
        progress["ligand_progress"]["current_stage"] = "mmgbsa"
        _set_step_status(progress, "mmgbsa", "running")
        _write_progress(progress_json, progress)

        mmgbsa_dir = ligand_md_dir / "mmgbsa"
        mmgbsa_record = None
        try:
            with gpu_environment(gpu_plan, gpu_assignment):
                mmgbsa_record = estimate_mmgbsa(
                    topology_pdb=sim_record.topology_pdb,
                    trajectory_dcd=sim_record.trajectory_dcd,
                    output_dir=str(mmgbsa_dir),
                    options=mmgbsa_options,
                )
            progress["ligand_status"][ligand]["mmgbsa"] = "completed"
            _log_event(progress, f"{ligand}: MMGBSA done — ΔG = {mmgbsa_record.mean_ddg_kcal:.2f} ± {mmgbsa_record.std_ddg_kcal:.2f} kcal/mol")
        except Exception as exc:
            progress["ligand_status"][ligand]["mmgbsa"] = "failed"
            _log_event(progress, f"{ligand} MMGBSA failed: {exc}")
        _write_progress(progress_json, progress)

        rmsd_mean: float | None = None
        if sim_record.rmsd_json:
            try:
                rmsd_data = json.loads(Path(sim_record.rmsd_json).read_text())
                rmsds = [float(r["rmsd_angstrom"]) for r in rmsd_data if r.get("rmsd_angstrom") is not None]
                rmsd_mean = sum(rmsds) / len(rmsds) if rmsds else None
            except Exception:
                pass

        top_interactions = interactions_record.top_interactions[:10] if interactions_record else []
        gate = _classify_md_gate(
            row=row,
            fallback_rank=ligand_idx,
            ligand_status=progress["ligand_status"][ligand],
            rmsd_mean=rmsd_mean,
            top_interactions=top_interactions,
            mmgbsa_mean=mmgbsa_record.mean_ddg_kcal if mmgbsa_record else None,
            mmgbsa_std=mmgbsa_record.std_ddg_kcal if mmgbsa_record else None,
        )
        progress["ligand_results"][ligand] = {
            "vina_score": vina_score,
            "mean_ddg_kcal": mmgbsa_record.mean_ddg_kcal if mmgbsa_record else None,
            "std_ddg_kcal": mmgbsa_record.std_ddg_kcal if mmgbsa_record else None,
            "ligand_rmsd_mean_angstrom": rmsd_mean,
            "top_interactions": top_interactions,
            "prep_record": str(prep_dir / "prep_record.json"),
            "simulation_record": str(sim_dir / "simulation_record.json"),
            "interactions_record": str(interactions_dir / "md_interactions_record.json") if interactions_record else None,
            "mmgbsa_record": str(mmgbsa_dir / "mmgbsa_record.json") if mmgbsa_record else None,
            "gpu_assignment": gpu_assignment or {},
            "block2_rank": gate["block2_rank"],
            "block2_score": gate["block2_score"],
            "md_gate": gate,
            "md_gate_status": gate["gate_status"],
            "md_gate_reasons": gate["gate_reasons"],
        }
        _record_md_gate(progress, ligand, gate)
        _log_event(progress, f"{ligand}: MD gate {gate['gate_status']} — {'; '.join(gate['gate_reasons'])}")
        progress["ligand_progress"]["completed_ligands"] = ligand_idx
        _write_progress(progress_json, progress)

    _set_final_step_statuses(progress)

    print("Generating MD optimization report ...", flush=True)
    progress["current_step"] = "report"
    _set_step_status(progress, "report", "running")
    _write_progress(progress_json, progress)

    report_path = _write_md_report(output_dir, selected, progress["ligand_results"], progress.get("md_gate_results", {}))
    progress["selections"]["md_report"] = str(report_path)
    _log_event(progress, f"Report written: {report_path}")

    _set_step_status(progress, "report", "completed")
    progress["status"] = "completed" if progress["ligand_results"] else "failed"
    progress["total_items"] = len(selected)
    progress["completed_items"] = len(progress["ligand_results"])
    progress["failed_items"] = max(0, len(selected) - len(progress["ligand_results"]))
    progress["md_gate_summary"] = _md_gate_summary(progress.get("md_gate_results", {}))
    progress["next_block_ready"] = progress["status"] == "completed" and progress["md_gate_summary"].get("pass", 0) > 0
    if not progress["ligand_results"]:
        _log_event(progress, "MD optimization failed: no ligands completed MD preparation/simulation.")
    progress["finished_at"] = _now()
    _write_progress(progress_json, progress)

    print(f"\nMD optimization {progress['status']}. Report: {report_path}", flush=True)
    return 0 if progress["ligand_results"] else 1


def _select_ligands_for_md(
    results_json: Path,
    top_n: int,
    ligand_names: list[str] | None,
) -> list[dict[str, Any]]:
    rows = json.loads(results_json.read_text())
    if not isinstance(rows, list):
        return []
    valid = [dict(row) for row in rows if isinstance(row, dict) and row.get("ligand")]

    if valid and "composite_score" in valid[0]:
        valid.sort(key=lambda r: -float(r.get("composite_score") or 0))
    else:
        valid.sort(key=lambda r: float(r.get("best_score") or r.get("score") or 0))

    if ligand_names:
        name_set = set(ligand_names)
        valid = [r for r in valid if str(r.get("ligand") or "") in name_set]
    else:
        # Deduplicate by ligand name while preserving order by score
        seen = set()
        deduped = []
        for r in valid:
            ligand_name = str(r.get("ligand") or "")
            if ligand_name not in seen:
                seen.add(ligand_name)
                deduped.append(r)
                if len(deduped) >= top_n:
                    break
        valid = deduped

    return valid


def _md_gate_policy() -> dict[str, Any]:
    return {
        "purpose": "Use MD as structural quality control, not as a primary reranker.",
        "block4_behavior": "Only pass ligands advance to Block 4; pass ligands retain Block 2 rank order.",
        "pass": (
            "MD preparation/simulation completed, ligand remains in the intended pocket, "
            "and at least one protein-ligand contact persists at the stable occupancy threshold."
        ),
        "review": (
            "Simulation completed but pose stability or interaction evidence is borderline or incomplete; "
            "inspect manually before advancing outside the automated Block 4 path."
        ),
        "fail": (
            "Setup/simulation failed, ligand moved substantially away from the starting pose, "
            "or no meaningful protein-ligand contacts persisted."
        ),
        "ligand_rmsd_review_angstrom": MD_GATE_LIGAND_RMSD_REVIEW_ANGSTROM,
        "ligand_rmsd_fail_angstrom": MD_GATE_LIGAND_RMSD_FAIL_ANGSTROM,
        "stable_contact_occupancy": MD_GATE_STABLE_CONTACT_OCCUPANCY,
        "review_contact_occupancy": MD_GATE_REVIEW_CONTACT_OCCUPANCY,
        "min_stable_contacts_pass": MD_GATE_MIN_STABLE_CONTACTS_PASS,
        "mmgbsa_policy": "MMGBSA is retained as an annotation and is not used as a hard pass/fail criterion.",
    }


def _block2_rank_for_row(row: dict[str, Any], fallback_rank: int) -> int:
    for key in ("block2_rank", "composite_rank", "initial_refinement_rank", "rank"):
        value = row.get(key)
        if value is None:
            continue
        try:
            rank = int(float(value))
        except (TypeError, ValueError):
            continue
        if rank > 0:
            return rank
    return fallback_rank


def _block2_score_for_row(row: dict[str, Any]) -> float | None:
    for key in ("block2_score", "composite_score", "best_score", "score"):
        value = _parse_float(row.get(key))
        if value is not None:
            return value
    return None


def _interaction_gate_metrics(top_interactions: list[dict[str, Any]] | None) -> dict[str, Any]:
    max_occupancy = 0.0
    stable_contacts: list[dict[str, Any]] = []
    review_contacts: list[dict[str, Any]] = []
    for interaction in top_interactions or []:
        occupancy = _parse_float(interaction.get("occupancy") or interaction.get("occupancy_fraction"))
        if occupancy is None:
            continue
        max_occupancy = max(max_occupancy, occupancy)
        if occupancy >= MD_GATE_STABLE_CONTACT_OCCUPANCY:
            stable_contacts.append(interaction)
        elif occupancy >= MD_GATE_REVIEW_CONTACT_OCCUPANCY:
            review_contacts.append(interaction)
    return {
        "stable_contact_count": len(stable_contacts),
        "review_contact_count": len(review_contacts),
        "max_contact_occupancy": round(max_occupancy, 4),
        "stable_contacts": stable_contacts[:10],
    }


def _classify_md_gate(
    *,
    row: dict[str, Any],
    fallback_rank: int,
    ligand_status: dict[str, Any],
    rmsd_mean: float | None = None,
    top_interactions: list[dict[str, Any]] | None = None,
    mmgbsa_mean: float | None = None,
    mmgbsa_std: float | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    interaction_metrics = _interaction_gate_metrics(top_interactions)
    reasons: list[str] = []
    gate_status = "pass"

    if failure_reason:
        gate_status = "fail"
        reasons.append(failure_reason)
    elif ligand_status.get("prep") != "completed":
        gate_status = "fail"
        reasons.append("MD preparation did not complete")
    elif ligand_status.get("simulation") != "completed":
        gate_status = "fail"
        reasons.append("MD simulation did not complete")
    else:
        if rmsd_mean is None:
            gate_status = "review"
            reasons.append("ligand RMSD was unavailable")
        elif rmsd_mean >= MD_GATE_LIGAND_RMSD_FAIL_ANGSTROM:
            gate_status = "fail"
            reasons.append(
                f"ligand RMSD {rmsd_mean:.2f} Å exceeds fail threshold "
                f"{MD_GATE_LIGAND_RMSD_FAIL_ANGSTROM:.1f} Å"
            )
        elif rmsd_mean >= MD_GATE_LIGAND_RMSD_REVIEW_ANGSTROM:
            gate_status = "review"
            reasons.append(
                f"ligand RMSD {rmsd_mean:.2f} Å exceeds review threshold "
                f"{MD_GATE_LIGAND_RMSD_REVIEW_ANGSTROM:.1f} Å"
            )

        stable_count = int(interaction_metrics["stable_contact_count"])
        max_occupancy = float(interaction_metrics["max_contact_occupancy"])
        if ligand_status.get("interactions") != "completed":
            if gate_status == "pass":
                gate_status = "review"
            reasons.append("interaction analysis did not complete")
        elif stable_count < MD_GATE_MIN_STABLE_CONTACTS_PASS:
            if max_occupancy < MD_GATE_REVIEW_CONTACT_OCCUPANCY:
                gate_status = "fail"
                reasons.append("no persistent protein-ligand contact was detected")
            elif gate_status != "fail":
                gate_status = "review"
                reasons.append("protein-ligand contacts were present but below stable occupancy threshold")

        if ligand_status.get("mmgbsa") != "completed":
            reasons.append("MMGBSA unavailable; not used for MD gate")

    if not reasons:
        reasons.append("completed MD with stable pocket contacts")

    return {
        "gate_status": gate_status,
        "block2_rank": _block2_rank_for_row(row, fallback_rank),
        "block2_score": _block2_score_for_row(row),
        "gate_reasons": reasons,
        "gate_metrics": {
            "ligand_rmsd_mean_angstrom": rmsd_mean,
            "mean_ddg_kcal": mmgbsa_mean,
            "std_ddg_kcal": mmgbsa_std,
            **interaction_metrics,
        },
        "gate_policy": _md_gate_policy(),
    }


def _record_md_gate(progress: dict[str, Any], ligand: str, gate: dict[str, Any]) -> None:
    progress.setdefault("md_gate_results", {})[ligand] = gate
    progress.setdefault("ligand_status", {}).setdefault(ligand, {})["md_gate"] = gate.get("gate_status")


def _md_gate_summary(md_gate_results: dict[str, Any]) -> dict[str, int]:
    summary = {"pass": 0, "review": 0, "fail": 0, "unclassified": 0}
    for gate in (md_gate_results or {}).values():
        status = ""
        if isinstance(gate, dict):
            status = str(gate.get("gate_status") or gate.get("status") or "").lower()
        if status in summary:
            summary[status] += 1
        else:
            summary["unclassified"] += 1
    return summary


def _resolve_pdbqts(row: dict[str, Any], base_dir: Path) -> tuple[Path | None, Path | None, Path | None]:
    receptor = _try_path(row.get("receptor_pdbqt"))
    docked = _try_path(row.get("output_pdbqt") or row.get("best_output_pdbqt"))
    ligand_pdbqt = _try_path(row.get("ligand_pdbqt"))

    if not receptor or not docked:
        for run_key in ("run_json", "best_run_json"):
            run_json_path = _try_path(row.get(run_key))
            if run_json_path and run_json_path.exists():
                try:
                    run_data = json.loads(run_json_path.read_text())
                    if not receptor:
                        receptor = _try_path(run_data.get("receptor_pdbqt"))
                    if not docked:
                        docked = _try_path(run_data.get("output_pdbqt"))
                    if not ligand_pdbqt:
                        ligand_pdbqt = _try_path(run_data.get("ligand_pdbqt"))
                except (json.JSONDecodeError, OSError):
                    pass
                break

    return receptor, docked, ligand_pdbqt


def _resolve_smiles(row: dict[str, Any], docked_pdbqt: Path | None, ligand_pdbqt: Path | None) -> str:
    for key in ("smiles", "canonical_smiles", "isomeric_smiles"):
        v = str(row.get(key) or "").strip()
        if v:
            return v
    for pdbqt in (ligand_pdbqt, docked_pdbqt):
        if pdbqt and pdbqt.exists():
            smiles = smiles_from_pdbqt(pdbqt)
            if smiles:
                return smiles
    return ""


def _write_md_report(
    output_dir: Path,
    selected: list[dict[str, Any]],
    ligand_results: dict[str, Any],
    md_gate_results: dict[str, Any] | None = None,
) -> Path:
    report_dir = output_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "md_optimization_report.md"

    md_gate_results = md_gate_results or {}
    ranked = sorted(
        enumerate(selected, start=1),
        key=lambda item: (_block2_rank_for_row(item[1], item[0]), item[0]),
    )
    gate_summary = _md_gate_summary(md_gate_results)

    lines = [
        "# MD and Optimization Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary",
        "",
        f"Block 3 MD pipeline (SMIRNOFF parametrization, OpenMM MD, ProLIF fingerprinting, MMGBSA ΔG) completed for {len(ligand_results)}/{len(selected)} ligand(s).",
        f"MD structural gate calls: pass {gate_summary['pass']}, review {gate_summary['review']}, fail {gate_summary['fail']}.",
        "Block 4 consumes only MD gate pass ligands, preserving the Block 2 composite-rank order.",
        "",
        "| Block 2 Rank | Ligand | MD Gate | Vina Score (kcal/mol) | ΔG mean (kcal/mol) | RMSD mean (Å) | Stable contacts | Reason |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    if not ligand_results:
        lines.extend([
            "",
            "**No MD/MMGBSA values were generated because no selected ligand completed MD preparation.**",
            "",
        ])
    for fallback_rank, row in ranked:
        ligand = str(row.get("ligand") or "")
        r = ligand_results.get(ligand) or {}
        gate = md_gate_results.get(ligand) or r.get("md_gate") or {}
        vina_score = r.get("vina_score")
        if vina_score is None:
            vina_score = _parse_float(row.get("best_score") or row.get("score"))
        vina = f"{vina_score:.3f}" if vina_score is not None else "—"
        ddg = f"{r['mean_ddg_kcal']:.2f}" if r.get("mean_ddg_kcal") is not None else "—"
        rmsd = f"{r['ligand_rmsd_mean_angstrom']:.2f}" if r.get("ligand_rmsd_mean_angstrom") is not None else "—"
        gate_status = str(gate.get("gate_status") or r.get("md_gate_status") or "unclassified")
        metrics = gate.get("gate_metrics") or {}
        stable_contacts = metrics.get("stable_contact_count", "—")
        reasons = "; ".join(str(x) for x in (gate.get("gate_reasons") or r.get("md_gate_reasons") or [])) or "—"
        block2_rank = gate.get("block2_rank") or r.get("block2_rank") or _block2_rank_for_row(row, fallback_rank)
        lines.append(f"| {block2_rank} | {ligand} | {gate_status} | {vina} | {ddg} | {rmsd} | {stable_contacts} | {reasons} |")

    lines.extend([
        "",
        "## Methodology",
        "",
        "- **MD Preparation**: PDBFixer protonation (pH 7.4), AMBER14 protein + GAFF2 ligand via SMIRNOFF (openff-2.2.0 Sage), TIP3P-FB water (1.2 nm padding), 0.15 M NaCl, energy minimization.",
        "- **MD Simulation**: OpenMM 8.1.5 — 100 ps NVT equilibration → 100 ps NPT equilibration → production NPT. Langevin thermostat at 300 K, Monte Carlo barostat at 1 atm, 2 fs timestep.",
        "- **Trajectory Analysis**: ProLIF 2.x protein-ligand interaction fingerprinting via MDAnalysis — H-bond, hydrophobic, π-stacking, cation-π, anionic, van der Waals contact occupancies per residue.",
        "- **MMGBSA**: GB-OBC2 implicit solvent. ΔG_bind ≈ ⟨E_complex⟩ − ⟨E_protein⟩ − ⟨E_ligand⟩. For relative ranking only; values are not experimentally calibrated absolute free energies.",
        "- **MD Gate**: PASS/REVIEW/FAIL is based on setup/simulation completion, ligand pose stability, and persistent protein-ligand contacts. MMGBSA is an annotation, not a hard gate.",
        "",
        "## Interpretation Guide",
        "",
        f"- **Pass**: completed MD, ligand RMSD < {MD_GATE_LIGAND_RMSD_REVIEW_ANGSTROM:.1f} Å, and at least {MD_GATE_MIN_STABLE_CONTACTS_PASS} contact with occupancy ≥ {MD_GATE_STABLE_CONTACT_OCCUPANCY:.2f}.",
        f"- **Review**: completed MD but ligand RMSD is {MD_GATE_LIGAND_RMSD_REVIEW_ANGSTROM:.1f}–{MD_GATE_LIGAND_RMSD_FAIL_ANGSTROM:.1f} Å, interaction evidence is borderline, or an annotation step failed.",
        f"- **Fail**: setup/simulation failed, ligand RMSD ≥ {MD_GATE_LIGAND_RMSD_FAIL_ANGSTROM:.1f} Å, or no persistent protein-ligand contact was detected.",
        "- **Block 4 handoff**: only pass ligands advance automatically; review ligands require manual inspection; fail ligands are excluded from FEP selection.",
        "",
        "## Per-Ligand Output Files",
        "",
    ])

    for row in selected:
        ligand = str(row.get("ligand") or "")
        r = ligand_results.get(ligand) or {}
        lines.extend([
            f"### {ligand}",
            "",
            f"- Prep record: `{r.get('prep_record', 'n/a')}`",
            f"- Simulation record: `{r.get('simulation_record', 'n/a')}`",
            f"- Interactions record: `{r.get('interactions_record', 'n/a')}`",
            f"- MMGBSA record: `{r.get('mmgbsa_record', 'n/a')}`",
        ])
        top = r.get("top_interactions") or []
        if top:
            lines.extend([
                "",
                "**Top MD interactions (ProLIF occupancy):**",
                "",
                "| Residue | Interaction | Occupancy |",
                "| --- | --- | ---: |",
            ])
            for interaction in top[:10]:
                res = interaction.get("residue") or interaction.get("residue_name") or ""
                itype = interaction.get("type") or interaction.get("interaction_type") or ""
                occ = interaction.get("occupancy") or interaction.get("occupancy_fraction") or ""
                if isinstance(occ, float):
                    occ = f"{occ:.2f}"
                lines.append(f"| {res} | {itype} | {occ} |")
        lines.append("")

    lines.extend([
        "## Recommended Next Steps",
        "",
        "1. Advance MD gate pass ligands to FEP in Block 2 rank order.",
        "2. Manually inspect review ligands before overriding the automated gate.",
        "3. Use MMGBSA and ProLIF details as supporting annotations, not as the primary ranking method.",
        "4. Visualize the final MD frame for top ligands: look for clashes, buried polar groups, or loss of key interactions.",
        "5. Validate experimentally before making biological claims.",
    ])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _crop_receptor_around_ligand(
    *,
    receptor_pdbqt: Path,
    docked_pdbqt: Path,
    output_pdb: Path,
    radius_angstrom: float,
    water_padding_nm: float = 1.2,
    ph: float = 7.4,
) -> dict[str, Any]:
    """Build a cropped, fully-fixed receptor PDB for MD prep.

    Pipeline: PDBQT → PDB → PDBFixer on the whole receptor, where templates
    match cleanly → identify residues within ``radius_angstrom`` of any ligand
    heavy atom → expand those hits into padded contiguous sequence windows.

    The output intentionally contains only heavy atoms.  ``prepare_md_system``
    then runs one final PDBFixer pass on contiguous peptide windows, avoiding
    isolated one-residue fragments that OpenMM/AMBER cannot template.

    Returns an estimated solvated atom count so callers can fail fast before
    OpenMM allocates GBs of memory.
    """
    from .md_prep import _receptor_pdbqt_to_pdb, _fix_protein

    work_dir = output_pdb.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    raw_pdb = work_dir / "receptor_raw.pdb"
    fixed_full_pdb = work_dir / "receptor_full_fixed.pdb"
    _receptor_pdbqt_to_pdb(receptor_pdbqt, raw_pdb)
    _fix_protein(raw_pdb, fixed_full_pdb, ph=ph, keep_water=False)

    ligand_coords: list[tuple[float, float, float]] = []
    for line in docked_pdbqt.read_text().splitlines():
        if line.startswith(("ATOM", "HETATM")):
            try:
                ligand_coords.append((float(line[30:38]), float(line[38:46]), float(line[46:54])))
            except ValueError:
                continue
    if not ligand_coords:
        raise ValueError(f"No ligand atoms found in {docked_pdbqt}")

    residue_atoms: dict[tuple[str, int, str], list[tuple[str, tuple[float, float, float], bool]]] = {}
    residue_order: list[tuple[str, int, str]] = []
    chain_order: dict[str, list[tuple[str, int, str]]] = {}
    for line in fixed_full_pdb.read_text().splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        try:
            chain = line[21]
            resnum = int(line[22:26])
            resname = line[17:20].strip()
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
        except ValueError:
            continue
        atom_name = line[12:16].strip()
        element = line[76:78].strip() if len(line) >= 78 else ""
        is_hydrogen = element == "H" or (not element and atom_name.startswith("H"))
        key = (chain, resnum, resname)
        if key not in residue_atoms:
            residue_atoms[key] = []
            residue_order.append(key)
            chain_order.setdefault(chain, []).append(key)
        residue_atoms[key].append((line, (x, y, z), is_hydrogen))

    # Keep residues with any HEAVY atom within radius of any ligand atom.
    radius_sq = radius_angstrom * radius_angstrom
    contact_residues: set[tuple[str, int, str]] = set()
    for key, atoms in residue_atoms.items():
        found = False
        for _line, (x, y, z), is_h in atoms:
            if is_h:
                continue
            for lx, ly, lz in ligand_coords:
                if (x - lx) ** 2 + (y - ly) ** 2 + (z - lz) ** 2 <= radius_sq:
                    found = True
                    break
            if found:
                break
        if found:
            contact_residues.add(key)

    if not contact_residues:
        raise ValueError(
            f"No receptor residues within {radius_angstrom} Å of the docked ligand. "
            "Check that receptor and docked-ligand coordinates share a frame."
        )

    kept: set[tuple[str, int, str]] = set()
    residue_padding = 2
    for chain, keys in chain_order.items():
        hit_indices = [idx for idx, key in enumerate(keys) if key in contact_residues]
        for idx in hit_indices:
            start = max(0, idx - residue_padding)
            end = min(len(keys), idx + residue_padding + 1)
            kept.update(keys[start:end])

    output_lines: list[str] = []
    prev_chain: str | None = None
    prev_resnum: int | None = None
    kept_atoms = 0
    kept_heavy_atoms = 0
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for key in residue_order:
        if key not in kept:
            continue
        chain, resnum, _resname = key
        if prev_chain is not None and (chain != prev_chain or (prev_resnum is not None and resnum > prev_resnum + 1)):
            output_lines.append("TER")
        for line, (x, y, z), is_h in residue_atoms[key]:
            if is_h:
                continue
            output_lines.append(line)
            kept_atoms += 1
            kept_heavy_atoms += 1
            xs.append(x); ys.append(y); zs.append(z)
        prev_chain = chain
        prev_resnum = resnum
    output_lines.append("TER")
    output_lines.append("END")
    output_pdb.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    pad_a = water_padding_nm * 10.0
    box_x = (max(xs) - min(xs)) + 2 * pad_a
    box_y = (max(ys) - min(ys)) + 2 * pad_a
    box_z = (max(zs) - min(zs)) + 2 * pad_a
    box_volume = box_x * box_y * box_z
    estimated_protein_atoms = int(kept_heavy_atoms * 2.0)
    estimated_atoms = int(estimated_protein_atoms + 0.1 * box_volume + len(ligand_coords) * 1.2)

    return {
        "total_residues": len(residue_atoms),
        "kept_residues": len(kept),
        "contact_residues": len(contact_residues),
        "residue_padding": residue_padding,
        "kept_atoms": kept_atoms,
        "kept_heavy_atoms": kept_heavy_atoms,
        "radius_angstrom": radius_angstrom,
        "box_angstrom": (box_x, box_y, box_z),
        "estimated_atoms": estimated_atoms,
    }


def _try_path(value: Any) -> Path | None:
    if not value:
        return None
    path = Path(str(value))
    return path if path.exists() else None


def _new_interactive_progress(root: Path, progress_json: Path) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if progress_json.exists():
        try:
            data = json.loads(progress_json.read_text())
            if isinstance(data, dict):
                existing = data
        except json.JSONDecodeError:
            existing = {}
    return {
        "started_at": existing.get("started_at") or _now(),
        "updated_at": _now(),
        "job_id": existing.get("job_id") or progress_json.parent.name.removeprefix("md-optimization-"),
        **campaign_context(),
        "status": "starting",
        "current_step": "select-inputs",
        "progress_json": str(progress_json),
        "terminal_log": existing.get("terminal_log") or str(progress_json.parent / "terminal.log"),
        "root": str(root),
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
        "selections": existing.get("selections") if isinstance(existing.get("selections"), dict) else {},
        "provenance": existing.get("provenance")
        if isinstance(existing.get("provenance"), dict)
        else runtime_provenance(forcefields={"protein": "amber14-all.xml", "water": "amber14/tip3pfb.xml", "ligand": "openff-2.2.0"}, structures={}),
        "dashboard_defaults": existing.get("dashboard_defaults") if isinstance(existing.get("dashboard_defaults"), dict) else {},
        "events": existing.get("events") if isinstance(existing.get("events"), list) else [{"time": _now(), "message": "Starting MD optimization wizard."}],
        "notes": ["Answer terminal prompts; the dashboard mirrors MD selections, cluster export, and progress."],
    }


def _recent_md_input_runs(root: Path, limit: int = 10) -> list[dict[str, Any]]:
    summary_paths: list[Path] = []
    for base in [root / "reports", root / "runs"]:
        summary_paths.extend(base.glob("*/hit_refinement_summary.json"))
        summary_paths.extend(base.glob("*/report/hit_refinement_summary.json"))
        summary_paths.extend(base.glob("*/small_screen_summary.json"))
        summary_paths.extend(base.glob("*/report/docking_results_summary.json"))
    rows: list[dict[str, Any]] = []
    for summary_path in sorted(set(summary_paths)):
        try:
            data = json.loads(summary_path.read_text())
        except Exception:
            continue
        results_json = (
            data.get("per_ligand_summary_json")
            or data.get("results_json")
            or data.get("final_results_json")
        )
        if not results_json or not Path(str(results_json)).exists():
            continue
        display_name = summary_path.parent.name if summary_path.parent.name != "report" else summary_path.parent.parent.name
        rows.append(
            {
                "name": display_name,
                "summary_path": str(summary_path),
                "results_json": str(results_json),
                "best_ligand": data.get("best_ligand"),
                "best_score": data.get("best_score"),
                "run_count": data.get("run_count") or data.get("docked_ligands"),
                "created_at": data.get("created_at") or data.get("finished_at"),
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


def _choose_row(prompt: str, rows: list[tuple[Any, str]], default: int = 1) -> Any:
    print(f"\n{prompt}")
    for index, (_row, label) in enumerate(rows, start=1):
        suffix = " [default]" if index == default else ""
        print(f"  {index}. {label}{suffix}")
    while True:
        try:
            raw = input(f"Select number [{default}]: ").strip()
        except EOFError:
            return rows[default - 1][0]
        if not raw:
            return rows[default - 1][0]
        try:
            index = int(raw)
        except ValueError:
            print("Enter a number.")
            continue
        if 1 <= index <= len(rows):
            return rows[index - 1][0]
        print(f"Enter a number from 1 to {len(rows)}.")


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return value or default


def _ask_int(prompt: str, default: int, minimum: int = 1) -> int:
    while True:
        raw = _ask(prompt, str(default))
        try:
            value = int(raw)
        except ValueError:
            print("Enter a whole number.")
            continue
        if value < minimum:
            print(f"Enter a value >= {minimum}.")
            continue
        return value


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _set_step_status(progress: dict[str, Any], key: str, status: str) -> None:
    for step in progress.get("steps", []):
        if step["key"] == key:
            step["status"] = status
            return


def _mark_ligand_downstream_skipped(progress: dict[str, Any], ligand: str) -> None:
    status = progress.get("ligand_status", {}).get(ligand)
    if not isinstance(status, dict):
        return
    for key in ("simulation", "interactions", "mmgbsa"):
        if status.get(key) in {None, "", "pending"}:
            status[key] = "skipped"


def _set_final_step_statuses(progress: dict[str, Any]) -> None:
    ligand_status = progress.get("ligand_status") or {}
    stage_map = {
        "md-prep": "prep",
        "md-simulation": "simulation",
        "md-interactions": "interactions",
        "mmgbsa": "mmgbsa",
    }
    for step_key, ligand_key in stage_map.items():
        statuses = [
            str(status.get(ligand_key) or "")
            for status in ligand_status.values()
            if isinstance(status, dict)
        ]
        if any(status == "completed" for status in statuses):
            _set_step_status(progress, step_key, "completed")
        elif any(status == "failed" for status in statuses):
            _set_step_status(progress, step_key, "failed")
        elif any(status == "skipped" for status in statuses):
            _set_step_status(progress, step_key, "skipped")
        else:
            _set_step_status(progress, step_key, "pending")


def _log_event(progress: dict[str, Any], message: str) -> None:
    progress.setdefault("events", []).append({"time": _now(), "message": message})
    print(message, flush=True)


def _write_progress(progress_json: Path, progress: dict[str, Any]) -> None:
    progress["updated_at"] = _now()
    progress_json.parent.mkdir(parents=True, exist_ok=True)
    progress_json.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
