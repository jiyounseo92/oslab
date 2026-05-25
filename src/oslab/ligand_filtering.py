from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem.MolStandardize import rdMolStandardize

from .presets.registry import load_ligand_filter_preset
from .schemas import LigandFilterPreset, LigandFilterSummary


CSV_FIELDS = [
    "index",
    "name",
    "smiles",
    "canonical_smiles",
    "molecular_weight",
    "clogp",
    "hbond_donors",
    "hbond_acceptors",
    "tpsa",
    "rotatable_bonds",
    "formal_charge",
    "included",
    "reasons",
    "flags",
]


STRUCTURAL_ALERTS = {
    "nitro": "[N+](=O)[O-]",
    "aldehyde": "[CX3H1](=O)[#6]",
    "acid_chloride": "C(=O)Cl",
    "epoxide": "C1OC1",
    "isocyanate": "N=C=O",
}


def load_ligands(input_path: Path) -> list[Chem.Mol]:
    suffix = input_path.suffix.lower()
    if suffix in {".sdf", ".sd"}:
        supplier = Chem.SDMolSupplier(str(input_path), removeHs=False)
        return [mol for mol in supplier if mol is not None]
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with input_path.open(newline="") as handle:
            sample = handle.readline()
            handle.seek(0)
            if _looks_like_table_header(sample, delimiter):
                reader = csv.DictReader(handle, delimiter=delimiter)
                return _molecules_from_table_rows(reader)
            return _molecules_from_smiles_lines(handle, delimiter="\t" if suffix == ".tsv" else None)
    if suffix in {".smi", ".smiles", ".txt"}:
        delimiter = "\t" if suffix == ".tsv" else None
        with input_path.open() as handle:
            return _molecules_from_smiles_lines(handle, delimiter=delimiter)
    raise ValueError("ligand input must be SDF, SMILES, TXT, CSV, or TSV")


def _molecules_from_smiles_lines(handle: Iterable[str], delimiter: str | None = None) -> list[Chem.Mol]:
    molecules: list[Chem.Mol] = []
    for line_number, line in enumerate(handle, start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(delimiter) if delimiter else line.replace(",", " ").split()
        if not parts or _is_smiles_header(parts):
            continue
        smiles = parts[0]
        name = parts[1] if len(parts) > 1 else f"mol_{line_number}"
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        mol.SetProp("_Name", name)
        molecules.append(mol)
    return molecules


def _molecules_from_table_rows(rows: Iterable[dict[str, str]]) -> list[Chem.Mol]:
    molecules: list[Chem.Mol] = []
    for line_number, row in enumerate(rows, start=1):
        normalized = {str(key or "").strip().lower(): str(value or "").strip() for key, value in row.items()}
        smiles = normalized.get("smiles") or normalized.get("canonical_smiles") or normalized.get("canonicalsmiles")
        if not smiles:
            continue
        name = normalized.get("name") or normalized.get("zinc_id") or normalized.get("id") or normalized.get("compound_id") or f"mol_{line_number}"
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        mol.SetProp("_Name", name)
        molecules.append(mol)
    return molecules


def _looks_like_table_header(line: str, delimiter: str) -> bool:
    fields = [field.strip().lower() for field in line.strip().split(delimiter)]
    return bool({"smiles", "canonical_smiles", "canonicalsmiles"} & set(fields))


def _is_smiles_header(parts: list[str]) -> bool:
    normalized = [part.strip().lower() for part in parts]
    if not normalized:
        return False
    if normalized[0] in {"smiles", "canonical_smiles", "canonicalsmiles"}:
        return True
    return normalized[:2] in (["smiles", "zinc_id"], ["smiles", "name"], ["smiles", "id"])


def filter_ligands(input_path: Path, output_dir: Path, preset_key: str = "drug_like") -> LigandFilterSummary:
    preset = load_ligand_filter_preset(preset_key)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    included_sdf = output_dir / "included.sdf"
    included_csv = output_dir / "included.csv"
    excluded_csv = output_dir / "excluded.csv"
    summary_json = output_dir / "ligand_filter_summary.json"

    molecules = load_ligands(input_path)
    seen: set[str] = set()
    included_rows: list[dict[str, str]] = []
    excluded_rows: list[dict[str, str]] = []
    writer = Chem.SDWriter(str(included_sdf))

    try:
        for index, mol in enumerate(molecules, start=1):
            processed = _standardize_molecule(mol, preset)
            row, reasons, flags = _evaluate_molecule(processed, preset, index, seen)
            row["included"] = "true" if not reasons else "false"
            row["reasons"] = "; ".join(reasons)
            row["flags"] = "; ".join(flags)
            if reasons:
                excluded_rows.append(row)
            else:
                for key, value in row.items():
                    processed.SetProp(key, str(value))
                writer.write(processed)
                included_rows.append(row)
    finally:
        writer.close()

    _write_csv(included_csv, included_rows)
    _write_csv(excluded_csv, excluded_rows)

    summary = LigandFilterSummary(
        input_path=str(input_path.resolve()),
        output_dir=str(output_dir),
        preset_key=preset.key,
        preset=preset,
        total_molecules=len(molecules),
        included_count=len(included_rows),
        excluded_count=len(excluded_rows),
        flagged_count=sum(1 for row in [*included_rows, *excluded_rows] if row["flags"]),
        included_sdf=str(included_sdf),
        included_csv=str(included_csv),
        excluded_csv=str(excluded_csv),
        summary_json=str(summary_json),
        created_at=datetime.now(timezone.utc),
        notes="Ligand filtering used RDKit descriptors and visible preset thresholds.",
    )
    summary_json.write_text(json.dumps(summary.model_dump(mode="json"), indent=2) + "\n")
    return summary


def _standardize_molecule(mol: Chem.Mol, preset: LigandFilterPreset) -> Chem.Mol:
    copy = Chem.Mol(mol)
    if preset.salts_and_mixtures == "remove":
        copy = rdMolStandardize.FragmentParent(copy)
    Chem.SanitizeMol(copy)
    return copy


def _evaluate_molecule(
    mol: Chem.Mol,
    preset: LigandFilterPreset,
    index: int,
    seen: set[str],
) -> tuple[dict[str, str], list[str], list[str]]:
    canonical = Chem.MolToSmiles(mol, canonical=True)
    name = mol.GetProp("_Name") if mol.HasProp("_Name") else f"mol_{index}"
    molecular_weight = float(Descriptors.MolWt(mol))
    clogp = float(Crippen.MolLogP(mol))
    donors = int(Lipinski.NumHDonors(mol))
    acceptors = int(Lipinski.NumHAcceptors(mol))
    tpsa = float(rdMolDescriptors.CalcTPSA(mol))
    rotatable = int(Lipinski.NumRotatableBonds(mol))
    charge = int(sum(atom.GetFormalCharge() for atom in mol.GetAtoms()))
    flags = _structural_alerts(mol)
    reasons: list[str] = []

    _check_range(reasons, "molecular_weight", molecular_weight, preset.molecular_weight.min, preset.molecular_weight.max)
    _check_range(reasons, "clogp", clogp, preset.clogp.min, preset.clogp.max)
    _check_max(reasons, "hbond_donors", donors, preset.hbond_donors_max)
    _check_max(reasons, "hbond_acceptors", acceptors, preset.hbond_acceptors_max)
    _check_max(reasons, "tpsa", tpsa, preset.tpsa_max)
    _check_max(reasons, "rotatable_bonds", rotatable, preset.rotatable_bonds_max)
    _check_range(reasons, "formal_charge", charge, preset.formal_charge.min, preset.formal_charge.max)

    if preset.deduplicate_by != "none":
        if canonical in seen:
            reasons.append("duplicate canonical_smiles")
        seen.add(canonical)
    if flags and (preset.structural_alert_policy == "exclude" or preset.strict_mode):
        reasons.append("structural alerts present")

    row = {
        "index": str(index),
        "name": name,
        "smiles": Chem.MolToSmiles(mol, canonical=False),
        "canonical_smiles": canonical,
        "molecular_weight": f"{molecular_weight:.3f}",
        "clogp": f"{clogp:.3f}",
        "hbond_donors": str(donors),
        "hbond_acceptors": str(acceptors),
        "tpsa": f"{tpsa:.3f}",
        "rotatable_bonds": str(rotatable),
        "formal_charge": str(charge),
    }
    return row, reasons, flags


def _structural_alerts(mol: Chem.Mol) -> list[str]:
    flags: list[str] = []
    for name, smarts in STRUCTURAL_ALERTS.items():
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is not None and mol.HasSubstructMatch(pattern):
            flags.append(name)
    return flags


def _check_range(reasons: list[str], name: str, value: float, minimum: float | None, maximum: float | None) -> None:
    if minimum is not None and value < minimum:
        reasons.append(f"{name} below minimum {minimum:g}")
    if maximum is not None and value > maximum:
        reasons.append(f"{name} above maximum {maximum:g}")


def _check_max(reasons: list[str], name: str, value: float, maximum: float) -> None:
    if value > maximum:
        reasons.append(f"{name} above maximum {maximum:g}")


def _write_csv(path: Path, rows: Iterable[dict[str, str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})
