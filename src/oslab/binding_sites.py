from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import gemmi

from .domain_annotations import annotate_pockets
from .schemas import BindingSiteRecord, DockingBox


COMMON_NON_LIGANDS = {
    "HOH",
    "WAT",
    "DOD",
    "NA",
    "CL",
    "K",
    "MG",
    "CA",
    "ZN",
    "MN",
    "SO4",
    "PO4",
    "GOL",
    "EDO",
}


def _read_structure(path: Path) -> gemmi.Structure:
    suffix = path.suffix.lower()
    if suffix in {".cif", ".mmcif"}:
        return gemmi.read_structure(str(path))
    return gemmi.read_pdb(str(path))


def _atom_position(atom: gemmi.Atom) -> tuple[float, float, float]:
    return (float(atom.pos.x), float(atom.pos.y), float(atom.pos.z))


def _centroid(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    if not points:
        raise ValueError("cannot calculate centroid with no selected atoms")
    count = float(len(points))
    return (
        sum(point[0] for point in points) / count,
        sum(point[1] for point in points) / count,
        sum(point[2] for point in points) / count,
    )


def _box_size(points: list[tuple[float, float, float]], padding: float, minimum_size: float) -> tuple[float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    return (
        max(max(xs) - min(xs) + padding * 2, minimum_size),
        max(max(ys) - min(ys) + padding * 2, minimum_size),
        max(max(zs) - min(zs) + padding * 2, minimum_size),
    )


def _write_record(record: BindingSiteRecord) -> BindingSiteRecord:
    metadata_path = Path(record.metadata_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n")
    return record


def find_ligand_residue_names(structure_path: Path) -> list[str]:
    structure = _read_structure(structure_path)
    names: set[str] = set()
    for model in structure:
        for chain in model:
            for residue in chain:
                if residue.het_flag == "H" and residue.name.strip() not in COMMON_NON_LIGANDS:
                    names.add(residue.name.strip())
    return sorted(names)


def box_from_ligand(
    structure_path: Path,
    ligand: str,
    output_dir: Path,
    padding: float = 6.0,
    minimum_size: float = 12.0,
    chain: str | None = None,
) -> BindingSiteRecord:
    structure_path = structure_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ligand = ligand.strip().upper()

    structure = _read_structure(structure_path)
    points: list[tuple[float, float, float]] = []
    residues: list[str] = []
    for model in structure:
        for gemmi_chain in model:
            if chain and gemmi_chain.name != chain:
                continue
            for residue in gemmi_chain:
                if residue.name.strip().upper() != ligand:
                    continue
                residues.append(f"{gemmi_chain.name}:{residue.name}{residue.seqid.num}{residue.seqid.icode.strip()}")
                for atom in residue:
                    if not atom.is_hydrogen():
                        points.append(_atom_position(atom))

    if not points:
        choices = ", ".join(find_ligand_residue_names(structure_path))
        raise ValueError(f"ligand '{ligand}' was not found. Available non-water heterogens: {choices or 'none'}")

    record = BindingSiteRecord(
        method="ligand-centroid",
        structure_path=str(structure_path),
        metadata_path=str(output_dir / "binding_site.json"),
        box=DockingBox(center=_centroid(points), size=_box_size(points, padding, minimum_size)),
        selected_atom_count=len(points),
        selected_residues=sorted(set(residues)),
        padding=padding,
        created_at=datetime.now(timezone.utc),
        notes=f"Docking box centered on ligand residue name {ligand}.",
    )
    return _write_record(record)


def box_from_residues(
    structure_path: Path,
    residues: list[str],
    output_dir: Path,
    padding: float = 6.0,
    minimum_size: float = 12.0,
) -> BindingSiteRecord:
    structure_path = structure_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    wanted = {_normalize_residue_selector(residue) for residue in residues}

    structure = _read_structure(structure_path)
    points: list[tuple[float, float, float]] = []
    found: set[str] = set()
    for model in structure:
        for chain in model:
            for residue in chain:
                selector = (chain.name, residue.seqid.num, residue.seqid.icode.strip())
                if selector not in wanted:
                    continue
                found.add(_format_residue_selector(selector))
                for atom in residue:
                    if not atom.is_hydrogen():
                        points.append(_atom_position(atom))

    missing = sorted(_format_residue_selector(selector) for selector in wanted if _format_residue_selector(selector) not in found)
    if missing:
        raise ValueError(f"residue selectors not found: {', '.join(missing)}")
    if not points:
        raise ValueError("no atoms selected for residue-based docking box")

    record = BindingSiteRecord(
        method="residue-centroid",
        structure_path=str(structure_path),
        metadata_path=str(output_dir / "binding_site.json"),
        box=DockingBox(center=_centroid(points), size=_box_size(points, padding, minimum_size)),
        selected_atom_count=len(points),
        selected_residues=sorted(found),
        padding=padding,
        created_at=datetime.now(timezone.utc),
        notes="Docking box centered on selected residues.",
    )
    return _write_record(record)


def run_fpocket(
    structure_path: Path,
    output_dir: Path,
    top_n: int = 8,
    min_spheres: int = 15,
    padding: float = 4.0,
    minimum_size: float = 10.0,
    target_identifier: str | None = None,
) -> dict[str, object]:
    structure_path = structure_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    working_structure = output_dir / structure_path.name
    if working_structure != structure_path:
        shutil.copy2(structure_path, working_structure)

    fpocket_dir = output_dir / f"{working_structure.stem}_out"
    if fpocket_dir.exists():
        shutil.rmtree(fpocket_dir)
    # fpocket mishandles absolute output paths that contain spaces. Run in the
    # copied-structure directory and pass only the local filename.
    command = ["fpocket", "-f", working_structure.name, "-i", str(min_spheres), "-w", "both"]
    completed = subprocess.run(command, cwd=output_dir, check=True, capture_output=True, text=True)
    info_path = fpocket_dir / f"{working_structure.stem}_info.txt"
    pockets = parse_fpocket_output(info_path, fpocket_dir / "pockets", padding=padding, minimum_size=minimum_size)[:top_n]
    # Annotate each pocket with lining residues and (when a UniProt mapping is
    # available) protein-domain coverage. Falls back to residue-list-only when
    # the structure has no PDB/UniProt identifier.
    identifier = target_identifier or working_structure.stem
    annotate_pockets(pockets, fpocket_out_dir=fpocket_dir, target_identifier=identifier)
    result = {
        "structure_path": str(structure_path),
        "output_dir": str(output_dir),
        "fpocket_dir": str(fpocket_dir),
        "info_path": str(info_path),
        "pockets": pockets,
        "padding": padding,
        "minimum_size": minimum_size,
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "fpocket_pockets.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def parse_fpocket_output(
    info_path: Path,
    pockets_dir: Path,
    padding: float = 4.0,
    minimum_size: float = 10.0,
) -> list[dict[str, object]]:
    metrics = _parse_fpocket_info(info_path)
    pockets: list[dict[str, object]] = []
    for pocket_id, values in metrics.items():
        vert_path = pockets_dir / f"pocket{pocket_id}_vert.pqr"
        points = _read_pqr_points(vert_path)
        if not points:
            continue
        center = _centroid(points)
        size = _box_size(points, padding=padding, minimum_size=minimum_size)
        pockets.append(
            {
                "pocket_id": pocket_id,
                "score": values.get("Score"),
                "druggability_score": values.get("Druggability Score"),
                "volume": values.get("Volume"),
                "alpha_spheres": int(values.get("Number of Alpha Spheres", len(points))),
                "center": center,
                "size": size,
                "points": points,
                "vert_pqr": str(vert_path),
            }
        )
    pockets.sort(key=lambda pocket: float(pocket.get("score") or 0), reverse=True)
    return pockets


def box_from_fpocket(
    structure_path: Path,
    pocket: dict[str, object],
    output_dir: Path,
    padding: float = 4.0,
    minimum_size: float = 10.0,
) -> BindingSiteRecord:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    vert_path = Path(str(pocket["vert_pqr"]))
    points = _read_pqr_points(vert_path)
    if not points:
        raise ValueError(f"fpocket pocket has no alpha-sphere coordinates: {vert_path}")
    center = _centroid(points)
    size = _box_size(points, padding=padding, minimum_size=minimum_size)
    pocket_id = int(pocket["pocket_id"])
    record = BindingSiteRecord(
        method="fpocket",
        structure_path=str(structure_path.resolve()),
        metadata_path=str(output_dir / "binding_site.json"),
        box=DockingBox(center=center, size=size),
        selected_atom_count=len(points),
        selected_residues=[f"fpocket:pocket{pocket_id}"],
        padding=padding,
        created_at=datetime.now(timezone.utc),
        notes=(
            f"Docking box generated from fpocket pocket {pocket_id}; "
            f"score={pocket.get('score')}, druggability={pocket.get('druggability_score')}, volume={pocket.get('volume')}."
        ),
    )
    return _write_record(record)


def _parse_fpocket_info(info_path: Path) -> dict[int, dict[str, float]]:
    pockets: dict[int, dict[str, float]] = {}
    current: int | None = None
    pocket_re = re.compile(r"^Pocket\s+(\d+)\s*:")
    metric_re = re.compile(r"^\s*([^:]+?)\s*:\s*([-+]?\d+(?:\.\d+)?)")
    for line in info_path.read_text().splitlines():
        pocket_match = pocket_re.match(line)
        if pocket_match:
            current = int(pocket_match.group(1))
            pockets[current] = {}
            continue
        if current is None:
            continue
        metric_match = metric_re.match(line)
        if metric_match:
            pockets[current][metric_match.group(1).strip()] = float(metric_match.group(2))
    return pockets


def _read_pqr_points(path: Path) -> list[tuple[float, float, float]]:
    points: list[tuple[float, float, float]] = []
    if not path.exists():
        return points
    for line in path.read_text().splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        parts = line.split()
        if len(parts) >= 8:
            x, y, z = parts[-5:-2]
            points.append((float(x), float(y), float(z)))
    return points


def _normalize_residue_selector(selector: str) -> tuple[str, int, str]:
    parts = selector.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(f"residue selector must look like CHAIN:NUMBER, got '{selector}'")
    chain = parts[0]
    residue = parts[1]
    insertion_code = ""
    if residue[-1:].isalpha():
        insertion_code = residue[-1]
        residue = residue[:-1]
    return (chain, int(residue), insertion_code)


def _format_residue_selector(selector: tuple[str, int, str]) -> str:
    chain, residue_number, insertion_code = selector
    return f"{chain}:{residue_number}{insertion_code}"
