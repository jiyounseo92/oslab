from __future__ import annotations

import json
import shutil
import subprocess
import csv
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rdkit import Chem
from rdkit.Chem import AllChem

from .jobs import DEFAULT_RDKIT_SEED, set_rdkit_seed
from .schemas import LigandPrepOptions, LigandPrepRecord
from .structures import sha256_file


def prepare_ligands_for_vina(
    input_sdf: Path,
    output_dir: Path,
    options: LigandPrepOptions | None = None,
) -> LigandPrepRecord:
    options = options or LigandPrepOptions()
    input_sdf = input_sdf.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    prepared_sdf = output_dir / "ligands_prepared.sdf"
    pdbqt_dir = output_dir / "pdbqt"
    metadata_path = output_dir / "ligand_prep.json"
    pdbqt_dir.mkdir(exist_ok=True)
    existing_record = _existing_ligand_prep_record(metadata_path, input_sdf, options)
    if existing_record:
        return existing_record

    if options.backend == "rdkit":
        commands = _prepare_with_rdkit(input_sdf, prepared_sdf, pdbqt_dir, options)
    else:
        commands = _prepare_with_openbabel(input_sdf, prepared_sdf, pdbqt_dir, options)

    repair_summary: dict[str, Any] | None = None
    if options.backend == "rdkit":
        repair_summary = repair_unique_pdbqt_outputs(
            output_dir,
            workers=options.workers,
            charge_model=options.charge_model,
        )
        pdbqt_files = sorted(str(Path(path).resolve()) for path in repair_summary["pdbqt_files"])
    else:
        pdbqt_files = sorted(str(path.resolve()) for path in pdbqt_dir.glob("*.pdbqt"))
    metadata_summary = _write_ligand_metadata_sidecars(prepared_sdf, [Path(path) for path in pdbqt_files], output_dir)
    record = LigandPrepRecord(
        input_sdf=str(input_sdf),
        prepared_sdf=str(prepared_sdf),
        pdbqt_dir=str(pdbqt_dir),
        metadata_path=str(metadata_path),
        input_sha256=sha256_file(input_sdf),
        prepared_sdf_sha256=sha256_file(prepared_sdf),
        pdbqt_files=pdbqt_files,
        pdbqt_sha256={path: sha256_file(Path(path)) for path in pdbqt_files},
        prepared_count=len(pdbqt_files),
        options=options,
        commands=commands,
        created_at=datetime.now(timezone.utc),
        notes=_ligand_prep_notes(repair_summary, metadata_summary),
    )
    metadata_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n")
    return record


def repair_unique_pdbqt_outputs(output_dir: Path, workers: int = 1, charge_model: str = "gasteiger") -> dict[str, Any]:
    output_dir = output_dir.resolve()
    prepared_dir = output_dir / "prepared-mols"
    pdbqt_dir = output_dir / "pdbqt"
    repair_dir = output_dir / "repair-unique-sdf"
    progress_json = output_dir / "pdbqt_repair_progress.json"
    failures_csv = output_dir / "pdbqt_repair_failures.csv"
    repair_dir.mkdir(parents=True, exist_ok=True)
    pdbqt_dir.mkdir(parents=True, exist_ok=True)

    inputs = sorted(prepared_dir.glob("*.sdf"))
    ligand_rows = _inspect_prepared_ligands(inputs, pdbqt_dir)
    repair_rows = [row for row in ligand_rows if row["needs_repair"]]
    selected_outputs = [
        Path(str(row["selected_pdbqt"]))
        for row in ligand_rows
        if not row["needs_repair"] and row.get("selected_pdbqt")
    ]
    progress: dict[str, Any] = {
        "phase": "repairing",
        "total_prepared_sdf": len(inputs),
        "total": len(repair_rows),
        "unique_existing": len(inputs) - len(repair_rows),
        "completed": 0,
        "repaired": 0,
        "skipped_existing": 0,
        "failed": 0,
        "pdbqt_dir": str(pdbqt_dir),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(progress_json, progress)

    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max(1, int(workers or 1))) as executor:
        futures = [
            executor.submit(_repair_one_pdbqt_output, Path(str(row["sdf"])), repair_dir, pdbqt_dir, charge_model)
            for row in repair_rows
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            row = future.result()
            progress["completed"] = index
            if row["status"] == "repaired":
                progress["repaired"] = int(progress["repaired"]) + 1
                selected_outputs.append(Path(row["pdbqt"]))
            elif row["status"] == "skipped_existing":
                progress["skipped_existing"] = int(progress["skipped_existing"]) + 1
                selected_outputs.append(Path(row["pdbqt"]))
            else:
                progress["failed"] = int(progress["failed"]) + 1
                failures.append(row)
            if index % 25 == 0 or index == len(futures):
                progress["updated_at"] = datetime.now(timezone.utc).isoformat()
                progress["pdbqt_count"] = len(list(pdbqt_dir.glob("*.pdbqt")))
                _write_json(progress_json, progress)

    pdbqt_files = sorted({str(path.resolve()) for path in selected_outputs if path.exists() and path.stat().st_size > 0})
    progress["phase"] = "completed"
    progress["finished_at"] = datetime.now(timezone.utc).isoformat()
    progress["selected_pdbqt_count"] = len(pdbqt_files)
    progress["pdbqt_count"] = len(list(pdbqt_dir.glob("*.pdbqt")))
    progress["failures_csv"] = str(failures_csv.resolve())
    _write_json(progress_json, progress)
    _write_failures(failures_csv, failures)
    return {
        **progress,
        "pdbqt_files": pdbqt_files,
        "progress_json": str(progress_json.resolve()),
        "failures_csv": str(failures_csv.resolve()),
    }


def _prepare_with_openbabel(input_sdf: Path, prepared_sdf: Path, pdbqt_dir: Path, options: LigandPrepOptions) -> list[list[str]]:
    obabel_cmd = ["obabel", str(input_sdf), "-O", str(prepared_sdf)]
    if options.generate_3d:
        obabel_cmd.append("--gen3d")
    obabel_cmd.extend(["-p", str(options.ph)])

    meeko_cmd = [
        "mk_prepare_ligand.py",
        "-i",
        str(prepared_sdf),
        "--multimol_outdir",
        str(pdbqt_dir),
        "--charge_model",
        options.charge_model,
    ]

    _run_command(obabel_cmd, timeout=None)
    _run_command(meeko_cmd, timeout=None)
    return [obabel_cmd, meeko_cmd]


def _existing_ligand_prep_record(metadata_path: Path, input_sdf: Path, options: LigandPrepOptions) -> LigandPrepRecord | None:
    if not metadata_path.exists():
        return None
    try:
        record = LigandPrepRecord.model_validate_json(metadata_path.read_text())
    except Exception:
        return None
    if Path(record.input_sdf).resolve() != input_sdf.resolve():
        return None
    if record.input_sha256 != sha256_file(input_sdf):
        return None
    if record.options.model_dump(mode="json") != options.model_dump(mode="json"):
        return None
    if not record.pdbqt_files:
        return None
    if not all(Path(path).exists() and Path(path).stat().st_size > 0 for path in record.pdbqt_files):
        return None
    prepared_mol_dir = metadata_path.parent / "prepared-mols"
    prepared_mol_count = len(list(prepared_mol_dir.glob("*.sdf"))) if prepared_mol_dir.exists() else 0
    if prepared_mol_count and len(record.pdbqt_files) < prepared_mol_count:
        failure_count = _count_failure_rows(metadata_path.parent / "pdbqt_repair_failures.csv")
        if len(record.pdbqt_files) + failure_count < prepared_mol_count:
            return None
    return record


def _ligand_prep_notes(repair_summary: dict[str, Any] | None, metadata_summary: dict[str, Any] | None = None) -> str:
    base = "Ligands prepared for AutoDock Vina with per-ligand RDKit/Open Babel geometry handling and Meeko PDBQT conversion."
    if metadata_summary:
        base = (
            f"{base} Ligand metadata sidecars were written for "
            f"{metadata_summary.get('metadata_count', 0)} ligand(s), and "
            f"{metadata_summary.get('annotated_pdbqt_count', 0)} PDBQT file(s) were annotated with REMARK SMILES."
        )
    if repair_summary:
        base = (
            f"{base} PDBQT outputs were checked for duplicate-name collisions; "
        f"{repair_summary.get('repaired', 0)} repaired, {repair_summary.get('skipped_existing', 0)} already correct, "
        f"{repair_summary.get('failed', 0)} skipped after failed repair, "
        f"{repair_summary.get('selected_pdbqt_count', 0)} selected for docking."
        )
    return base


def _write_ligand_metadata_sidecars(prepared_sdf: Path, pdbqt_files: list[Path], output_dir: Path) -> dict[str, Any]:
    rows = _ligand_metadata_rows(prepared_sdf, pdbqt_files)
    if not rows:
        return {"metadata_count": 0, "annotated_pdbqt_count": 0}
    json_path = output_dir / "ligand_metadata.json"
    csv_path = output_dir / "ligand_metadata.csv"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prepared_sdf": str(prepared_sdf),
        "ligands": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["name", "original_name", "safe_name", "pdbqt_stem", "pdbqt", "smiles"],
        )
        writer.writeheader()
        writer.writerows(rows)
    annotated = 0
    for row in rows:
        pdbqt = Path(str(row.get("pdbqt") or ""))
        smiles = str(row.get("smiles") or "")
        if pdbqt.exists() and smiles and _ensure_pdbqt_smiles_remark(pdbqt, smiles):
            annotated += 1
    return {
        "metadata_count": len(rows),
        "annotated_pdbqt_count": annotated,
        "metadata_json": str(json_path),
        "metadata_csv": str(csv_path),
    }


def _ligand_metadata_rows(prepared_sdf: Path, pdbqt_files: list[Path]) -> list[dict[str, str]]:
    if not prepared_sdf.exists():
        return []
    pdbqt_by_stem = {path.stem: path for path in pdbqt_files if path.exists()}
    rows: list[dict[str, str]] = []
    supplier = Chem.SDMolSupplier(str(prepared_sdf), removeHs=False)
    for index, mol in enumerate(supplier, start=1):
        if mol is None:
            continue
        name = mol.GetProp("_Name") if mol.HasProp("_Name") else f"ligand_{index}"
        original = mol.GetProp("original_name") if mol.HasProp("original_name") else name
        safe_name = _safe_name(name)
        pdbqt = pdbqt_by_stem.get(safe_name) or pdbqt_by_stem.get(_safe_name(original))
        smiles = _mol_to_smiles(mol)
        rows.append(
            {
                "name": name,
                "original_name": original,
                "safe_name": safe_name,
                "pdbqt_stem": pdbqt.stem if pdbqt else safe_name,
                "pdbqt": str(pdbqt.resolve()) if pdbqt else "",
                "smiles": smiles,
            }
        )
    return rows


def _mol_to_smiles(mol: Chem.Mol) -> str:
    try:
        copy = Chem.Mol(mol)
        return Chem.MolToSmiles(Chem.RemoveHs(copy), isomericSmiles=True)
    except Exception:
        return ""


def _ensure_pdbqt_smiles_remark(pdbqt: Path, smiles: str) -> bool:
    if not smiles:
        return False
    try:
        text = pdbqt.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for line in text.splitlines():
        if line.startswith("REMARK SMILES ") and not line.startswith("REMARK SMILES IDX"):
            return False
    pdbqt.write_text(f"REMARK SMILES {smiles}\n{text}", encoding="utf-8")
    return True


def _inspect_prepared_ligands(inputs: list[Path], pdbqt_dir: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    name_counts: dict[str, int] = {}
    for src in inputs:
        original = _read_molecule_name(src)
        name_counts[original] = name_counts.get(original, 0) + 1
        rows.append({"sdf": str(src), "original_name": original, "unique_name": _safe_name(src.stem)})
    for row in rows:
        original_pdbqt = pdbqt_dir / f"{_safe_name(str(row['original_name']))}.pdbqt"
        unique_pdbqt = pdbqt_dir / f"{row['unique_name']}.pdbqt"
        duplicate_name = name_counts[str(row["original_name"])] > 1
        if duplicate_name or not original_pdbqt.exists():
            row["needs_repair"] = True
            row["selected_pdbqt"] = str(unique_pdbqt) if unique_pdbqt.exists() and unique_pdbqt.stat().st_size > 0 else ""
        else:
            row["needs_repair"] = False
            row["selected_pdbqt"] = str(original_pdbqt)
    return rows


def _read_molecule_name(src: Path) -> str:
    supplier = Chem.SDMolSupplier(str(src), removeHs=False)
    mol = next(iter(supplier), None)
    if mol is None:
        return src.stem
    return mol.GetProp("_Name") if mol.HasProp("_Name") else src.stem


def _repair_one_pdbqt_output(src: Path, repair_dir: Path, pdbqt_dir: Path, charge_model: str) -> dict[str, str]:
    unique = _safe_name(src.stem)
    expected = pdbqt_dir / f"{unique}.pdbqt"
    if expected.exists() and expected.stat().st_size > 0:
        return {"status": "skipped_existing", "name": unique, "pdbqt": str(expected.resolve()), "error": ""}
    try:
        from meeko import MoleculePreparation, PDBQTWriterLegacy

        supplier = Chem.SDMolSupplier(str(src), removeHs=False)
        mol = next(iter(supplier), None)
        if mol is None:
            raise ValueError("RDKit could not read prepared SDF")
        if mol.HasProp("_Name"):
            mol.SetProp("original_name", mol.GetProp("_Name"))
        mol.SetProp("_Name", unique)
        dst = repair_dir / src.name
        writer = Chem.SDWriter(str(dst))
        try:
            writer.write(mol)
        finally:
            writer.close()
        preparation = MoleculePreparation(charge_model=charge_model)
        setups = preparation.prepare(mol)
        if not setups:
            raise RuntimeError("Meeko did not produce a molecule setup")
        pdbqt, ok, message = PDBQTWriterLegacy.write_string(setups[0])
        if not ok:
            raise RuntimeError(message or "Meeko PDBQT writer failed")
        expected.write_text(pdbqt)
        if not expected.exists() or expected.stat().st_size == 0:
            raise RuntimeError(f"expected PDBQT not created: {expected}")
        return {"status": "repaired", "name": unique, "pdbqt": str(expected.resolve()), "error": ""}
    except Exception as exc:
        return {"status": "failed", "name": unique, "pdbqt": "", "error": str(exc).replace("\n", " ")}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def _write_failures(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "status", "error"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "name": row.get("name", ""),
                    "status": row.get("status", ""),
                    "error": row.get("error", ""),
                }
            )


def _count_failure_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as handle:
            return sum(1 for row in csv.DictReader(handle) if row.get("status") == "failed")
    except Exception:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return max(0, len(lines) - 1)


def _prepare_with_rdkit(input_sdf: Path, prepared_sdf: Path, pdbqt_dir: Path, options: LigandPrepOptions) -> list[list[str]]:
    prepared_dir = prepared_sdf.parent / "prepared-mols"
    prepared_dir.mkdir(exist_ok=True)
    failures_csv = prepared_sdf.parent / "ligand_prep_failures.csv"

    supplier = Chem.SDMolSupplier(str(input_sdf), removeHs=False)
    tasks: list[tuple[str, str, str, str, str, bool, str, int]] = []
    for index, mol in enumerate(supplier, start=1):
        if mol is None:
            continue
        name = _safe_name(mol.GetProp("_Name") if mol.HasProp("_Name") else f"ligand_{index}")
        molblock = Chem.MolToMolBlock(mol)
        tasks.append(
            (
                molblock,
                name,
                str(prepared_dir / f"{index:06d}_{name}.sdf"),
                str(pdbqt_dir),
                options.charge_model,
                options.generate_3d,
                str(options.ph),
                options.timeout_seconds,
            )
        )

    results: list[dict[str, str]] = []
    workers = max(1, int(options.workers or 1))
    if workers == 1:
        results = [_prepare_one_ligand(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_prepare_one_ligand, task) for task in tasks]
            for future in as_completed(futures):
                results.append(future.result())

    successful_sdfs = sorted(Path(result["sdf"]) for result in results if result["status"] == "ok")
    writer = Chem.SDWriter(str(prepared_sdf))
    try:
        for sdf_path in successful_sdfs:
            for mol in Chem.SDMolSupplier(str(sdf_path), removeHs=False):
                if mol is not None:
                    writer.write(mol)
    finally:
        writer.close()

    failures = [result for result in results if result["status"] != "ok"]
    failures_csv.write_text("ligand,status,error\n" + "".join(f"{row['name']},{row['status']},{row['error']}\n" for row in failures))
    if not successful_sdfs:
        raise ValueError(f"no ligands prepared successfully; failures: {failures_csv}")
    return [
        ["rdkit-embed-mmff", str(input_sdf), str(prepared_sdf), f"workers={workers}", f"generate_3d={options.generate_3d}"],
        ["mk_prepare_ligand.py", "--per-ligand", str(pdbqt_dir), "--charge_model", options.charge_model],
    ]


def _prepare_one_ligand(task: tuple[str, str, str, str, str, bool, str, int]) -> dict[str, str]:
    molblock, name, sdf_path, pdbqt_dir, charge_model, generate_3d, ph, timeout = task
    try:
        set_rdkit_seed()
        mol = Chem.MolFromMolBlock(molblock, removeHs=False, sanitize=True)
        if mol is None:
            raise ValueError("RDKit could not parse molecule")
        if generate_3d:
            mol = Chem.AddHs(mol)
            params = AllChem.ETKDGv3()
            params.randomSeed = DEFAULT_RDKIT_SEED
            status = AllChem.EmbedMolecule(mol, params)
            if status != 0:
                status = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=DEFAULT_RDKIT_SEED)
            if status != 0:
                raise ValueError("RDKit conformer embedding failed")
            try:
                AllChem.MMFFOptimizeMolecule(mol, maxIters=250)
            except Exception:
                AllChem.UFFOptimizeMolecule(mol, maxIters=250)
        sdf = Path(sdf_path)
        unique_name = _safe_name(sdf.stem)
        if mol.HasProp("_Name"):
            mol.SetProp("original_name", mol.GetProp("_Name"))
        mol.SetProp("_Name", unique_name)
        writer = Chem.SDWriter(str(sdf))
        try:
            writer.write(mol)
        finally:
            writer.close()
        _write_pdbqt_with_meeko(sdf, Path(pdbqt_dir), charge_model, timeout)
        expected_pdbqt = Path(pdbqt_dir) / f"{unique_name}.pdbqt"
        if not expected_pdbqt.exists() or expected_pdbqt.stat().st_size == 0:
            raise RuntimeError(f"Meeko did not create expected PDBQT output: {expected_pdbqt}")
        return {"name": name, "sdf": str(sdf), "status": "ok", "error": ""}
    except Exception as exc:
        return {"name": name, "sdf": sdf_path, "status": "failed", "error": str(exc).replace("\n", " ")}


def _write_pdbqt_with_meeko(sdf: Path, pdbqt_dir: Path, charge_model: str, timeout: int) -> None:
    cli = shutil.which("mk_prepare_ligand.py")
    if cli or getattr(_run_command, "__module__", __name__) != __name__:
        cmd = [
            cli or "mk_prepare_ligand.py",
            "-i",
            str(sdf),
            "--multimol_outdir",
            str(pdbqt_dir),
            "--charge_model",
            charge_model,
        ]
        _run_command(cmd, timeout=timeout)
        return

    from meeko import MoleculePreparation, PDBQTWriterLegacy

    supplier = Chem.SDMolSupplier(str(sdf), removeHs=False)
    mol = next(iter(supplier), None)
    if mol is None:
        raise ValueError("RDKit could not read prepared SDF for Meeko conversion")
    name = _safe_name(mol.GetProp("_Name") if mol.HasProp("_Name") else sdf.stem)
    preparation = MoleculePreparation(charge_model=charge_model)
    setups = preparation.prepare(mol)
    if not setups:
        raise RuntimeError("Meeko did not produce a molecule setup")
    pdbqt, ok, message = PDBQTWriterLegacy.write_string(setups[0])
    if not ok:
        raise RuntimeError(message or "Meeko PDBQT writer failed")
    output = pdbqt_dir / f"{name}.pdbqt"
    output.write_text(pdbqt)


def _run_command(command: list[str], timeout: int | None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(f"{' '.join(command)} failed: {detail}") from exc


def _safe_name(name: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in name.strip())
    return safe[:80] or "ligand"
