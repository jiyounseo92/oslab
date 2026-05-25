from __future__ import annotations

import csv
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from .schemas import InteractionAnalysisRecord


def make_complex_pdb_from_pdbqt(receptor_pdbqt: Path, ligand_pdbqt: Path, complex_pdb: Path) -> Path:
    receptor_pdbqt = receptor_pdbqt.resolve()
    ligand_pdbqt = ligand_pdbqt.resolve()
    complex_pdb = complex_pdb.resolve()
    complex_pdb.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for line in receptor_pdbqt.read_text().splitlines():
        if line.startswith(("ATOM  ", "HETATM")):
            lines.append(_pdbqt_atom_to_pdb(line, hetatm=False))

    for index, line in enumerate(_first_model_atom_lines(ligand_pdbqt), start=1):
        lines.append(_pdbqt_atom_to_pdb(line, hetatm=True, serial=index, residue_name="LIG", chain="Z", residue_number=1))

    lines.append("END")
    complex_pdb.write_text("\n".join(lines) + "\n")
    return complex_pdb


def run_plip_analysis(receptor_pdbqt: Path, docked_ligand_pdbqt: Path, output_dir: Path) -> InteractionAnalysisRecord:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    complex_pdb = output_dir / "complex.pdb"
    metadata_path = output_dir / "interaction_analysis.json"
    make_complex_pdb_from_pdbqt(receptor_pdbqt, docked_ligand_pdbqt, complex_pdb)

    plip_bin = shutil.which("plip") or shutil.which("plipcmd") or "plip"
    command = [plip_bin, "-f", str(complex_pdb), "-o", str(output_dir), "-x", "-t", "--name", "plip_report"]
    completed = subprocess.run(command, capture_output=True, text=True)
    xml = output_dir / "plip_report.xml"
    txt = output_dir / "plip_report.txt"
    interaction_csv = None
    interaction_json = None
    if xml.exists():
        interaction_csv = output_dir / "interaction_summary.csv"
        interaction_json = output_dir / "interaction_summary.json"
        summarize_plip_xml(xml, interaction_csv, interaction_json)
    record = InteractionAnalysisRecord(
        receptor_pdbqt=str(receptor_pdbqt.resolve()),
        docked_ligand_pdbqt=str(docked_ligand_pdbqt.resolve()),
        complex_pdb=str(complex_pdb),
        output_dir=str(output_dir),
        metadata_path=str(metadata_path),
        plip_xml=str(xml) if xml.exists() else None,
        plip_txt=str(txt) if txt.exists() else None,
        interaction_csv=str(interaction_csv) if interaction_csv else None,
        interaction_json=str(interaction_json) if interaction_json else None,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        created_at=datetime.now(timezone.utc),
        notes="PLIP interaction analysis. Nonzero returncode means PLIP could not produce a complete interaction report.",
    )
    metadata_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n")
    return record


def summarize_plip_xml(xml_path: Path, csv_path: Path, json_path: Path) -> list[dict[str, str]]:
    rows = plip_interaction_rows(xml_path)
    fieldnames = [
        "ligand",
        "ligand_type",
        "interaction_type",
        "residue_chain",
        "residue_number",
        "residue_type",
        "distance",
        "lig_x",
        "lig_y",
        "lig_z",
        "prot_x",
        "prot_y",
        "prot_z",
    ]
    csv_path.write_text("")
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, indent=2) + "\n")
    return rows


def plip_interaction_rows(xml_path: Path) -> list[dict[str, str]]:
    root = ET.parse(xml_path).getroot()
    rows: list[dict[str, str]] = []
    for site in root.findall("bindingsite"):
        identifiers = site.find("identifiers")
        ligand = _text(identifiers, "longname") or _text(identifiers, "hetid") or ""
        chain = _text(identifiers, "chain")
        position = _text(identifiers, "position")
        ligand_id = ":".join(part for part in [ligand, chain, position] if part)
        ligand_type = _text(identifiers, "ligtype")
        interactions = site.find("interactions")
        if interactions is None:
            continue
        for group in interactions:
            interaction_type = group.tag
            for interaction in group:
                ligcoo = _coordinates(interaction, "ligcoo")
                protcoo = _coordinates(interaction, "protcoo")
                rows.append(
                    {
                        "ligand": ligand_id,
                        "ligand_type": ligand_type,
                        "interaction_type": interaction_type,
                        "residue_chain": _text(interaction, "reschain"),
                        "residue_number": _text(interaction, "resnr"),
                        "residue_type": _text(interaction, "restype"),
                        "distance": _interaction_distance(interaction),
                        "lig_x": ligcoo[0],
                        "lig_y": ligcoo[1],
                        "lig_z": ligcoo[2],
                        "prot_x": protcoo[0],
                        "prot_y": protcoo[1],
                        "prot_z": protcoo[2],
                    }
                )
    return rows


def _interaction_distance(interaction: ET.Element) -> str:
    for tag in ["dist", "dist_d-a", "dist_h-a", "centdist"]:
        value = _text(interaction, tag)
        if value:
            return value
    return ""


def _coordinates(interaction: ET.Element, tag: str) -> tuple[str, str, str]:
    parent = interaction.find(tag)
    if parent is None:
        return "", "", ""
    return (_text(parent, "x"), _text(parent, "y"), _text(parent, "z"))


def _text(element: ET.Element | None, tag: str) -> str:
    if element is None:
        return ""
    child = element.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _first_model_atom_lines(path: Path) -> list[str]:
    atoms: list[str] = []
    in_first_model = False
    has_model = False
    for line in path.read_text().splitlines():
        if line.startswith("MODEL"):
            has_model = True
            in_first_model = True
            continue
        if line.startswith("ENDMDL") and in_first_model:
            break
        if has_model and not in_first_model:
            continue
        if line.startswith(("ATOM  ", "HETATM")):
            atoms.append(line)
    return atoms


def _pdbqt_atom_to_pdb(
    line: str,
    hetatm: bool,
    serial: int | None = None,
    residue_name: str | None = None,
    chain: str | None = None,
    residue_number: int | None = None,
) -> str:
    record = "HETATM" if hetatm else line[:6]
    atom_serial = serial if serial is not None else int(line[6:11])
    atom_name = line[12:16]
    resname = (residue_name or line[17:20].strip() or "UNK")[:3].rjust(3)
    chain_id = (chain or line[21:22].strip() or "A")[:1]
    resnum = residue_number if residue_number is not None else int((line[22:26].strip() or "1"))
    x = float(line[30:38])
    y = float(line[38:46])
    z = float(line[46:54])
    element = _pdbqt_atom_type_to_element(line.split()[-1] if line.split() else "")
    if not element:
        element = "".join(ch for ch in atom_name if ch.isalpha())[:2].strip()
    pdb_line = (
        f"{record:<6}{atom_serial:5d} {atom_name:<4} {resname} {chain_id}"
        f"{resnum:4d}    {x:8.3f}{y:8.3f}{z:8.3f}"
        f"{1.00:6.2f}{0.00:6.2f}"
    )
    return f"{pdb_line:<76}{element:>2}  "


def _pdbqt_atom_type_to_element(atom_type: str) -> str:
    ad4_map = {
        "A": "C",
        "C": "C",
        "N": "N",
        "NA": "N",
        "NS": "N",
        "OA": "O",
        "OS": "O",
        "S": "S",
        "SA": "S",
        "P": "P",
        "F": "F",
        "Cl": "Cl",
        "CL": "Cl",
        "Br": "Br",
        "BR": "Br",
        "I": "I",
        "HD": "H",
        "H": "H",
    }
    return ad4_map.get(atom_type, "")
