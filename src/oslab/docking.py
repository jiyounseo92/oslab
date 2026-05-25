from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .schemas import BindingSiteRecord, ReceptorPrepRecord, VinaRunOptions, VinaRunRecord
from .structures import sha256_file


def _tool_path(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    env_path = Path(sys.executable).resolve().parent / name
    if env_path.exists():
        return str(env_path)
    raise FileNotFoundError(
        f"required executable '{name}' was not found on PATH or beside the active Python executable"
    )


def prepare_receptor_for_vina(
    input_pdb: Path,
    output_dir: Path,
    binding_site_json: Path | None = None,
    allow_bad_residues: bool = False,
    default_altloc: str | None = None,
    delete_residues: str | None = None,
) -> ReceptorPrepRecord:
    input_pdb = input_pdb.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    receptor_pdbqt = output_dir / "receptor.pdbqt"
    vina_box_config = output_dir / "vina_box.txt" if binding_site_json else None
    metadata_path = output_dir / "receptor_prep.json"

    cmd = [
        _tool_path("mk_prepare_receptor.py"),
        "-i",
        str(input_pdb),
        "-p",
        str(receptor_pdbqt),
    ]
    if allow_bad_residues:
        cmd.append("--allow_bad_res")
    if default_altloc:
        cmd.extend(["--default_altloc", default_altloc])
    if delete_residues:
        cmd.extend(["--delete_residues", delete_residues])
    if binding_site_json:
        site = BindingSiteRecord.model_validate(json.loads(binding_site_json.read_text()))
        cmd.extend(
            [
                "--box_center",
                str(site.box.center[0]),
                str(site.box.center[1]),
                str(site.box.center[2]),
                "--box_size",
                str(site.box.size[0]),
                str(site.box.size[1]),
                str(site.box.size[2]),
                "-v",
                str(vina_box_config),
            ]
        )

    subprocess.run(cmd, check=True, capture_output=True, text=True)
    if not receptor_pdbqt.exists() or receptor_pdbqt.stat().st_size == 0:
        raise RuntimeError(f"Meeko receptor preparation produced an empty PDBQT: {receptor_pdbqt}")

    record = ReceptorPrepRecord(
        input_pdb=str(input_pdb),
        receptor_pdbqt=str(receptor_pdbqt),
        vina_box_config=str(vina_box_config) if vina_box_config else None,
        metadata_path=str(metadata_path),
        input_sha256=sha256_file(input_pdb),
        receptor_pdbqt_sha256=sha256_file(receptor_pdbqt),
        command=cmd,
        created_at=datetime.now(timezone.utc),
        notes="Receptor prepared for AutoDock Vina with Meeko.",
    )
    metadata_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n")
    return record


def run_vina(
    receptor_pdbqt: Path,
    ligand_pdbqt: Path,
    binding_site_json: Path,
    output_dir: Path,
    options: VinaRunOptions | None = None,
) -> VinaRunRecord:
    options = options or VinaRunOptions()
    receptor_pdbqt = receptor_pdbqt.resolve()
    ligand_pdbqt = ligand_pdbqt.resolve()
    binding_site_json = binding_site_json.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    site = BindingSiteRecord.model_validate(json.loads(binding_site_json.read_text()))
    output_pdbqt = output_dir / f"{ligand_pdbqt.stem}_docked.pdbqt"
    log_path = output_dir / "vina.log"
    metadata_path = output_dir / "vina_run.json"

    cmd = [
        _tool_path("vina"),
        "--receptor",
        str(receptor_pdbqt),
        "--ligand",
        str(ligand_pdbqt),
        "--center_x",
        str(site.box.center[0]),
        "--center_y",
        str(site.box.center[1]),
        "--center_z",
        str(site.box.center[2]),
        "--size_x",
        str(site.box.size[0]),
        "--size_y",
        str(site.box.size[1]),
        "--size_z",
        str(site.box.size[2]),
        "--exhaustiveness",
        str(options.exhaustiveness),
        "--num_modes",
        str(options.num_modes),
        "--cpu",
        str(options.cpu),
        "--seed",
        str(options.seed),
        "--out",
        str(output_pdbqt),
    ]

    completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
    log_path.write_text(completed.stdout + completed.stderr)
    if not output_pdbqt.exists() or output_pdbqt.stat().st_size == 0:
        raise RuntimeError(f"Vina produced an empty output PDBQT: {output_pdbqt}")
    best_score = parse_vina_best_score(log_path)

    record = VinaRunRecord(
        receptor_pdbqt=str(receptor_pdbqt),
        ligand_pdbqt=str(ligand_pdbqt),
        binding_site_json=str(binding_site_json),
        output_pdbqt=str(output_pdbqt),
        log_path=str(log_path),
        metadata_path=str(metadata_path),
        best_score=best_score,
        receptor_sha256=sha256_file(receptor_pdbqt),
        ligand_sha256=sha256_file(ligand_pdbqt),
        output_sha256=sha256_file(output_pdbqt) if output_pdbqt.exists() else None,
        command=cmd,
        options=options,
        created_at=datetime.now(timezone.utc),
        notes="AutoDock Vina docking run.",
    )
    metadata_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n")
    return record


def parse_vina_best_score(log_path: Path) -> float | None:
    pattern = re.compile(r"^\s*1\s+(-?\d+(?:\.\d+)?)\s+")
    for line in log_path.read_text().splitlines():
        match = pattern.match(line)
        if match:
            return float(match.group(1))
    return None
