from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import ProteinPrepOptions, ProteinPrepRecord
from .structures import sha256_file


def _version_or_unknown(module_name: str) -> str:
    try:
        module = __import__(module_name)
    except Exception:
        return "unavailable"
    return str(getattr(module, "__version__", "unknown"))


def fix_protein_structure(input_path: Path, output_path: Path, options: ProteinPrepOptions) -> list[str]:
    try:
        from openmm.app import PDBFile
        from pdbfixer import PDBFixer
    except Exception as exc:  # pragma: no cover - depends on optional stack
        raise RuntimeError("PDBFixer/OpenMM are required for protein preparation") from exc

    warnings: list[str] = []
    fixer = PDBFixer(filename=str(input_path))

    fixer.findMissingResidues()
    if fixer.missingResidues:
        warnings.append(f"missing residues detected: {len(fixer.missingResidues)} chain-position entries")

    fixer.findNonstandardResidues()
    if fixer.nonstandardResidues:
        warnings.append(f"nonstandard residues replaced: {len(fixer.nonstandardResidues)}")
    fixer.replaceNonstandardResidues()

    fixer.removeHeterogens(keepWater=options.keep_water)
    if options.keep_water:
        warnings.append("waters were retained during heterogen removal")
    else:
        warnings.append("waters and heterogens were removed during receptor preparation")

    fixer.findMissingAtoms()
    missing_atom_count = sum(len(atoms) for atoms in fixer.missingAtoms.values())
    missing_terminal_count = sum(len(atoms) for atoms in fixer.missingTerminals.values())
    if missing_atom_count or missing_terminal_count:
        warnings.append(f"missing atoms added: {missing_atom_count}; missing terminal atoms added: {missing_terminal_count}")
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(options.ph)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        PDBFile.writeFile(fixer.topology, fixer.positions, handle)
    return warnings


def minimize_protein_structure(input_path: Path, output_path: Path, options: ProteinPrepOptions) -> list[str]:
    try:
        from openmm import LangevinMiddleIntegrator, unit
        from openmm.app import ForceField, Modeller, PDBFile, Simulation
    except Exception as exc:  # pragma: no cover - depends on optional stack
        raise RuntimeError("OpenMM is required for protein minimization") from exc

    warnings: list[str] = []
    pdb = PDBFile(str(input_path))
    modeller = Modeller(pdb.topology, pdb.positions)
    forcefield = ForceField("amber14-all.xml", "amber14/tip3pfb.xml")
    system = forcefield.createSystem(modeller.topology)
    integrator = LangevinMiddleIntegrator(
        300 * unit.kelvin,
        1 / unit.picosecond,
        0.004 * unit.picoseconds,
    )
    simulation = Simulation(modeller.topology, system, integrator)
    simulation.context.setPositions(modeller.positions)
    simulation.minimizeEnergy(maxIterations=options.max_minimization_iterations)
    state = simulation.context.getState(getPositions=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        PDBFile.writeFile(modeller.topology, state.getPositions(), handle)
    warnings.append(f"OpenMM minimization completed with maxIterations={options.max_minimization_iterations}")
    return warnings


def prepare_protein(
    input_path: Path,
    output_dir: Path,
    options: ProteinPrepOptions | None = None,
) -> ProteinPrepRecord:
    options = options or ProteinPrepOptions()
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    fixed_path = output_dir / "protein_fixed.pdb"
    prepared_path = output_dir / "protein_prepared.pdb"
    metadata_path = output_dir / "protein_prep.json"

    warnings = fix_protein_structure(input_path, fixed_path, options)
    if options.minimize:
        warnings.extend(minimize_protein_structure(fixed_path, prepared_path, options))
    else:
        prepared_path.write_bytes(fixed_path.read_bytes())
        warnings.append("OpenMM minimization skipped by user option")

    record = ProteinPrepRecord(
        input_path=str(input_path),
        fixed_path=str(fixed_path),
        prepared_path=str(prepared_path),
        metadata_path=str(metadata_path),
        input_sha256=sha256_file(input_path),
        fixed_sha256=sha256_file(fixed_path),
        prepared_sha256=sha256_file(prepared_path),
        prepared_at=datetime.now(timezone.utc),
        options=options,
        tool_versions={
            "openmm": _version_or_unknown("openmm"),
            "pdbfixer": _version_or_unknown("pdbfixer"),
        },
        warnings=warnings,
        notes="Protein prepared with PDBFixer and optionally minimized with OpenMM.",
    )
    metadata_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n")
    return record

