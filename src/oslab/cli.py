from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .binding_sites import box_from_ligand, box_from_residues, find_ligand_residue_names
from .docking import prepare_receptor_for_vina, run_vina
from .dashboard import serve_dashboard
from .demo_results import install_demo_results
from .hpc import (
    HpcJobConfig,
    export_slurm_docking,
    export_slurm_fep,
    export_slurm_hit_refinement,
    export_slurm_md_optimization,
    export_slurm_small_screen,
)
from .hit_clustering import cluster_hits_from_results
from .hit_refinement import refine_hits_from_results, run_interactive_hit_refinement
from .interactions import run_plip_analysis
from .ligand_filtering import filter_ligands
from .ligand_prep import prepare_ligands_for_vina
from .ligand_sources import LIGAND_SOURCES, ligand_source_rows
from .model import Workflow
from .presets.registry import list_ligand_filter_presets, load_ligand_filter_preset
from .protein import prepare_protein
from .project import default_project_root, ensure_project_layout, set_default_project_root
from .reporting import summarize_validation_runs, summarize_vina_runs
from .screening import run_prepared_pdbqt_screen, run_small_screen
from .schemas import (
    LigandPrepOptions,
    MdPrepOptions,
    MdSimulationOptions,
    MmgbsaOptions,
    ProteinPrepOptions,
    VinaRunOptions,
)
from .structures import (
    fetch_alphafold_structure,
    fetch_pdb_structure,
    list_structure_records,
    register_local_structure,
)
from .md_optimization import run_interactive_md_optimization, run_md_optimization
from .md_prep import prepare_md_system, smiles_from_pdbqt
from .md_simulation import run_md
from .md_interactions import analyze_trajectory
from .mmgbsa import estimate_mmgbsa
from .terminal_orchestration import run_terminal_orchestration
from .tools import check_cli_tools, check_python_imports
from .validation import redock_crystal_ligand
from .visualization import render_binding_site_html
from .workflows import build_docking_workflow
from .fep import run_interactive_fep, run_fep_pipeline, recent_md_optimization_runs


def _triple(values: list[str], name: str) -> tuple[float, float, float]:
    if len(values) != 3:
        raise argparse.ArgumentTypeError(f"{name} requires exactly three numbers")
    return (float(values[0]), float(values[1]), float(values[2]))


def _add_slurm_single_job_args(parser: argparse.ArgumentParser, *, default_job_name: str) -> None:
    parser.add_argument("--job-name", default=default_job_name)
    parser.add_argument("--cpus-per-task", type=int, default=None)
    parser.add_argument("--time", default=None)
    parser.add_argument("--partition")
    parser.add_argument("--account")
    parser.add_argument("--gres", help="Optional SLURM generic resource request, e.g. gpu:1.")
    parser.add_argument("--memory", help="Optional SLURM memory request, e.g. 32G.")
    parser.add_argument("--setup-command", help="Shell command to load modules/activate env before running.")
    parser.add_argument("--oslab-command", default="oslab")


def _add_gpu_assignment_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--gpu-mode",
        choices=["auto", "all", "single", "custom", "cpu"],
        default="auto",
        help="GPU assignment policy for CUDA OpenMM/OpenFE work.",
    )
    parser.add_argument(
        "--gpu-devices",
        default="",
        help="Comma-separated CUDA device list for --gpu-mode custom, or to limit auto/all/single.",
    )
    parser.add_argument(
        "--gpu-jobs-per-device",
        type=int,
        default=1,
        help="Concurrent Block 4 transformations per GPU; Block 3 records deterministic per-ligand assignments.",
    )
    parser.add_argument(
        "--require-gpu",
        action="store_true",
        help="Fail instead of falling back to CPU when no CUDA GPU is discovered.",
    )


def cmd_check_tools(_args: argparse.Namespace) -> int:
    failed = False
    for status in [*check_cli_tools(), *check_python_imports()]:
        marker = "OK" if status.available else "MISSING"
        print(f"{marker:7} {status.name:22} {status.detail}")
        failed = failed or not status.available
    return 1 if failed else 0


def cmd_ligand_sources(args: argparse.Namespace) -> int:
    rows = ligand_source_rows()
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    headers = ("key", "vina", "prep", "molecule_count", "typical_size")
    print(f"{headers[0]:28} {headers[1]:5} {headers[2]:11} {headers[3]:58} {headers[4]}")
    print("-" * 130)
    for row in rows:
        print(
            f"{row['key']:28} "
            f"{str(row['vina_ready']):5} "
            f"{row['rdkit_meeko_prep']:11} "
            f"{str(row['molecule_count'])[:58]:58} "
            f"{row['typical_size']}"
        )
    return 0


def cmd_filter_presets(args: argparse.Namespace) -> int:
    if args.preset:
        preset = load_ligand_filter_preset(args.preset)
        print(json.dumps(preset.model_dump(), indent=2))
        return 0

    for key in list_ligand_filter_presets():
        preset = load_ligand_filter_preset(key)
        print(f"{preset.key:18} {preset.name}")
        print(f"{'':18} {preset.description}")
    return 0


def cmd_init_project(args: argparse.Namespace) -> int:
    layout = ensure_project_layout(args.root)
    if getattr(args, "set_default", False):
        set_default_project_root(args.root)
    print(json.dumps(layout.model_dump(), indent=2))
    return 0


def cmd_configure(args: argparse.Namespace) -> int:
    root = set_default_project_root(args.root)
    layout = ensure_project_layout(root)
    result = {
        "configured_project_root": str(root),
        "layout": layout.model_dump(),
        "environment_override": "Set OSLAB_ROOT to override this location for one shell/session.",
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_install_demo(args: argparse.Namespace) -> int:
    result = install_demo_results(args.root, overwrite=args.overwrite)
    print(json.dumps(result, indent=2))
    return 0


def cmd_fetch_benchmark(args: argparse.Namespace) -> int:
    from .benchmarks import REGISTRY, describe_registry, fetch_benchmark
    if getattr(args, "list", False):
        print(json.dumps(describe_registry(), indent=2))
        return 0
    if args.name not in REGISTRY:
        print(json.dumps({"error": f"Unknown benchmark {args.name!r}", "known": sorted(REGISTRY)}, indent=2), file=sys.stderr)
        return 2
    def on_file(bf, status, n):
        size = f"{n:>12,}" if n else "           "
        print(f"  {status:>10}  {size} B  {bf.relpath}", file=sys.stderr)
    try:
        result = fetch_benchmark(args.name, args.to, overwrite=args.overwrite, on_file=on_file)
    except KeyError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    except Exception as exc:  # urllib.error.URLError, OSError, etc.
        print(json.dumps({"error": f"download failed: {exc}"}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def cmd_fetch_pdb(args: argparse.Namespace) -> int:
    record = fetch_pdb_structure(
        pdb_id=args.pdb_id,
        root=args.root,
        file_format=args.format,
        overwrite=args.overwrite,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_fetch_alphafold(args: argparse.Namespace) -> int:
    record = fetch_alphafold_structure(
        uniprot_accession=args.accession,
        root=args.root,
        model_version=args.model_version,
        overwrite=args.overwrite,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_register_local_structure(args: argparse.Namespace) -> int:
    record = register_local_structure(
        input_path=args.path,
        root=args.root,
        identifier=args.identifier,
        file_format=args.format,
        copy=not args.no_copy,
        overwrite=args.overwrite,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_list_structures(args: argparse.Namespace) -> int:
    records = list_structure_records(args.root)
    if args.json:
        print(json.dumps([record.model_dump(mode="json") for record in records], indent=2))
        return 0
    print(f"{'key':28} {'type':13} {'format':6} {'sha256':12} path")
    print("-" * 100)
    for record in records:
        print(
            f"{record.key:28} {record.structure_type:13} "
            f"{record.file_format:6} {record.sha256[:12]} {record.cached_path}"
        )
    return 0


def cmd_prepare_protein(args: argparse.Namespace) -> int:
    options = ProteinPrepOptions(
        ph=args.ph,
        keep_water=args.keep_water,
        minimize=not args.no_minimize,
        max_minimization_iterations=args.max_minimization_iterations,
    )
    record = prepare_protein(args.structure, args.out, options)
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_binding_site_ligands(args: argparse.Namespace) -> int:
    names = find_ligand_residue_names(args.structure)
    if args.json:
        print(json.dumps(names, indent=2))
    else:
        for name in names:
            print(name)
    return 0


def cmd_binding_site_from_ligand(args: argparse.Namespace) -> int:
    record = box_from_ligand(
        structure_path=args.structure,
        ligand=args.ligand,
        output_dir=args.out,
        padding=args.padding,
        minimum_size=args.minimum_size,
        chain=args.chain,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_binding_site_from_residues(args: argparse.Namespace) -> int:
    record = box_from_residues(
        structure_path=args.structure,
        residues=args.residue,
        output_dir=args.out,
        padding=args.padding,
        minimum_size=args.minimum_size,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_filter_ligands(args: argparse.Namespace) -> int:
    summary = filter_ligands(args.input, args.out, args.preset)
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return 0


def cmd_prepare_ligands(args: argparse.Namespace) -> int:
    options = LigandPrepOptions(
        ph=args.ph,
        generate_3d=not args.no_gen3d,
        charge_model=args.charge_model,
        backend=args.backend,
        workers=args.workers,
        timeout_seconds=args.timeout_seconds,
    )
    record = prepare_ligands_for_vina(args.input, args.out, options)
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_prepare_receptor_vina(args: argparse.Namespace) -> int:
    record = prepare_receptor_for_vina(
        input_pdb=args.input,
        output_dir=args.out,
        binding_site_json=args.binding_site,
        allow_bad_residues=args.allow_bad_residues,
        default_altloc=args.default_altloc,
        delete_residues=args.delete_residues,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_run_vina(args: argparse.Namespace) -> int:
    options = VinaRunOptions(
        exhaustiveness=args.exhaustiveness,
        num_modes=args.num_modes,
        cpu=args.cpu,
        seed=args.seed,
    )
    record = run_vina(
        receptor_pdbqt=args.receptor,
        ligand_pdbqt=args.ligand,
        binding_site_json=args.binding_site,
        output_dir=args.out,
        options=options,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_summarize_vina(args: argparse.Namespace) -> int:
    summary = summarize_vina_runs(args.vina_run, args.out, args.interaction_analysis)
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return 0


def cmd_summarize_validation(args: argparse.Namespace) -> int:
    summary = summarize_validation_runs(args.validation_run, args.out, make_overlay=not args.no_overlay)
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return 0


def cmd_visualize_binding_site(args: argparse.Namespace) -> int:
    output = render_binding_site_html(
        structure_path=args.structure,
        binding_site_json=args.binding_site,
        output_html=args.out,
        docked_ligand=args.docked_ligand,
    )
    print(output)
    return 0


def cmd_interactions_plip(args: argparse.Namespace) -> int:
    record = run_plip_analysis(
        receptor_pdbqt=args.receptor_pdbqt,
        docked_ligand_pdbqt=args.docked_ligand,
        output_dir=args.out,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return record.returncode


def cmd_validation_redock(args: argparse.Namespace) -> int:
    options = VinaRunOptions(
        exhaustiveness=args.exhaustiveness,
        num_modes=args.num_modes,
        cpu=args.cpu,
        seed=args.seed,
    )
    record = redock_crystal_ligand(
        structure_path=args.structure,
        ligand=args.ligand,
        receptor_pdbqt=args.receptor,
        binding_site_json=args.binding_site,
        output_dir=args.out,
        chain=args.chain,
        residue_number=args.residue_number,
        options=options,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0 if record.status in {"pass", "review"} else 1


def cmd_screen_small(args: argparse.Namespace) -> int:
    report_context = _read_report_context(args.report_context_json)
    ligand_options = LigandPrepOptions(
        ph=args.ph,
        generate_3d=not args.no_gen3d,
        charge_model=args.charge_model,
        backend=args.ligand_prep_backend,
        workers=args.ligand_prep_workers,
        timeout_seconds=args.ligand_prep_timeout,
    )
    vina_options = VinaRunOptions(
        exhaustiveness=args.exhaustiveness,
        num_modes=args.num_modes,
        cpu=args.cpu,
        seed=args.seed,
        workers=args.docking_workers,
    )
    if args.execution_backend == "local":
        # Write a docking-kind progress.json so the dashboard's
        # /api/progress-scan discovers this CLI run and shows it in the
        # Progress Monitor / Reports tabs whenever --out is inside the
        # dashboard workspace root. Without this, oslab screen small was
        # invisible to the dashboard even though the result CSV was on
        # disk (audit problem #5).
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        progress_path = out_dir / "progress.json"

        def _write_progress(payload: dict[str, object]) -> None:
            payload.setdefault("kind", "docking")
            payload["updated_at"] = datetime.now(timezone.utc).isoformat()
            try:
                progress_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            except OSError:
                pass

        started_at = datetime.now(timezone.utc).isoformat()
        _write_progress({
            "status": "running",
            "current_step": "running",
            "percent": 0,
            "started_at": started_at,
            "message": "oslab screen small in progress",
        })
        try:
            summary = run_small_screen(
                ligands=args.ligands,
                receptor_pdbqt=args.receptor,
                binding_site_json=args.binding_site,
                output_dir=args.out,
                max_ligands=args.max_ligands,
                preset=args.preset,
                run_plip=not args.no_plip,
                ligand_prep_options=ligand_options,
                vina_options=vina_options,
                report_context=report_context,
            )
        except Exception as exc:
            _write_progress({
                "status": "failed",
                "current_step": "failed",
                "percent": 0,
                "started_at": started_at,
                "message": f"oslab screen small failed: {exc}",
            })
            raise
        report_dir = str((out_dir / "report").resolve()) if (out_dir / "report").exists() else ""
        results_csv = getattr(summary, "results_csv", "") or ""
        _write_progress({
            "status": "completed",
            "current_step": "completed",
            "percent": 100,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "message": f"docked {summary.docked_ligands} ligand(s); best score {summary.best_score}",
            "report_dir": report_dir,
            "results_json": str(getattr(summary, "results_json", "") or ""),
        })
        print(json.dumps(summary.model_dump(mode="json"), indent=2))
        return 0

    export = export_slurm_small_screen(
        ligands=args.ligands,
        receptor_pdbqt=args.receptor,
        binding_site_json=args.binding_site,
        output_dir=args.out,
        max_ligands=args.max_ligands,
        preset=args.preset,
        ligand_prep_options=ligand_options,
        vina_options=vina_options,
        job_name=args.slurm_job_name,
        cpus_per_task=args.slurm_cpus_per_task,
        array_concurrency=args.slurm_array_concurrency,
        time_limit=args.slurm_time,
        partition=args.slurm_partition,
        account=args.slurm_account,
        gres=args.slurm_gres,
        setup_command=args.slurm_setup_command,
        oslab_command=args.oslab_command,
    )
    print(
        json.dumps(
            {
                "backend": "slurm-export",
                "output_dir": str(export.output_dir),
                "filter_summary_json": export.filter_summary_json,
                "ligand_prep_json": export.ligand_prep_json,
                "submit_script": str(export.docking_export.submit_script),
                "collect_script": str(export.docking_export.collect_script),
                "ligand_count": export.docking_export.ligand_count,
            },
            indent=2,
        )
    )
    return 0


def cmd_screen_pdbqt_dir(args: argparse.Namespace) -> int:
    report_context = _read_report_context(args.report_context_json)
    vina_options = VinaRunOptions(
        exhaustiveness=args.exhaustiveness,
        num_modes=args.num_modes,
        cpu=args.cpu,
        seed=args.seed,
        workers=args.docking_workers,
    )
    summary = run_prepared_pdbqt_screen(
        ligand_dir=args.ligand_dir,
        receptor_pdbqt=args.receptor,
        binding_site_json=args.binding_site,
        output_dir=args.out,
        max_ligands=args.max_ligands,
        run_plip=not args.no_plip,
        vina_options=vina_options,
        report_context=report_context,
        progress_json=args.progress_json,
    )
    print(json.dumps(summary.model_dump(mode="json"), indent=2))
    return 0


def _read_report_context(path: Path | None) -> dict[str, object]:
    if not path:
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        raise SystemExit(f"could not read report context JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"report context JSON must contain an object: {path}")
    return data


def cmd_dashboard_serve(args: argparse.Namespace) -> int:
    serve_dashboard(root=args.root, host=args.host, port=args.port, open_browser=args.open_browser)
    return 0


def cmd_md_prep(args: argparse.Namespace) -> int:
    # Resolve SMILES: explicit arg > REMARK in docked PDBQT > REMARK in input PDBQT
    smiles = args.smiles
    if not smiles:
        smiles = smiles_from_pdbqt(args.docked_ligand)
    if not smiles and args.ligand_pdbqt:
        smiles = smiles_from_pdbqt(args.ligand_pdbqt)
    if not smiles:
        raise SystemExit(
            "--smiles is required (or store a REMARK SMILES line in the PDBQT file)."
        )
    options = MdPrepOptions(
        ph=args.ph,
        keep_water=args.keep_water,
        water_padding_nm=args.water_padding_nm,
        ionic_strength_m=args.ionic_strength_m,
        temperature_k=args.temperature_k,
        minimization_steps=args.minimization_steps,
        smirnoff_forcefield=args.smirnoff_forcefield,
    )
    record = prepare_md_system(
        receptor_pdbqt=args.receptor,
        docked_ligand_pdbqt=args.docked_ligand,
        ligand_smiles=smiles,
        output_dir=args.out,
        options=options,
        protein_pdb=args.protein_pdb,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_md_run(args: argparse.Namespace) -> int:
    options = MdSimulationOptions(
        timestep_fs=args.timestep_fs,
        temperature_k=args.temperature_k,
        nvt_equilibration_ns=args.nvt_ns,
        npt_equilibration_ns=args.npt_ns,
        production_ns=args.production_ns,
        save_every_steps=args.save_every_steps,
    )
    record = run_md(
        topology_pdb=args.topology,
        system_xml=args.system_xml,
        output_dir=args.out,
        options=options,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_md_interactions(args: argparse.Namespace) -> int:
    record = analyze_trajectory(
        topology_pdb=args.topology,
        trajectory_dcd=args.trajectory,
        output_dir=args.out,
        plip_interaction_json=args.plip_json,
        step=args.step,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_md_mmgbsa(args: argparse.Namespace) -> int:
    options = MmgbsaOptions(
        n_frames=args.n_frames,
        smirnoff_forcefield=args.smirnoff_forcefield,
    )
    record = estimate_mmgbsa(
        topology_pdb=args.topology,
        trajectory_dcd=args.trajectory,
        output_dir=args.out,
        options=options,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def cmd_md_optimize(args: argparse.Namespace) -> int:
    if args.interactive:
        return run_interactive_md_optimization(args.root or default_project_root(), args.progress_json)
    if not args.results_json or not args.out or not args.progress_json:
        raise SystemExit("--results-json, --out, and --progress-json are required unless --interactive is used")
    prep_options = MdPrepOptions(
        ph=args.ph,
        water_padding_nm=args.water_padding_nm,
        ionic_strength_m=args.ionic_strength_m,
        temperature_k=args.temperature_k,
        minimization_steps=args.minimization_steps,
        smirnoff_forcefield=args.smirnoff_forcefield,
    )
    sim_options = MdSimulationOptions(
        timestep_fs=args.timestep_fs,
        temperature_k=args.temperature_k,
        nvt_equilibration_ns=args.nvt_ns,
        npt_equilibration_ns=args.npt_ns,
        production_ns=args.production_ns,
    )
    mmgbsa_options = MmgbsaOptions(
        n_frames=args.n_frames,
        smirnoff_forcefield=args.smirnoff_forcefield,
    )
    root = args.root or Path(".")
    return run_md_optimization(
        root=root,
        progress_json=args.progress_json,
        results_json=args.results_json,
        output_dir=args.out,
        top_n=args.top_n,
        prep_options=prep_options,
        sim_options=sim_options,
        mmgbsa_options=mmgbsa_options,
        crop_radius_angstrom=args.crop_radius_angstrom,
        max_solvated_atoms=args.max_solvated_atoms,
        gpu_mode=args.gpu_mode,
        gpu_devices=args.gpu_devices,
        gpu_jobs_per_device=args.gpu_jobs_per_device,
        require_gpu=args.require_gpu,
    )


def cmd_orchestrate_terminal(args: argparse.Namespace) -> int:
    return run_terminal_orchestration(args.root, args.progress_json)


def cmd_fep_run(args: argparse.Namespace) -> int:
    root = (args.root or Path(".")).resolve()
    if args.interactive:
        if args.max_minutes_per_transformation is not None:
            import os as _os
            _os.environ["OSLAB_OPENFE_MAX_MINUTES_PER_TRANSFORMATION"] = str(args.max_minutes_per_transformation)
        return run_interactive_fep(root, args.progress_json)
    # Non-interactive: require explicit arguments
    if not args.md_progress_json:
        raise SystemExit("--md-progress-json is required unless --interactive is used")
    import json as _json
    import uuid as _uuid
    session_id = _uuid.uuid4().hex[:8]
    progress_json = args.progress_json or root / "runs" / f"fep-{session_id}" / "progress.json"
    # Load ligands from MD progress JSON
    try:
        md_data = _json.loads(Path(args.md_progress_json).read_text())
    except Exception as exc:
        raise SystemExit(f"Could not read md-progress-json: {exc}")
    ligand_results = md_data.get("ligand_results") or {}
    if not ligand_results:
        raise SystemExit("No ligand_results found in md-progress-json")
    from .fep import _ranked_ligands, _ligand_smiles_from_md_run, _receptor_pdb_from_md_run
    ranked = _ranked_ligands(ligand_results)
    if not ranked:
        raise SystemExit(
            "No MD gate pass ligands found in md-progress-json. "
            "Block 4 now accepts only Block 3 pass ligands, ranked by Block 2 order."
        )
    md_smiles_map = _ligand_smiles_from_md_run({"ligand_results": ligand_results})

    analog_library_dict = None
    if args.input_mode == "analog":
        # Pick parent (explicit name, else top-MMGBSA hit with SMILES)
        parent_name = args.analog_parent
        if not parent_name:
            for name, _ in ranked:
                if name in md_smiles_map:
                    parent_name = name
                    break
        elif parent_name not in {name for name, _ in ranked}:
            raise SystemExit(
                f"--analog-parent {parent_name!r} is not an MD gate pass ligand. "
                "Choose a Block 3 pass ligand or rerun Block 3."
            )
        if not parent_name or parent_name not in md_smiles_map:
            raise SystemExit(
                f"--analog-parent {parent_name!r} has no SMILES in the MD run. "
                "Pass an explicit --analog-parent."
            )
        parent_smiles = md_smiles_map[parent_name]
        from .analog_library import generate_analogs
        library = generate_analogs(
            parent_smiles,
            parent_name=parent_name,
            n_max=max(1, int(args.n_analogs)),
        )
        if not library.analogs:
            raise SystemExit(
                f"Analog library for {parent_name} is empty after filtering "
                f"(rejected: {library.rejected_summary})."
            )
        smiles_map = library.smiles_map()
        selected = list(smiles_map.keys())
        reference = parent_name
        receptor_pdb = _receptor_pdb_from_md_run({"ligand_results": ligand_results}, parent_name)
        analog_library_dict = library.to_dict()
    else:
        top_n = min(args.top_n, len(ranked))
        if top_n < 2:
            raise SystemExit("Need at least 2 MD gate pass ligands for top-N FEP.")
        selected = [name for name, _ in ranked[:top_n]]
        smiles_map = md_smiles_map
        reference = selected[0] if selected else ""
        receptor_pdb = _receptor_pdb_from_md_run({"ligand_results": ligand_results}, reference)

    out = args.out or root / "reports" / f"fep-{session_id}"
    return run_fep_pipeline(
        root=root,
        progress_json=Path(progress_json),
        selected_ligands=selected,
        ligand_smiles={k: v for k, v in smiles_map.items() if k in selected},
        reference_ligand=reference,
        receptor_pdb=receptor_pdb,
        output_dir=Path(out),
        n_lambda=args.n_lambda,
        n_steps_per_window=args.n_steps_per_window,
        n_equilibration_steps=args.n_equilibration_steps,
        max_minutes_per_transformation=args.max_minutes_per_transformation,
        temperature_k=args.temperature_k,
        forcefield=args.forcefield,
        md_run={"ligand_results": ligand_results},
        analog_library=analog_library_dict,
        gpu_mode=args.gpu_mode,
        gpu_devices=args.gpu_devices,
        gpu_jobs_per_device=args.gpu_jobs_per_device,
        require_gpu=args.require_gpu,
    )


def cmd_refine_hits(args: argparse.Namespace) -> int:
    if args.interactive:
        return run_interactive_hit_refinement(args.root, args.progress_json)
    if not args.results_json or not args.out:
        raise SystemExit("--results-json and --out are required unless --interactive is used")
    result = refine_hits_from_results(
        results_json=args.results_json,
        output_dir=args.out,
        top_n=args.top_n,
        exhaustiveness=args.exhaustiveness,
        num_modes=args.num_modes,
        cpu=args.cpu,
        workers=args.workers,
        seeds=[int(seed.strip()) for seed in args.seeds.split(",") if seed.strip()],
        run_plip=not args.no_plip,
        plip_top_n=args.plip_top_n,
        progress_json=args.progress_json,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_cluster_hits(args: argparse.Namespace) -> int:
    result = cluster_hits_from_results(
        results_json=args.results_json,
        output_dir=args.out,
        top_n=args.top_n,
        similarity_threshold=args.similarity_threshold,
        radius=args.radius,
        fp_size=args.fp_size,
        max_per_cluster=args.max_per_cluster,
        progress_json=args.progress_json,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_hpc_export_slurm_docking(args: argparse.Namespace) -> int:
    options = VinaRunOptions(
        exhaustiveness=args.exhaustiveness,
        num_modes=args.num_modes,
        cpu=args.vina_cpu,
        seed=args.seed,
    )
    export = export_slurm_docking(
        receptor_pdbqt=args.receptor,
        binding_site_json=args.binding_site,
        ligand_dir=args.ligand_dir,
        output_dir=args.out,
        options=options,
        job_name=args.job_name,
        cpus_per_task=args.cpus_per_task,
        array_concurrency=args.array_concurrency,
        time_limit=args.time,
        partition=args.partition,
        account=args.account,
        gres=args.gres,
        setup_command=args.setup_command,
        oslab_command=args.oslab_command,
    )
    print(json.dumps(_export_to_json(export), indent=2))
    return 0


def _hpc_config_from_args(args: argparse.Namespace, default_job_name: str, default_time: str, default_cpus: int = 1, default_gres: str | None = None) -> HpcJobConfig:
    return HpcJobConfig(
        job_name=args.job_name or default_job_name,
        cpus_per_task=args.cpus_per_task or default_cpus,
        time_limit=args.time or default_time,
        partition=args.partition,
        account=args.account,
        gres=args.gres if args.gres is not None else default_gres,
        memory=args.memory,
        setup_command=args.setup_command,
    )


def cmd_hpc_export_slurm_hit_refinement(args: argparse.Namespace) -> int:
    export = export_slurm_hit_refinement(
        results_json=args.results_json,
        output_dir=args.out,
        top_n=args.top_n,
        exhaustiveness=args.exhaustiveness,
        num_modes=args.num_modes,
        cpu=args.cpu,
        seeds=args.seeds,
        run_plip=not args.no_plip,
        plip_top_n=args.plip_top_n,
        config=_hpc_config_from_args(args, "oslab-hit-refine", "12:00:00", default_cpus=max(1, args.cpu)),
        oslab_command=args.oslab_command,
    )
    print(json.dumps(_export_to_json(export), indent=2))
    return 0


def cmd_hpc_export_slurm_md_optimization(args: argparse.Namespace) -> int:
    export = export_slurm_md_optimization(
        root=args.root or default_project_root(),
        results_json=args.results_json,
        output_dir=args.out,
        top_n=args.top_n,
        ph=args.ph,
        water_padding_nm=args.water_padding_nm,
        ionic_strength_m=args.ionic_strength_m,
        temperature_k=args.temperature_k,
        minimization_steps=args.minimization_steps,
        smirnoff_forcefield=args.smirnoff_forcefield,
        timestep_fs=args.timestep_fs,
        nvt_ns=args.nvt_ns,
        npt_ns=args.npt_ns,
        production_ns=args.production_ns,
        n_frames=args.n_frames,
        crop_radius_angstrom=args.crop_radius_angstrom,
        max_solvated_atoms=args.max_solvated_atoms,
        config=_hpc_config_from_args(args, "oslab-md", "24:00:00", default_cpus=4, default_gres="gpu:1"),
        oslab_command=args.oslab_command,
    )
    print(json.dumps(_export_to_json(export), indent=2))
    return 0


def cmd_hpc_export_slurm_fep(args: argparse.Namespace) -> int:
    export = export_slurm_fep(
        root=args.root or default_project_root(),
        md_progress_json=args.md_progress_json,
        output_dir=args.out,
        top_n=args.top_n,
        n_lambda=args.n_lambda,
        n_steps_per_window=args.n_steps_per_window,
        n_equilibration_steps=args.n_equilibration_steps,
        temperature_k=args.temperature_k,
        forcefield=args.forcefield,
        input_mode=args.input_mode,
        analog_parent=args.analog_parent,
        n_analogs=args.n_analogs,
        config=_hpc_config_from_args(args, "oslab-fep", "48:00:00", default_cpus=4, default_gres="gpu:1"),
        oslab_command=args.oslab_command,
    )
    print(json.dumps(_export_to_json(export), indent=2))
    return 0


def _export_to_json(export: object) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in export.__dict__.items():
        if isinstance(value, Path):
            result[key] = str(value)
        elif isinstance(value, list):
            result[key] = [str(item) for item in value]
        else:
            result[key] = value
    return result


def cmd_plan(args: argparse.Namespace) -> int:
    workflow = build_docking_workflow(
        receptor=args.receptor,
        ligands=args.ligands,
        output_dir=args.out,
        center=args.center,
        size=args.size,
        ligand_source_key=args.ligand_source,
    )
    args.out.mkdir(parents=True, exist_ok=True)
    for subdir in ("prepared", "ligands", "docking"):
        (args.out / subdir).mkdir(exist_ok=True)
    workflow.manifest_path.write_text(json.dumps(workflow.to_dict(), indent=2) + "\n")
    print(workflow.manifest_path)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    data = json.loads(args.manifest.read_text())
    workflow = Workflow.from_dict(data)
    for index, step in enumerate(workflow.steps, start=1):
        print(f"[{index}/{len(workflow.steps)}] {step.name}")
        print("  " + " ".join(step.argv))
        if args.dry_run:
            continue
        for output in step.outputs:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(step.argv, check=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oslab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check-tools", help="Report installed open-source engines.")
    check.set_defaults(func=cmd_check_tools)

    ligand_sources = subparsers.add_parser("ligand-sources", help="Show ligand source choices and prep requirements.")
    ligand_sources.add_argument("--json", action="store_true", help="Emit machine-readable source metadata.")
    ligand_sources.set_defaults(func=cmd_ligand_sources)

    filter_presets = subparsers.add_parser("filter-presets", help="Show visible ligand filter presets.")
    filter_presets.add_argument("--preset", help="Emit one preset as JSON.")
    filter_presets.set_defaults(func=cmd_filter_presets)

    configure = subparsers.add_parser("configure", help="Save the default Open Structure Lab workspace location.")
    configure.add_argument("--root", type=Path, default=default_project_root(), help="Workspace folder for data, runs, logs, and reports.")
    configure.set_defaults(func=cmd_configure)

    init_project = subparsers.add_parser("init-project", help="Create project run/cache/report directories.")
    init_project.add_argument("--root", type=Path, default=default_project_root())
    init_project.add_argument("--set-default", action="store_true", help="Also save this root for future oslab commands.")
    init_project.set_defaults(func=cmd_init_project)

    demo = subparsers.add_parser("install-demo", help="Install compact bundled FOXP3 example results into a workspace.")
    demo.add_argument("--root", type=Path, default=default_project_root())
    demo.add_argument("--overwrite", action="store_true")
    demo.set_defaults(func=cmd_install_demo)

    fetch_bench = subparsers.add_parser(
        "fetch-benchmark",
        help="Download a public benchmark dataset (e.g. DUD-E CDK2) into <workspace>/benchmarks/<name>/.",
    )
    fetch_bench.add_argument("name", nargs="?", default="cdk2-dude", help="Benchmark name (default: cdk2-dude).")
    fetch_bench.add_argument("--to", type=Path, default=default_project_root(), help="Workspace root.")
    fetch_bench.add_argument("--overwrite", action="store_true", help="Re-download even if files already exist.")
    fetch_bench.add_argument("--list", action="store_true", help="List known benchmarks and exit.")
    fetch_bench.set_defaults(func=cmd_fetch_benchmark)

    structures = subparsers.add_parser("structures", help="Fetch/register/list protein structures.")
    structure_subparsers = structures.add_subparsers(dest="structure_command", required=True)

    fetch_pdb = structure_subparsers.add_parser("fetch-pdb", help="Download an experimental structure from RCSB PDB.")
    fetch_pdb.add_argument("pdb_id")
    fetch_pdb.add_argument("--root", type=Path, default=default_project_root())
    fetch_pdb.add_argument("--format", choices=["cif", "pdb"], default="cif")
    fetch_pdb.add_argument("--overwrite", action="store_true")
    fetch_pdb.set_defaults(func=cmd_fetch_pdb)

    fetch_af = structure_subparsers.add_parser("fetch-alphafold", help="Download a predicted structure from AlphaFold DB.")
    fetch_af.add_argument("accession")
    fetch_af.add_argument("--root", type=Path, default=default_project_root())
    fetch_af.add_argument("--model-version", type=int, default=None)
    fetch_af.add_argument("--overwrite", action="store_true")
    fetch_af.set_defaults(func=cmd_fetch_alphafold)

    register_local = structure_subparsers.add_parser("register-local", help="Register a local PDB/mmCIF structure.")
    register_local.add_argument("path", type=Path)
    register_local.add_argument("--root", type=Path, default=default_project_root())
    register_local.add_argument("--identifier")
    register_local.add_argument("--format", choices=["pdb", "cif", "mmcif"])
    register_local.add_argument("--no-copy", action="store_true")
    register_local.add_argument("--overwrite", action="store_true")
    register_local.set_defaults(func=cmd_register_local_structure)

    list_structures = structure_subparsers.add_parser("list", help="List cached/registered structures.")
    list_structures.add_argument("--root", type=Path, default=default_project_root())
    list_structures.add_argument("--json", action="store_true")
    list_structures.set_defaults(func=cmd_list_structures)

    protein = subparsers.add_parser("protein", help="Prepare and inspect protein structures.")
    protein_subparsers = protein.add_subparsers(dest="protein_command", required=True)

    prepare = protein_subparsers.add_parser("prepare", help="Prepare a protein with PDBFixer/OpenMM.")
    prepare.add_argument("--structure", required=True, type=Path)
    prepare.add_argument("--out", required=True, type=Path)
    prepare.add_argument("--ph", type=float, default=7.4)
    prepare.add_argument("--keep-water", action="store_true")
    prepare.add_argument("--no-minimize", action="store_true")
    prepare.add_argument("--max-minimization-iterations", type=int, default=500)
    prepare.set_defaults(func=cmd_prepare_protein)

    binding_site = subparsers.add_parser("binding-site", help="Choose docking-box centers and sizes.")
    binding_site_subparsers = binding_site.add_subparsers(dest="binding_site_command", required=True)

    ligand_names = binding_site_subparsers.add_parser("ligands", help="List likely ligand residue names in a structure.")
    ligand_names.add_argument("--structure", required=True, type=Path)
    ligand_names.add_argument("--json", action="store_true")
    ligand_names.set_defaults(func=cmd_binding_site_ligands)

    from_ligand = binding_site_subparsers.add_parser("from-ligand", help="Create a docking box from a ligand centroid.")
    from_ligand.add_argument("--structure", required=True, type=Path)
    from_ligand.add_argument("--ligand", required=True)
    from_ligand.add_argument("--out", required=True, type=Path)
    from_ligand.add_argument("--chain")
    from_ligand.add_argument("--padding", type=float, default=6.0)
    from_ligand.add_argument("--minimum-size", type=float, default=12.0)
    from_ligand.set_defaults(func=cmd_binding_site_from_ligand)

    from_residues = binding_site_subparsers.add_parser("from-residues", help="Create a docking box from residue centroids.")
    from_residues.add_argument("--structure", required=True, type=Path)
    from_residues.add_argument("--residue", action="append", required=True, help="Residue selector like A:145. Repeatable.")
    from_residues.add_argument("--out", required=True, type=Path)
    from_residues.add_argument("--padding", type=float, default=6.0)
    from_residues.add_argument("--minimum-size", type=float, default=12.0)
    from_residues.set_defaults(func=cmd_binding_site_from_residues)

    ligands = subparsers.add_parser("ligands", help="Prepare, filter, and inspect ligand libraries.")
    ligand_subparsers = ligands.add_subparsers(dest="ligand_command", required=True)

    filter_cmd = ligand_subparsers.add_parser("filter", help="Filter a ligand file with a visible RDKit preset.")
    filter_cmd.add_argument("--input", required=True, type=Path)
    filter_cmd.add_argument("--out", required=True, type=Path)
    filter_cmd.add_argument("--preset", default="drug_like", choices=list_ligand_filter_presets())
    filter_cmd.set_defaults(func=cmd_filter_ligands)

    prep_cmd = ligand_subparsers.add_parser("prepare-vina", help="Convert filtered ligands to Vina-ready PDBQT files.")
    prep_cmd.add_argument("--input", required=True, type=Path, help="Input SDF, typically included.sdf from ligand filtering.")
    prep_cmd.add_argument("--out", required=True, type=Path)
    prep_cmd.add_argument("--ph", type=float, default=7.4)
    prep_cmd.add_argument("--no-gen3d", action="store_true")
    prep_cmd.add_argument("--charge-model", choices=["gasteiger", "espaloma", "zero", "read"], default="gasteiger")
    prep_cmd.add_argument("--backend", choices=["rdkit", "openbabel"], default="rdkit")
    prep_cmd.add_argument("--workers", type=int, default=1)
    prep_cmd.add_argument("--timeout-seconds", type=int, default=120)
    prep_cmd.set_defaults(func=cmd_prepare_ligands)

    docking = subparsers.add_parser("docking", help="Prepare receptors and run AutoDock Vina.")
    docking_subparsers = docking.add_subparsers(dest="docking_command", required=True)

    receptor_cmd = docking_subparsers.add_parser("prepare-receptor", help="Convert a prepared receptor PDB to PDBQT.")
    receptor_cmd.add_argument("--input", required=True, type=Path)
    receptor_cmd.add_argument("--out", required=True, type=Path)
    receptor_cmd.add_argument("--binding-site", type=Path)
    receptor_cmd.add_argument("--allow-bad-residues", action="store_true")
    receptor_cmd.add_argument("--default-altloc")
    receptor_cmd.add_argument("--delete-residues", help="Meeko residue deletion selector, e.g. A:400")
    receptor_cmd.set_defaults(func=cmd_prepare_receptor_vina)

    vina_cmd = docking_subparsers.add_parser("run-vina", help="Run AutoDock Vina for one ligand PDBQT.")
    vina_cmd.add_argument("--receptor", required=True, type=Path)
    vina_cmd.add_argument("--ligand", required=True, type=Path)
    vina_cmd.add_argument("--binding-site", required=True, type=Path)
    vina_cmd.add_argument("--out", required=True, type=Path)
    vina_cmd.add_argument("--exhaustiveness", type=int, default=8)
    vina_cmd.add_argument("--num-modes", type=int, default=9)
    vina_cmd.add_argument("--cpu", type=int, default=0)
    vina_cmd.add_argument("--seed", type=int, default=0)
    vina_cmd.set_defaults(func=cmd_run_vina)

    results = subparsers.add_parser("results", help="Summarize and report workflow results.")
    results_subparsers = results.add_subparsers(dest="results_command", required=True)

    summarize_vina = results_subparsers.add_parser("summarize-vina", help="Summarize Vina run JSON files.")
    summarize_vina.add_argument("--vina-run", type=Path, action="append", required=True)
    summarize_vina.add_argument("--interaction-analysis", type=Path, action="append")
    summarize_vina.add_argument("--out", required=True, type=Path)
    summarize_vina.set_defaults(func=cmd_summarize_vina)

    summarize_validation = results_subparsers.add_parser(
        "summarize-validation", help="Summarize redocking validation JSON files."
    )
    summarize_validation.add_argument("--validation-run", type=Path, action="append", required=True)
    summarize_validation.add_argument("--out", required=True, type=Path)
    summarize_validation.add_argument("--no-overlay", action="store_true")
    summarize_validation.set_defaults(func=cmd_summarize_validation)

    visualize = subparsers.add_parser("visualize", help="Generate HTML molecular visualizations.")
    visualize_subparsers = visualize.add_subparsers(dest="visualize_command", required=True)

    visualize_site = visualize_subparsers.add_parser("binding-site", help="Render a binding-site box in 3Dmol.js HTML.")
    visualize_site.add_argument("--structure", required=True, type=Path)
    visualize_site.add_argument("--binding-site", required=True, type=Path)
    visualize_site.add_argument("--out", required=True, type=Path)
    visualize_site.add_argument("--docked-ligand", type=Path)
    visualize_site.set_defaults(func=cmd_visualize_binding_site)

    interactions = subparsers.add_parser("interactions", help="Analyze protein-ligand interactions.")
    interactions_subparsers = interactions.add_subparsers(dest="interactions_command", required=True)

    plip_cmd = interactions_subparsers.add_parser("plip", help="Run PLIP on a docked receptor-ligand complex.")
    plip_cmd.add_argument("--receptor-pdbqt", required=True, type=Path)
    plip_cmd.add_argument("--docked-ligand", required=True, type=Path)
    plip_cmd.add_argument("--out", required=True, type=Path)
    plip_cmd.set_defaults(func=cmd_interactions_plip)

    validation = subparsers.add_parser("validation", help="Validate docking workflows against known structures.")
    validation_subparsers = validation.add_subparsers(dest="validation_command", required=True)

    redock = validation_subparsers.add_parser("redock", help="Redock a crystallographic ligand and calculate RMSD.")
    redock.add_argument("--structure", required=True, type=Path)
    redock.add_argument("--ligand", required=True)
    redock.add_argument("--chain")
    redock.add_argument("--residue-number", type=int)
    redock.add_argument("--receptor", required=True, type=Path)
    redock.add_argument("--binding-site", required=True, type=Path)
    redock.add_argument("--out", required=True, type=Path)
    redock.add_argument("--exhaustiveness", type=int, default=8)
    redock.add_argument("--num-modes", type=int, default=1)
    redock.add_argument("--cpu", type=int, default=1)
    redock.add_argument("--seed", type=int, default=1)
    redock.set_defaults(func=cmd_validation_redock)

    screen = subparsers.add_parser("screen", help="Run small deterministic ligand screens.")
    screen_subparsers = screen.add_subparsers(dest="screen_command", required=True)

    small_screen = screen_subparsers.add_parser("small", help="Filter, prepare, dock, analyze, and report a small ligand set.")
    small_screen.add_argument("--ligands", required=True, type=Path)
    small_screen.add_argument("--receptor", required=True, type=Path, help="Prepared receptor PDBQT.")
    small_screen.add_argument("--binding-site", required=True, type=Path)
    small_screen.add_argument("--out", required=True, type=Path)
    small_screen.add_argument("--max-ligands", type=int, default=20)
    small_screen.add_argument("--preset", default="drug_like", choices=list_ligand_filter_presets())
    small_screen.add_argument("--ph", type=float, default=7.4)
    small_screen.add_argument("--no-gen3d", action="store_true")
    small_screen.add_argument("--charge-model", choices=["gasteiger", "espaloma", "zero", "read"], default="gasteiger")
    small_screen.add_argument("--ligand-prep-backend", choices=["rdkit", "openbabel"], default="rdkit")
    small_screen.add_argument("--ligand-prep-workers", type=int, default=1)
    small_screen.add_argument("--ligand-prep-timeout", type=int, default=120)
    small_screen.add_argument("--docking-workers", type=int, default=1)
    small_screen.add_argument("--execution-backend", choices=["local", "slurm-export"], default="local")
    small_screen.add_argument("--slurm-job-name", default="oslab-vina")
    small_screen.add_argument("--slurm-cpus-per-task", type=int, default=1)
    small_screen.add_argument("--slurm-array-concurrency", type=int)
    small_screen.add_argument("--slurm-time", default="04:00:00")
    small_screen.add_argument("--slurm-partition")
    small_screen.add_argument("--slurm-account")
    small_screen.add_argument("--slurm-gres", help="Optional SLURM generic resource request, e.g. gpu:1.")
    small_screen.add_argument("--slurm-setup-command", help="Shell command to load modules/activate env before each task.")
    small_screen.add_argument("--oslab-command", default="oslab")
    small_screen.add_argument("--no-plip", action="store_true")
    small_screen.add_argument("--exhaustiveness", type=int, default=1)
    small_screen.add_argument("--num-modes", type=int, default=1)
    small_screen.add_argument("--cpu", type=int, default=1)
    small_screen.add_argument("--seed", type=int, default=1)
    small_screen.add_argument("--report-context-json", type=Path, help="Optional JSON file with target, ligand library, and user-entered run context for the report.")
    small_screen.set_defaults(func=cmd_screen_small)

    pdbqt_screen = screen_subparsers.add_parser(
        "pdbqt-dir",
        help="Dock an existing directory of Vina-ready ligand PDBQT files without ligand preparation.",
    )
    pdbqt_screen.add_argument("--ligand-dir", required=True, type=Path, help="Directory containing prepared ligand .pdbqt files.")
    pdbqt_screen.add_argument("--receptor", required=True, type=Path, help="Prepared receptor PDBQT.")
    pdbqt_screen.add_argument("--binding-site", required=True, type=Path)
    pdbqt_screen.add_argument("--out", required=True, type=Path)
    pdbqt_screen.add_argument("--max-ligands", type=int, help="Maximum prepared PDBQT ligands to dock. Omit to dock every .pdbqt file.")
    pdbqt_screen.add_argument("--docking-workers", type=int, default=1)
    pdbqt_screen.add_argument("--no-plip", action="store_true")
    pdbqt_screen.add_argument("--exhaustiveness", type=int, default=1)
    pdbqt_screen.add_argument("--num-modes", type=int, default=1)
    pdbqt_screen.add_argument("--cpu", type=int, default=1)
    pdbqt_screen.add_argument("--seed", type=int, default=1)
    pdbqt_screen.add_argument("--progress-json", type=Path)
    pdbqt_screen.add_argument("--report-context-json", type=Path, help="Optional JSON file with target, ligand library, and user-entered run context for the report.")
    pdbqt_screen.set_defaults(func=cmd_screen_pdbqt_dir)

    dashboard = subparsers.add_parser("dashboard", help="Run the local HTML dashboard.")
    dashboard_subparsers = dashboard.add_subparsers(dest="dashboard_command", required=True)

    dashboard_serve = dashboard_subparsers.add_parser("serve", help="Serve the local dashboard.")
    dashboard_serve.add_argument("--root", type=Path, default=default_project_root())
    dashboard_serve.add_argument("--host", default="127.0.0.1")
    dashboard_serve.add_argument("--port", type=int, default=8765)
    dashboard_serve.add_argument("--open-browser", action="store_true")
    dashboard_serve.set_defaults(func=cmd_dashboard_serve)

    orchestrate = subparsers.add_parser("orchestrate", help="Run deterministic orchestration flows.")
    orchestrate_subparsers = orchestrate.add_subparsers(dest="orchestrate_command", required=True)
    terminal_orch = orchestrate_subparsers.add_parser("terminal", help="Start an interactive terminal orchestration wizard.")
    terminal_orch.add_argument("--root", type=Path, default=default_project_root())
    terminal_orch.add_argument("--progress-json", type=Path)
    terminal_orch.set_defaults(func=cmd_orchestrate_terminal)

    refine = subparsers.add_parser("refine", help="Refine and rescore top docking hits.")
    refine_subparsers = refine.add_subparsers(dest="refine_command", required=True)
    refine_hits = refine_subparsers.add_parser("hits", help="Re-dock top hits from a completed docking report.")
    refine_hits.add_argument("--root", type=Path, default=default_project_root())
    refine_hits.add_argument("--interactive", action="store_true", help="Ask the user to choose from recent docking runs.")
    refine_hits.add_argument("--results-json", type=Path, help="Existing vina_results.json to refine.")
    refine_hits.add_argument("--out", type=Path, help="Output directory for hit refinement.")
    refine_hits.add_argument("--top-n", type=int, default=20)
    refine_hits.add_argument("--exhaustiveness", type=int, default=16)
    refine_hits.add_argument("--num-modes", type=int, default=3)
    refine_hits.add_argument("--cpu", type=int, default=1)
    refine_hits.add_argument("--workers", type=int, default=1, help="Number of concurrent Vina re-docking jobs.")
    refine_hits.add_argument("--seeds", default="1,2,3")
    refine_hits.add_argument("--no-plip", action="store_true")
    refine_hits.add_argument("--plip-top-n", type=int, help="If PLIP is enabled, run PLIP on this many ligands from the post-refinement composite ranking.")
    refine_hits.add_argument("--progress-json", type=Path)
    refine_hits.set_defaults(func=cmd_refine_hits)

    cluster = subparsers.add_parser("cluster", help="Cluster and diversify docking hit lists.")
    cluster_subparsers = cluster.add_subparsers(dest="cluster_command", required=True)
    cluster_hits = cluster_subparsers.add_parser(
        "hits",
        help="Cluster docking hits and write a Block-2-compatible representative results JSON.",
    )
    cluster_hits.add_argument("--results-json", required=True, type=Path, help="Existing vina_results.json to cluster.")
    cluster_hits.add_argument("--out", required=True, type=Path, help="Output directory for hit clustering.")
    cluster_hits.add_argument("--top-n", type=int, default=300, help="Maximum representatives to pass into Block 2.")
    cluster_hits.add_argument("--similarity-threshold", type=float, default=0.65)
    cluster_hits.add_argument("--radius", type=int, default=2, help="Morgan fingerprint radius.")
    cluster_hits.add_argument("--fp-size", type=int, default=2048, help="Morgan fingerprint bit vector size.")
    cluster_hits.add_argument(
        "--max-per-cluster",
        type=int,
        default=3,
        help="Maximum selected ligands from any one cluster before Block 2.",
    )
    cluster_hits.add_argument("--progress-json", type=Path)
    cluster_hits.set_defaults(func=cmd_cluster_hits)

    md = subparsers.add_parser("md", help="Molecular dynamics and MMGBSA rescoring.")
    md_subparsers = md.add_subparsers(dest="md_command", required=True)

    md_prep = md_subparsers.add_parser(
        "prep", help="Prepare a solvated protein-ligand system for MD (GAFF2 + TIP3P)."
    )
    md_prep.add_argument("--receptor", required=True, type=Path, help="Receptor PDBQT from docking setup.")
    md_prep.add_argument("--docked-ligand", required=True, type=Path, help="Vina docked output PDBQT.")
    md_prep.add_argument("--smiles", default="", help="Ligand SMILES (falls back to REMARK SMILES in PDBQT).")
    md_prep.add_argument("--ligand-pdbqt", type=Path, help="Input ligand PDBQT (for SMILES extraction fallback).")
    md_prep.add_argument("--protein-pdb", type=Path, help="Pre-prepared protein PDB; skips PDBQT conversion.")
    md_prep.add_argument("--out", required=True, type=Path)
    md_prep.add_argument("--ph", type=float, default=7.4)
    md_prep.add_argument("--keep-water", action="store_true")
    md_prep.add_argument("--water-padding-nm", type=float, default=1.2)
    md_prep.add_argument("--ionic-strength-m", type=float, default=0.15)
    md_prep.add_argument("--temperature-k", type=float, default=300.0)
    md_prep.add_argument("--minimization-steps", type=int, default=1000)
    md_prep.add_argument("--smirnoff-forcefield", default="openff-2.2.0",
                         help="OpenFF SMIRNOFF force field name (e.g. openff-2.2.0).")
    md_prep.set_defaults(func=cmd_md_prep)

    md_run = md_subparsers.add_parser("run", help="Run NVT+NPT equilibration and production MD.")
    md_run.add_argument("--topology", required=True, type=Path, help="topology.pdb from md prep.")
    md_run.add_argument("--system-xml", required=True, type=Path, help="system.xml from md prep.")
    md_run.add_argument("--out", required=True, type=Path)
    md_run.add_argument("--timestep-fs", type=float, default=2.0)
    md_run.add_argument("--temperature-k", type=float, default=300.0)
    md_run.add_argument("--nvt-ns", type=float, default=0.1)
    md_run.add_argument("--npt-ns", type=float, default=0.1)
    md_run.add_argument("--production-ns", type=float, default=1.0)
    md_run.add_argument("--save-every-steps", type=int, default=5000)
    md_run.set_defaults(func=cmd_md_run)

    md_interactions = md_subparsers.add_parser(
        "interactions", help="ProLIF fingerprinting on an MD trajectory."
    )
    md_interactions.add_argument("--topology", required=True, type=Path)
    md_interactions.add_argument("--trajectory", required=True, type=Path)
    md_interactions.add_argument("--out", required=True, type=Path)
    md_interactions.add_argument("--plip-json", type=Path, help="Static PLIP interaction_summary.json for comparison.")
    md_interactions.add_argument("--step", type=int, default=1, help="Analyse every N-th frame.")
    md_interactions.set_defaults(func=cmd_md_interactions)

    md_mmgbsa = md_subparsers.add_parser(
        "mmgbsa", help="MMGBSA binding energy estimate from an MD trajectory."
    )
    md_mmgbsa.add_argument("--topology", required=True, type=Path)
    md_mmgbsa.add_argument("--trajectory", required=True, type=Path)
    md_mmgbsa.add_argument("--out", required=True, type=Path)
    md_mmgbsa.add_argument("--n-frames", type=int, default=50)
    md_mmgbsa.add_argument("--smirnoff-forcefield", default="openff-2.2.0",
                           help="OpenFF SMIRNOFF force field name (e.g. openff-2.2.0).")
    md_mmgbsa.set_defaults(func=cmd_md_mmgbsa)

    md_optimize = md_subparsers.add_parser(
        "optimize",
        help="Run full MD pipeline (prep + sim + ProLIF + MMGBSA) for top ligands from a docking or hit-refinement run.",
    )
    md_optimize.add_argument("--interactive", action="store_true", help="Ask for MD inputs/settings in Terminal.")
    md_optimize.add_argument(
        "--results-json", type=Path,
        help="vina_results.json or per_ligand_summary.json from docking / hit-refinement.",
    )
    md_optimize.add_argument("--out", type=Path, help="Output directory for all MD results.")
    md_optimize.add_argument("--root", type=Path, default=None, help="Project root (default: current directory).")
    md_optimize.add_argument("--top-n", type=int, default=3, help="Number of top ligands to run MD on.")
    md_optimize.add_argument("--progress-json", type=Path, help="Path to write live progress JSON.")
    md_optimize.add_argument("--ph", type=float, default=7.4)
    md_optimize.add_argument("--water-padding-nm", type=float, default=1.2)
    md_optimize.add_argument("--ionic-strength-m", type=float, default=0.15)
    md_optimize.add_argument("--temperature-k", type=float, default=300.0)
    md_optimize.add_argument("--minimization-steps", type=int, default=1000)
    md_optimize.add_argument("--smirnoff-forcefield", default="openff-2.2.0")
    md_optimize.add_argument("--timestep-fs", type=float, default=2.0)
    md_optimize.add_argument("--nvt-ns", type=float, default=0.1)
    md_optimize.add_argument("--npt-ns", type=float, default=0.1)
    md_optimize.add_argument("--production-ns", type=float, default=1.0)
    md_optimize.add_argument("--n-frames", type=int, default=50)
    md_optimize.add_argument(
        "--crop-radius-angstrom", type=float, default=15.0,
        help="Crop receptor to residues within this distance of the docked ligand. Set to 0 to disable cropping.",
    )
    md_optimize.add_argument(
        "--max-solvated-atoms", type=int, default=200000,
        help="Fail fast if estimated solvated system exceeds this atom count.",
    )
    _add_gpu_assignment_args(md_optimize)
    md_optimize.set_defaults(func=cmd_md_optimize)

    hpc = subparsers.add_parser("hpc", help="Export scheduler jobs for cluster execution.")
    hpc_subparsers = hpc.add_subparsers(dest="hpc_command", required=True)

    slurm_docking = hpc_subparsers.add_parser("export-slurm-docking", help="Export a SLURM array job for Vina docking.")
    slurm_docking.add_argument("--receptor", required=True, type=Path)
    slurm_docking.add_argument("--binding-site", required=True, type=Path)
    slurm_docking.add_argument("--ligand-dir", required=True, type=Path, help="Directory containing ligand PDBQT files.")
    slurm_docking.add_argument("--out", required=True, type=Path)
    slurm_docking.add_argument("--job-name", default="oslab-vina")
    slurm_docking.add_argument("--cpus-per-task", type=int, default=1)
    slurm_docking.add_argument("--array-concurrency", type=int)
    slurm_docking.add_argument("--time", default="04:00:00")
    slurm_docking.add_argument("--partition")
    slurm_docking.add_argument("--account")
    slurm_docking.add_argument("--gres", help="Optional SLURM generic resource request, e.g. gpu:1.")
    slurm_docking.add_argument("--setup-command", help="Shell command to load modules/activate env before each task.")
    slurm_docking.add_argument("--oslab-command", default="oslab")
    slurm_docking.add_argument("--exhaustiveness", type=int, default=1)
    slurm_docking.add_argument("--num-modes", type=int, default=1)
    slurm_docking.add_argument("--vina-cpu", type=int, default=1)
    slurm_docking.add_argument("--seed", type=int, default=1)
    slurm_docking.set_defaults(func=cmd_hpc_export_slurm_docking)

    slurm_refine = hpc_subparsers.add_parser("export-slurm-hit-refinement", help="Export a SLURM job for Block 2 hit refinement.")
    slurm_refine.add_argument("--results-json", required=True, type=Path)
    slurm_refine.add_argument("--out", required=True, type=Path)
    slurm_refine.add_argument("--top-n", type=int, default=20)
    slurm_refine.add_argument("--exhaustiveness", type=int, default=16)
    slurm_refine.add_argument("--num-modes", type=int, default=3)
    slurm_refine.add_argument("--cpu", type=int, default=1)
    slurm_refine.add_argument("--seeds", default="1,2,3")
    slurm_refine.add_argument("--no-plip", action="store_true")
    slurm_refine.add_argument("--plip-top-n", type=int)
    _add_slurm_single_job_args(slurm_refine, default_job_name="oslab-hit-refine")
    slurm_refine.set_defaults(func=cmd_hpc_export_slurm_hit_refinement)

    slurm_md = hpc_subparsers.add_parser("export-slurm-md-optimization", help="Export a SLURM job for Block 3 MD and Optimization.")
    slurm_md.add_argument("--root", type=Path, default=None)
    slurm_md.add_argument("--results-json", required=True, type=Path)
    slurm_md.add_argument("--out", required=True, type=Path)
    slurm_md.add_argument("--top-n", type=int, default=3)
    slurm_md.add_argument("--ph", type=float, default=7.4)
    slurm_md.add_argument("--water-padding-nm", type=float, default=1.2)
    slurm_md.add_argument("--ionic-strength-m", type=float, default=0.15)
    slurm_md.add_argument("--temperature-k", type=float, default=300.0)
    slurm_md.add_argument("--minimization-steps", type=int, default=1000)
    slurm_md.add_argument("--smirnoff-forcefield", default="openff-2.2.0")
    slurm_md.add_argument("--timestep-fs", type=float, default=2.0)
    slurm_md.add_argument("--nvt-ns", type=float, default=0.1)
    slurm_md.add_argument("--npt-ns", type=float, default=0.1)
    slurm_md.add_argument("--production-ns", type=float, default=1.0)
    slurm_md.add_argument("--n-frames", type=int, default=50)
    slurm_md.add_argument("--crop-radius-angstrom", type=float, default=15.0)
    slurm_md.add_argument("--max-solvated-atoms", type=int, default=200000)
    _add_slurm_single_job_args(slurm_md, default_job_name="oslab-md")
    slurm_md.set_defaults(func=cmd_hpc_export_slurm_md_optimization)

    slurm_fep = hpc_subparsers.add_parser("export-slurm-fep", help="Export a SLURM job for Block 4 OpenFE FEP.")
    slurm_fep.add_argument("--root", type=Path, default=None)
    slurm_fep.add_argument("--md-progress-json", required=True, type=Path)
    slurm_fep.add_argument("--out", required=True, type=Path)
    slurm_fep.add_argument("--top-n", type=int, default=3)
    slurm_fep.add_argument("--n-lambda", type=int, default=11)
    slurm_fep.add_argument("--n-steps-per-window", type=int, default=25000)
    slurm_fep.add_argument("--n-equilibration-steps", type=int, default=5000)
    slurm_fep.add_argument("--temperature-k", type=float, default=300.0)
    slurm_fep.add_argument("--forcefield", default="openff-2.2.1")
    slurm_fep.add_argument("--input-mode", choices=["topn", "analog"], default="topn")
    slurm_fep.add_argument("--analog-parent")
    slurm_fep.add_argument("--n-analogs", type=int, default=20)
    _add_slurm_single_job_args(slurm_fep, default_job_name="oslab-fep")
    slurm_fep.set_defaults(func=cmd_hpc_export_slurm_fep)

    plan = subparsers.add_parser("plan", help="Create a docking workflow manifest.")
    plan.add_argument("--receptor", required=True, type=Path)
    plan.add_argument("--ligands", required=True, type=Path)
    plan.add_argument("--ligand-source", default="custom-sdf", choices=sorted(LIGAND_SOURCES))
    plan.add_argument("--center", required=True, nargs=3)
    plan.add_argument("--size", required=True, nargs=3)
    plan.add_argument("--out", required=True, type=Path)
    plan.set_defaults(func=cmd_plan)

    run = subparsers.add_parser("run", help="Run a workflow manifest.")
    run.add_argument("manifest", type=Path)
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(func=cmd_run)

    fep = subparsers.add_parser("fep", help="Block 4: Alchemical relative binding free energy (RBFE) with official OpenFE.")
    fep_subparsers = fep.add_subparsers(dest="fep_command", required=True)

    fep_run = fep_subparsers.add_parser(
        "run", help="Run OpenFE RBFE pipeline for top ligands from an MD optimization run."
    )
    fep_run.add_argument("--root", type=Path, default=None, help="Project root directory.")
    fep_run.add_argument("--interactive", action="store_true", help="Interactive terminal wizard mode (default for dashboard).")
    fep_run.add_argument("--md-progress-json", type=Path, help="progress.json from a completed MD optimization run.")
    fep_run.add_argument("--top-n", type=int, default=3, help="Top N MD-pass ligands, preserving Block 2 rank order, to include in FEP.")
    fep_run.add_argument("--n-lambda", type=int, default=11, help="OpenFE lambda windows per transformation.")
    fep_run.add_argument("--n-steps-per-window", type=int, default=25000, help="OpenFE production MD steps per lambda window.")
    fep_run.add_argument("--n-equilibration-steps", type=int, default=5000, help="OpenFE equilibration steps per lambda window.")
    fep_run.add_argument("--temperature-k", type=float, default=300.0, help="Simulation temperature in Kelvin.")
    fep_run.add_argument("--forcefield", default="openff-2.2.1", help="SMIRNOFF force field for ligands.")
    fep_run.add_argument(
        "--max-minutes-per-transformation",
        type=float,
        default=None,
        help=(
            "Maximum wall time for each OpenFE transformation before it is marked timed_out "
            "and the next transformation is attempted. Defaults to "
            "OSLAB_OPENFE_MAX_MINUTES_PER_TRANSFORMATION or 240 minutes. Use 0 to disable."
        ),
    )
    fep_run.add_argument(
        "--input-mode",
        choices=["topn", "analog"],
        default="topn",
        help="topn: perturb across top-N MMGBSA hits. analog: auto-build a "
             "library of close analogs around one parent and FEP within it.",
    )
    fep_run.add_argument(
        "--analog-parent",
        type=str,
        default=None,
        help="(analog mode) Ligand name from the MD run to build analogs around. "
             "If omitted in non-interactive mode, the top-MMGBSA hit is used.",
    )
    fep_run.add_argument(
        "--n-analogs",
        type=int,
        default=20,
        help="(analog mode) Number of analogs to keep after filtering.",
    )
    fep_run.add_argument("--progress-json", type=Path, help="Path to write FEP progress JSON.")
    fep_run.add_argument("--out", type=Path, help="Output directory for FEP results.")
    _add_gpu_assignment_args(fep_run)
    fep_run.set_defaults(func=cmd_fep_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "center"):
        args.center = _triple(args.center, "center")
    if hasattr(args, "size"):
        args.size = _triple(args.size, "size")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
