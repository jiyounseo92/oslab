from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from rdkit import Chem

from .compound_registry import register_compound
from .docking import run_vina
from .interactions import run_plip_analysis
from .ligand_filtering import filter_ligands
from .ligand_prep import prepare_ligands_for_vina
from .md_prep import smiles_from_pdbqt
from .reporting import summarize_vina_runs
from .schemas import LigandPrepOptions, LigandPrepRecord, SmallScreenSummary, VinaRunOptions, VinaRunRecord


def run_small_screen(
    ligands: Path,
    receptor_pdbqt: Path,
    binding_site_json: Path,
    output_dir: Path,
    max_ligands: int = 20,
    preset: str = "drug_like",
    run_plip: bool = True,
    ligand_prep_options: LigandPrepOptions | None = None,
    vina_options: VinaRunOptions | None = None,
    report_context: dict[str, object] | None = None,
) -> SmallScreenSummary:
    if max_ligands < 1:
        raise ValueError("max_ligands must be at least 1")
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ligand_prep_options = ligand_prep_options or LigandPrepOptions()
    vina_options = vina_options or VinaRunOptions(exhaustiveness=1, num_modes=1, cpu=1, seed=1)

    existing_prep = _existing_ligand_prep_for_screen_input(ligands)
    if existing_prep:
        filter_summary_json, ligand_prep = existing_prep
        ligand_paths = [Path(path) for path in ligand_prep.pdbqt_files[:max_ligands]]
    else:
        filter_summary = filter_ligands(ligands, output_dir / "filtered", preset)
        limited_sdf = _write_limited_sdf(Path(filter_summary.included_sdf), output_dir / "ligands" / "screen_ligands.sdf", max_ligands)
        ligand_prep = prepare_ligands_for_vina(limited_sdf, output_dir / "ligand-vina-prep", ligand_prep_options)
        filter_summary_json = filter_summary.summary_json
        ligand_paths = [Path(path) for path in ligand_prep.pdbqt_files]

    vina_runs: list[Path] = []
    interaction_jsons: list[Path] = []
    docking_workers = max(1, int(getattr(vina_options, "workers", 1) or 1))
    if docking_workers == 1:
        for ligand_pdbqt in ligand_paths:
            run_path, interaction_path = _dock_one_ligand(
                receptor_pdbqt,
                ligand_pdbqt,
                binding_site_json,
                output_dir,
                vina_options,
                run_plip,
            )
            vina_runs.append(run_path)
            if interaction_path:
                interaction_jsons.append(interaction_path)
    else:
        with ThreadPoolExecutor(max_workers=docking_workers) as executor:
            futures = [
                executor.submit(
                    _dock_one_ligand,
                    receptor_pdbqt,
                    ligand_pdbqt,
                    binding_site_json,
                    output_dir,
                    vina_options,
                    run_plip,
                )
                for ligand_pdbqt in ligand_paths
            ]
            for future in as_completed(futures):
                run_path, interaction_path = future.result()
                vina_runs.append(run_path)
                if interaction_path:
                    interaction_jsons.append(interaction_path)

    report_context = {
        **(report_context or {}),
        "input_ligands": str(ligands.resolve()),
        "receptor_pdbqt": str(receptor_pdbqt.resolve()),
        "binding_site_json": str(binding_site_json.resolve()),
        "output_dir": str(output_dir),
        "requested_max_ligands": max_ligands,
        "prepared_ligands": ligand_prep.prepared_count,
        "docked_ligands": len(vina_runs),
        "interaction_analyses": len(interaction_jsons),
        "preset": preset,
        "run_plip": run_plip,
        "ligand_prep_options": ligand_prep_options.model_dump(mode="json"),
        "vina_options": vina_options.model_dump(mode="json"),
    }
    (output_dir / "report_context.json").write_text(json.dumps(report_context, indent=2) + "\n")
    report_summary = summarize_vina_runs(vina_runs, output_dir / "report", interaction_jsons if interaction_jsons else None, report_context=report_context)
    metadata_path = output_dir / "small_screen_summary.json"
    summary = SmallScreenSummary(
        input_ligands=str(ligands.resolve()),
        receptor_pdbqt=str(receptor_pdbqt.resolve()),
        binding_site_json=str(binding_site_json.resolve()),
        output_dir=str(output_dir),
        filter_summary_json=filter_summary_json,
        ligand_prep_json=ligand_prep.metadata_path,
        docking_report=report_summary.report_markdown,
        results_csv=report_summary.results_csv,
        results_json=report_summary.results_json,
        metadata_path=str(metadata_path),
        requested_max_ligands=max_ligands,
        prepared_ligands=ligand_prep.prepared_count,
        docked_ligands=len(vina_runs),
        interaction_analyses=len(interaction_jsons),
        best_ligand=report_summary.best_ligand,
        best_score=report_summary.best_score,
        vina_runs=[str(path.resolve()) for path in vina_runs],
        interaction_analysis_jsons=[str(path.resolve()) for path in interaction_jsons],
        created_at=datetime.now(timezone.utc),
        notes=(
            "Small screen reused existing ligand_prep.json and docked prepared PDBQT files."
            if existing_prep
            else "Small screen completed with RDKit filtering, Open Babel/Meeko ligand preparation, AutoDock Vina docking, optional PLIP analysis, and report generation."
        ),
    )
    metadata_path.write_text(json.dumps(summary.model_dump(mode="json"), indent=2) + "\n")
    return summary


def run_prepared_pdbqt_screen(
    ligand_dir: Path,
    receptor_pdbqt: Path,
    binding_site_json: Path,
    output_dir: Path,
    max_ligands: int | None = None,
    run_plip: bool = False,
    vina_options: VinaRunOptions | None = None,
    report_context: dict[str, object] | None = None,
    progress_json: Path | None = None,
) -> SmallScreenSummary:
    ligand_dir = ligand_dir.resolve()
    receptor_pdbqt = receptor_pdbqt.resolve()
    binding_site_json = binding_site_json.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    vina_options = vina_options or VinaRunOptions(exhaustiveness=1, num_modes=1, cpu=1, seed=1)

    ligand_paths = sorted(path for path in ligand_dir.glob("*.pdbqt") if path.is_file())
    if max_ligands is not None and max_ligands > 0:
        ligand_paths = ligand_paths[:max_ligands]
    if not ligand_paths:
        raise ValueError(f"no PDBQT ligands found in {ligand_dir}")

    failures_path = output_dir / "failures" / "docking_failures.tsv"
    if failures_path.exists():
        failures_path.unlink()

    def write_progress(done: int, message: str, status: str = "running") -> None:
        if not progress_json:
            return
        progress_json.parent.mkdir(parents=True, exist_ok=True)
        total = len(ligand_paths)
        progress = {
            "run_label": output_dir.name.removesuffix("-docking"),
            "current_step": "docking",
            "status": status,
            "phase": "docking",
            "prepared_count": total,
            "docked_count": done,
            "attempted_count": done,
            "target_count": total,
            "percent": round((done / total * 100.0) if total else 0.0, 3),
            "message": message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "report_dir": str(output_dir),
            "results_json": str(output_dir / "report" / "vina_results.json"),
            "ligand_pdbqt_dir": str(ligand_dir),
        }
        progress_json.write_text(json.dumps(progress, indent=2) + "\n")

    vina_runs: list[Path] = []
    interaction_jsons: list[Path] = []
    docking_workers = max(1, int(getattr(vina_options, "workers", 1) or 1))
    write_progress(0, f"Starting docking for {len(ligand_paths)} prepared PDBQT ligands.")
    if docking_workers == 1:
        for index, ligand_pdbqt in enumerate(ligand_paths, start=1):
            try:
                run_path, interaction_path = _dock_one_ligand(
                    receptor_pdbqt,
                    ligand_pdbqt,
                    binding_site_json,
                    output_dir,
                    vina_options,
                    run_plip,
                )
                vina_runs.append(run_path)
                if interaction_path:
                    interaction_jsons.append(interaction_path)
            except Exception as exc:
                failures_path.parent.mkdir(exist_ok=True)
                with failures_path.open("a", encoding="utf-8") as handle:
                    handle.write(f"{ligand_pdbqt}\t{type(exc).__name__}: {exc}\n")
            if index == len(ligand_paths) or index % 100 == 0:
                write_progress(index, f"Docked {index}/{len(ligand_paths)} ligands.")
    else:
        with ThreadPoolExecutor(max_workers=docking_workers) as executor:
            futures = {
                executor.submit(
                    _dock_one_ligand,
                    receptor_pdbqt,
                    ligand_pdbqt,
                    binding_site_json,
                    output_dir,
                    vina_options,
                    run_plip,
                ): ligand_pdbqt
                for ligand_pdbqt in ligand_paths
            }
            for index, future in enumerate(as_completed(futures), start=1):
                ligand_pdbqt = futures[future]
                try:
                    run_path, interaction_path = future.result()
                    vina_runs.append(run_path)
                    if interaction_path:
                        interaction_jsons.append(interaction_path)
                except Exception as exc:
                    failures_path.parent.mkdir(exist_ok=True)
                    with failures_path.open("a", encoding="utf-8") as handle:
                        handle.write(f"{ligand_pdbqt}\t{type(exc).__name__}: {exc}\n")
                if index == len(ligand_paths) or index % 100 == 0:
                    write_progress(index, f"Docked {index}/{len(ligand_paths)} ligands.")

    report_context = {
        **(report_context or {}),
        "input_ligands": str(ligand_dir),
        "receptor_pdbqt": str(receptor_pdbqt),
        "binding_site_json": str(binding_site_json),
        "output_dir": str(output_dir),
        "requested_max_ligands": max_ligands or len(ligand_paths),
        "prepared_ligands": len(ligand_paths),
        "docked_ligands": len(vina_runs),
        "interaction_analyses": len(interaction_jsons),
        "preset": "preprepared_pdbqt_no_filter",
        "run_plip": run_plip,
        "ligand_prep_options": {"skipped": True, "reason": "input was a prepared PDBQT directory"},
        "vina_options": vina_options.model_dump(mode="json"),
    }
    (output_dir / "report_context.json").write_text(json.dumps(report_context, indent=2) + "\n")
    if not vina_runs:
        write_progress(len(ligand_paths), "Docking failed: 0 successful Vina result JSON files.", "failed")
        raise RuntimeError(f"Docking failed for all {len(ligand_paths)} ligands. See {failures_path}")
    report_summary = summarize_vina_runs(
        vina_runs,
        output_dir / "report",
        interaction_jsons if interaction_jsons else None,
        report_context=report_context,
    )
    metadata_path = output_dir / "small_screen_summary.json"
    summary = SmallScreenSummary(
        input_ligands=str(ligand_dir),
        receptor_pdbqt=str(receptor_pdbqt),
        binding_site_json=str(binding_site_json),
        output_dir=str(output_dir),
        filter_summary_json="",
        ligand_prep_json="",
        docking_report=report_summary.report_markdown,
        results_csv=report_summary.results_csv,
        results_json=report_summary.results_json,
        metadata_path=str(metadata_path),
        requested_max_ligands=max_ligands or len(ligand_paths),
        prepared_ligands=len(ligand_paths),
        docked_ligands=len(vina_runs),
        interaction_analyses=len(interaction_jsons),
        best_ligand=report_summary.best_ligand,
        best_score=report_summary.best_score,
        vina_runs=[str(path.resolve()) for path in vina_runs],
        interaction_analysis_jsons=[str(path.resolve()) for path in interaction_jsons],
        created_at=datetime.now(timezone.utc),
        notes="Screen completed using an existing directory of Vina-ready PDBQT ligands; ligand preparation was skipped.",
    )
    metadata_path.write_text(json.dumps(summary.model_dump(mode="json"), indent=2) + "\n")
    write_progress(len(ligand_paths), f"Docking complete: {len(vina_runs)}/{len(ligand_paths)} ligands produced Vina result JSON files.", "completed")
    return summary


def _existing_ligand_prep_for_screen_input(ligands: Path) -> tuple[str, LigandPrepRecord] | None:
    ligands = ligands.resolve()
    candidates = [
        ligands.parent.parent / "vina-prep" / "ligand_prep.json",
        ligands.parent / "ligand_prep.json",
    ]
    for metadata_path in candidates:
        if not metadata_path.exists():
            continue
        try:
            record = LigandPrepRecord.model_validate_json(metadata_path.read_text())
        except Exception:
            continue
        if Path(record.input_sdf).resolve() != ligands:
            continue
        if not record.pdbqt_files:
            continue
        if not all(Path(path).exists() and Path(path).stat().st_size > 0 for path in record.pdbqt_files):
            continue
        filter_summary = ligands.parent / "ligand_filter_summary.json"
        return (str(filter_summary.resolve()) if filter_summary.exists() else "", record)
    return None


def _dock_one_ligand(
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    binding_site_json: Path,
    output_dir: Path,
    vina_options: VinaRunOptions,
    run_plip: bool,
) -> tuple[Path, Path | None]:
    run_dir = output_dir / "docking" / ligand_pdbqt.stem
    existing_run = run_dir / "vina_run.json"
    if _valid_existing_vina_run(existing_run, receptor_pdbqt, ligand_pdbqt, binding_site_json, vina_options):
        interaction_json = _existing_or_run_interaction(
            run_json=existing_run,
            receptor_pdbqt=receptor_pdbqt,
            output_dir=output_dir,
            ligand_stem=ligand_pdbqt.stem,
            run_plip=run_plip,
        )
        return existing_run, interaction_json

    run_record = run_vina(
        receptor_pdbqt=receptor_pdbqt,
        ligand_pdbqt=ligand_pdbqt,
        binding_site_json=binding_site_json,
        output_dir=run_dir,
        options=vina_options,
    )
    smiles = smiles_from_pdbqt(ligand_pdbqt)
    if smiles:
        register_compound(
            output_dir.parent,
            smiles,
            source_path=str(ligand_pdbqt),
            source_label=ligand_pdbqt.stem,
            increment_screen_count=True,
        )
    interaction_json = _existing_or_run_interaction(
        run_json=Path(run_record.metadata_path),
        receptor_pdbqt=receptor_pdbqt,
        output_dir=output_dir,
        ligand_stem=ligand_pdbqt.stem,
        run_plip=run_plip,
    )
    return Path(run_record.metadata_path), interaction_json


def _valid_existing_vina_run(
    run_json: Path,
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    binding_site_json: Path,
    options: VinaRunOptions,
) -> bool:
    if not run_json.exists():
        return False
    try:
        record = VinaRunRecord.model_validate(json.loads(run_json.read_text()))
    except Exception:
        return False
    if Path(record.receptor_pdbqt).resolve() != receptor_pdbqt.resolve():
        return False
    if Path(record.ligand_pdbqt).resolve() != ligand_pdbqt.resolve():
        return False
    if Path(record.binding_site_json).resolve() != binding_site_json.resolve():
        return False
    if record.options.exhaustiveness != options.exhaustiveness:
        return False
    if record.options.num_modes != options.num_modes:
        return False
    if record.options.cpu != options.cpu:
        return False
    if record.options.seed != options.seed:
        return False
    output = Path(record.output_pdbqt)
    return output.exists() and output.stat().st_size > 0 and record.best_score is not None


def _existing_or_run_interaction(
    run_json: Path,
    receptor_pdbqt: Path,
    output_dir: Path,
    ligand_stem: str,
    run_plip: bool,
) -> Path | None:
    if not run_plip:
        return None
    interaction_dir = output_dir / "interactions" / ligand_stem
    existing = interaction_dir / "interaction_analysis.json"
    if existing.exists() and existing.stat().st_size > 0:
        return existing
    record = VinaRunRecord.model_validate(json.loads(run_json.read_text()))
    interaction_record = run_plip_analysis(
        receptor_pdbqt=receptor_pdbqt,
        docked_ligand_pdbqt=Path(record.output_pdbqt),
        output_dir=interaction_dir,
    )
    return Path(interaction_record.metadata_path)


def _write_limited_sdf(input_sdf: Path, output_sdf: Path, max_ligands: int) -> Path:
    output_sdf.parent.mkdir(parents=True, exist_ok=True)
    supplier = Chem.SDMolSupplier(str(input_sdf), removeHs=False)
    writer = Chem.SDWriter(str(output_sdf))
    written = 0
    try:
        for mol in supplier:
            if mol is None:
                continue
            writer.write(mol)
            written += 1
            if written >= max_ligands:
                break
    finally:
        writer.close()
    if written == 0:
        raise ValueError("no ligands remained after filtering")
    return output_sdf
