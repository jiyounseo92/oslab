from __future__ import annotations

import sys
from pathlib import Path

from .ligand_sources import get_ligand_source
from .model import CommandStep, Workflow


def build_docking_workflow(
    receptor: Path,
    ligands: Path,
    output_dir: Path,
    center: tuple[float, float, float],
    size: tuple[float, float, float],
    ligand_source_key: str = "custom-sdf",
) -> Workflow:
    receptor = receptor.resolve()
    ligands = ligands.resolve()
    output_dir = output_dir.resolve()

    prepared_receptor = output_dir / "prepared" / "receptor_prepared.pdb"
    minimized_receptor = output_dir / "prepared" / "receptor_minimized.pdb"
    receptor_pdbqt = output_dir / "docking" / "receptor.pdbqt"
    ligands_sdf = output_dir / "ligands" / "ligands_prepared.sdf"
    ligands_pdbqt = output_dir / "docking" / "ligands.pdbqt"
    docked = output_dir / "docking" / "docked_poses.pdbqt"
    log = output_dir / "docking" / "vina.log"
    python = sys.executable or "python3"
    ligand_source = get_ligand_source(ligand_source_key)

    steps = [
        CommandStep(
            name="prepare-protein",
            argv=[
                python,
                "-m",
                "oslab.refine_openmm",
                "--input",
                str(receptor),
                "--output",
                str(prepared_receptor),
                "--mode",
                "fix",
            ],
            inputs=[str(receptor)],
            outputs=[str(prepared_receptor)],
            notes="Repairs missing heavy atoms/residues when PDBFixer can infer them.",
        ),
        CommandStep(
            name="minimize-protein",
            argv=[
                python,
                "-m",
                "oslab.refine_openmm",
                "--input",
                str(prepared_receptor),
                "--output",
                str(minimized_receptor),
                "--mode",
                "minimize",
            ],
            inputs=[str(prepared_receptor)],
            outputs=[str(minimized_receptor)],
            notes="Runs restrained all-atom minimization with OpenMM when installed.",
        ),
    ]

    if ligand_source.vina_ready:
        docking_ligand_input = ligands
        steps.append(
            CommandStep(
                name="use-vina-ready-ligands",
                argv=[python, "-c", "pass"],
                inputs=[str(ligands)],
                outputs=[str(ligands)],
                notes=(
                    f"{ligand_source.name} is marked Vina-ready. "
                    "Skipping RDKit/Meeko ligand preparation; only do this when ligand provenance is trusted."
                ),
            )
        )
    else:
        docking_ligand_input = ligands_pdbqt
        steps.extend(
            [
                CommandStep(
                    name="prepare-ligands",
                    argv=["obabel", str(ligands), "-O", str(ligands_sdf), "--gen3d", "-p", "7.4"],
                    inputs=[str(ligands)],
                    outputs=[str(ligands_sdf)],
                    notes="Use RDKit standardization before this step for production screens.",
                ),
                CommandStep(
                    name="ligands-to-pdbqt",
                    argv=["mk_prepare_ligand.py", "-i", str(ligands_sdf), "-o", str(ligands_pdbqt)],
                    inputs=[str(ligands_sdf)],
                    outputs=[str(ligands_pdbqt)],
                    notes="Meeko prepares ligand atom types, torsions, and charges for Vina-family docking.",
                ),
            ]
        )

    steps.extend(
        [
            CommandStep(
                name="receptor-to-pdbqt",
                argv=[
                    "mk_prepare_receptor.py",
                    "-i",
                    str(minimized_receptor),
                    "-o",
                    str(receptor_pdbqt),
                ],
                inputs=[str(minimized_receptor)],
                outputs=[str(receptor_pdbqt)],
                notes="Meeko prepares receptor atom types and charges for Vina-family docking.",
            ),
            CommandStep(
                name="dock-vina",
                argv=[
                    "vina",
                    "--receptor",
                    str(receptor_pdbqt),
                    "--ligand",
                    str(docking_ligand_input),
                    "--center_x",
                    str(center[0]),
                    "--center_y",
                    str(center[1]),
                    "--center_z",
                    str(center[2]),
                    "--size_x",
                    str(size[0]),
                    "--size_y",
                    str(size[1]),
                    "--size_z",
                    str(size[2]),
                    "--out",
                    str(docked),
                    "--log",
                    str(log),
                ],
                inputs=[str(receptor_pdbqt), str(docking_ligand_input)],
                outputs=[str(docked), str(log)],
                notes="Docking box must be selected from an active site, known ligand, pocket finder, or domain knowledge.",
            ),
        ]
    )

    return Workflow(
        receptor=str(receptor),
        ligands=str(ligands),
        output_dir=str(output_dir),
        center=center,
        size=size,
        steps=steps,
        ligand_source=ligand_source.to_dict(),
    )
