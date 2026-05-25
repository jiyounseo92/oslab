from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import gemmi
from rdkit import Chem
from rdkit.Chem import rdMolAlign

from .binding_sites import _read_structure
from .docking import run_vina
from .schemas import RedockingValidationRecord, VinaRunOptions, VinaRunRecord


def redock_crystal_ligand(
    structure_path: Path,
    ligand: str,
    receptor_pdbqt: Path,
    binding_site_json: Path,
    output_dir: Path,
    chain: str | None = None,
    residue_number: int | None = None,
    options: VinaRunOptions | None = None,
) -> RedockingValidationRecord:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    reference_pdb = extract_ligand_pdb(structure_path, ligand, output_dir / "reference_ligand.pdb", chain, residue_number)
    reference_sdf = output_dir / "reference_ligand.sdf"
    reference_pdbqt = output_dir / "reference_ligand.pdbqt"
    commands = prepare_reference_ligand(reference_pdb, reference_sdf, reference_pdbqt)

    vina_record = run_vina(
        receptor_pdbqt=receptor_pdbqt,
        ligand_pdbqt=reference_pdbqt,
        binding_site_json=binding_site_json,
        output_dir=output_dir / "vina",
        options=options or VinaRunOptions(),
    )
    docked_sdf = output_dir / "docked_ligand.sdf"
    convert_cmd = ["obabel", "-ipdbqt", vina_record.output_pdbqt, "-osdf", "-O", str(docked_sdf)]
    subprocess.run(convert_cmd, check=True, capture_output=True, text=True)

    rmsd = calculate_heavy_atom_rmsd(reference_sdf, docked_sdf)
    metadata_path = output_dir / "redocking_validation.json"
    record = RedockingValidationRecord(
        structure_path=str(Path(structure_path).resolve()),
        ligand=ligand.strip().upper(),
        chain=chain,
        residue_number=residue_number,
        reference_ligand_pdb=str(reference_pdb),
        reference_ligand_sdf=str(reference_sdf),
        reference_ligand_pdbqt=str(reference_pdbqt),
        docked_ligand_sdf=str(docked_sdf),
        vina_run_json=vina_record.metadata_path,
        metadata_path=str(metadata_path),
        rmsd_heavy_atom=rmsd,
        status=_rmsd_status(rmsd),
        thresholds={"pass_max_angstrom": 2.0, "review_max_angstrom": 3.0},
        commands=[*commands, VinaRunRecord.model_validate(json.loads(Path(vina_record.metadata_path).read_text())).command, convert_cmd],
        created_at=datetime.now(timezone.utc),
        notes="Redocking validation compares the docked pose to the crystallographic ligand pose using RDKit heavy-atom best RMSD.",
    )
    metadata_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n")
    return record


def extract_ligand_pdb(
    structure_path: Path,
    ligand: str,
    output_pdb: Path,
    chain: str | None = None,
    residue_number: int | None = None,
) -> Path:
    structure_path = structure_path.resolve()
    output_pdb = output_pdb.resolve()
    output_pdb.parent.mkdir(parents=True, exist_ok=True)
    structure = _read_structure(structure_path)
    ligand = ligand.strip().upper()
    selected: list[tuple[gemmi.Chain, gemmi.Residue]] = []
    for model in structure:
        for gemmi_chain in model:
            if chain and gemmi_chain.name != chain:
                continue
            for residue in gemmi_chain:
                if residue.name.strip().upper() != ligand:
                    continue
                if residue_number is not None and residue.seqid.num != residue_number:
                    continue
                selected.append((gemmi_chain, residue))
    if not selected:
        selector = ligand
        if chain:
            selector = f"{chain}:{selector}"
        if residue_number is not None:
            selector = f"{selector}{residue_number}"
        raise ValueError(f"ligand residue not found: {selector}")
    if len(selected) > 1:
        choices = ", ".join(f"{chain_obj.name}:{residue.name}{residue.seqid.num}" for chain_obj, residue in selected)
        raise ValueError(f"ligand selector matched multiple residues; specify --chain/--residue-number. Matches: {choices}")

    chain_obj, residue = selected[0]
    lines: list[str] = []
    serial = 1
    for atom in residue:
        if atom.is_hydrogen():
            continue
        lines.append(_pdb_hetatm_line(serial, atom, residue.name.strip().upper(), "Z", 1))
        serial += 1
    if serial == 1:
        raise ValueError(f"ligand residue {chain_obj.name}:{residue.name}{residue.seqid.num} has no heavy atoms")
    lines.append("END")
    output_pdb.write_text("\n".join(lines) + "\n")
    return output_pdb


def prepare_reference_ligand(reference_pdb: Path, reference_sdf: Path, reference_pdbqt: Path) -> list[list[str]]:
    obabel = _resolve_env_tool("obabel")
    obabel_cmd = [obabel, "-ipdb", str(reference_pdb), "-osdf", "-O", str(reference_sdf), "-h"]
    subprocess.run(obabel_cmd, check=True, capture_output=True, text=True)
    meeko_cli = shutil.which("mk_prepare_ligand.py")
    if meeko_cli:
        meeko_cmd = [
            meeko_cli,
            "-i",
            str(reference_sdf),
            "-o",
            str(reference_pdbqt),
            "--charge_model",
            "gasteiger",
        ]
        subprocess.run(meeko_cmd, check=True, capture_output=True, text=True)
    else:
        meeko_cmd = ["meeko-python-api", "-i", str(reference_sdf), "-o", str(reference_pdbqt), "--charge_model", "gasteiger"]
        _prepare_reference_ligand_with_meeko_api(reference_sdf, reference_pdbqt)
    return [obabel_cmd, meeko_cmd]


def _resolve_env_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidate = Path(sys.executable).resolve().parent / name
    if candidate.exists():
        return str(candidate)
    return name


def _prepare_reference_ligand_with_meeko_api(reference_sdf: Path, reference_pdbqt: Path) -> None:
    from meeko import MoleculePreparation, PDBQTWriterLegacy

    mol = _read_first_sdf_molecule(reference_sdf)
    preparation = MoleculePreparation(charge_model="gasteiger")
    setups = preparation.prepare(mol)
    if not setups:
        raise RuntimeError("Meeko did not produce a molecule setup")
    pdbqt, ok, message = PDBQTWriterLegacy.write_string(setups[0])
    if not ok:
        raise RuntimeError(message or "Meeko PDBQT writer failed")
    reference_pdbqt.write_text(pdbqt)


def calculate_heavy_atom_rmsd(reference_sdf: Path, docked_sdf: Path) -> float:
    reference = _read_first_sdf_molecule(reference_sdf)
    docked = _read_first_sdf_molecule(docked_sdf)
    reference_heavy = Chem.RemoveHs(reference)
    docked_heavy = Chem.RemoveHs(docked)
    return float(rdMolAlign.GetBestRMS(reference_heavy, docked_heavy))


def _read_first_sdf_molecule(path: Path) -> Chem.Mol:
    supplier = Chem.SDMolSupplier(str(path), removeHs=False)
    mol = supplier[0] if supplier and len(supplier) else None
    if mol is None:
        raise ValueError(f"could not read molecule from SDF: {path}")
    return mol


def _rmsd_status(rmsd: float | None) -> str:
    if rmsd is None:
        return "error"
    if rmsd <= 2.0:
        return "pass"
    if rmsd <= 3.0:
        return "review"
    return "fail"


def _pdb_hetatm_line(serial: int, atom: gemmi.Atom, residue_name: str, chain: str, residue_number: int) -> str:
    element = atom.element.name
    return (
        f"HETATM{serial:5d} {atom.name[:4]:<4} {residue_name[:3]:>3} {chain[:1]}"
        f"{residue_number:4d}    {atom.pos.x:8.3f}{atom.pos.y:8.3f}{atom.pos.z:8.3f}"
        f"  1.00  0.00          {element:>2}"
    )
