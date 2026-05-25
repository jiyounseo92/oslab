from __future__ import annotations

import argparse
import sys
from pathlib import Path


def fix_structure(input_path: Path, output_path: Path) -> None:
    try:
        from pdbfixer import PDBFixer
        from openmm.app import PDBFile
    except Exception as exc:  # pragma: no cover - depends on optional stack
        raise SystemExit(
            "PDBFixer/OpenMM are required for structure fixing. "
            "Install with conda-forge packages: pdbfixer openmm."
        ) from exc

    fixer = PDBFixer(filename=str(input_path))
    fixer.findMissingResidues()
    fixer.findNonstandardResidues()
    fixer.replaceNonstandardResidues()
    fixer.removeHeterogens(keepWater=True)
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(7.4)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        PDBFile.writeFile(fixer.topology, fixer.positions, handle)


def minimize_structure(input_path: Path, output_path: Path) -> None:
    try:
        from openmm import LangevinMiddleIntegrator, unit
        from openmm.app import ForceField, Modeller, PDBFile, Simulation
    except Exception as exc:  # pragma: no cover - depends on optional stack
        raise SystemExit(
            "OpenMM is required for minimization. Install with conda-forge package: openmm."
        ) from exc

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
    simulation.minimizeEnergy(maxIterations=500)
    state = simulation.context.getState(getPositions=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        PDBFile.writeFile(modeller.topology, state.getPositions(), handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repair or minimize a protein structure with PDBFixer/OpenMM.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=["fix", "minimize"], required=True)
    args = parser.parse_args(argv)

    if args.mode == "fix":
        fix_structure(args.input, args.output)
    else:
        minimize_structure(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
