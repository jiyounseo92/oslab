"""
MD system preparation: protein cleaning, GAFF2 ligand parametrization, solvation, and energy minimization.

Pipeline
--------
1. Extract protein PDB from receptor PDBQT (or accept a pre-prepared PDB directly).
2. Run PDBFixer to repair missing atoms/residues and add hydrogens at pH 7.4.
3. Read the docked ligand pose from a PDBQT file via meeko → RDKit Mol (preserves
   docked coordinates, proper connectivity).
4. Create an openff Molecule from SMILES and assign docked coordinates to it.
5. Parametrize protein with AMBER14 + TIP3P-FB; ligand with GAFF2 via
   openmmforcefields.
6. Assemble protein-ligand complex, solvate with explicit TIP3P water (1.2 nm
   padding) and 0.15 M NaCl.
7. Energy minimise (configurable iterations).
8. Write: protein.pdb, ligand.sdf, topology.pdb, system.xml, prep_record.json.
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gpu import openmm_platform_from_env
from .jobs import DEFAULT_RDKIT_SEED, set_rdkit_seed
from .schemas import MdPrepOptions, MdPrepRecord


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def prepare_md_system(
    receptor_pdbqt: Path,
    docked_ligand_pdbqt: Path,
    ligand_smiles: str,
    output_dir: Path,
    options: MdPrepOptions | None = None,
    protein_pdb: Path | None = None,
) -> MdPrepRecord:
    """Prepare a solvated protein-ligand OpenMM system ready for MD.

    Parameters
    ----------
    receptor_pdbqt:
        Meeko-prepared receptor PDBQT file (from Vina docking setup).
    docked_ligand_pdbqt:
        Vina output PDBQT for the best-scored ligand pose.
    ligand_smiles:
        Canonical SMILES string for the ligand.
    output_dir:
        Directory where all outputs are written.
    options:
        Preparation settings; uses defaults if None.
    protein_pdb:
        Optional pre-prepared protein PDB.  If supplied, the receptor PDBQT is
        used only for the bounding box and the protein PDB is passed directly to
        PDBFixer.  This is preferred when the original prepared PDB is available.

    Returns
    -------
    MdPrepRecord  (also written to output_dir/prep_record.json).
    """
    _require_openmm()
    options = options or MdPrepOptions()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    commands: list[list[str]] = []

    # ------------------------------------------------------------------ #
    # 1. Protein: PDBQT → clean PDB (or use provided PDB)               #
    # ------------------------------------------------------------------ #
    if protein_pdb is not None:
        protein_pdb = protein_pdb.resolve()
        raw_protein_pdb = protein_pdb
    else:
        raw_protein_pdb = output_dir / "protein_raw.pdb"
        _receptor_pdbqt_to_pdb(receptor_pdbqt, raw_protein_pdb)

    fixed_protein_pdb = output_dir / "protein.pdb"
    _fix_protein(raw_protein_pdb, fixed_protein_pdb, options.ph, options.keep_water)

    # ------------------------------------------------------------------ #
    # 2. Ligand: docked PDBQT → RDKit Mol with docked coords            #
    # ------------------------------------------------------------------ #
    ligand_sdf = output_dir / "ligand.sdf"
    rdmol = _docked_pdbqt_to_rdmol(docked_ligand_pdbqt, ligand_smiles, ligand_sdf, warnings)

    # ------------------------------------------------------------------ #
    # 3. Assemble, solvate, minimise                                     #
    # ------------------------------------------------------------------ #
    topology_pdb = output_dir / "topology.pdb"
    system_xml = output_dir / "system.xml"
    _assemble_and_solvate(
        fixed_protein_pdb,
        rdmol,
        topology_pdb,
        system_xml,
        options,
        warnings,
    )

    # ------------------------------------------------------------------ #
    # 4. Write record                                                     #
    # ------------------------------------------------------------------ #
    from openmm import version as _ov
    from openff.toolkit import __version__ as _offv

    record = MdPrepRecord(
        receptor_pdbqt=str(receptor_pdbqt.resolve()),
        docked_ligand_pdbqt=str(docked_ligand_pdbqt.resolve()),
        ligand_smiles=ligand_smiles,
        protein_pdb=str(fixed_protein_pdb),
        ligand_sdf=str(ligand_sdf),
        topology_pdb=str(topology_pdb),
        system_xml=str(system_xml),
        output_dir=str(output_dir),
        metadata_path=str(output_dir / "prep_record.json"),
        options=options,
        tool_versions={
            "openmm": str(_ov.full_version),
            "openff_toolkit": str(_offv),
        },
        warnings=warnings,
        created_at=datetime.now(timezone.utc),
    )
    (output_dir / "prep_record.json").write_text(
        json.dumps(record.model_dump(mode="json"), indent=2) + "\n"
    )
    return record


# ---------------------------------------------------------------------------
# SMILES utility (used by CLI / hit-refinement data)
# ---------------------------------------------------------------------------

def smiles_from_pdbqt(pdbqt_path: Path) -> str | None:
    """Return the SMILES stored in a ``REMARK SMILES`` line of a PDBQT file.

    Returns None if no such remark is present.
    """
    for line in pdbqt_path.read_text().splitlines():
        if line.startswith("REMARK SMILES"):
            parts = line.split(None, 2)
            if len(parts) >= 3:
                return parts[2].strip()
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_openmm() -> None:
    try:
        import openmm  # noqa: F401
        import pdbfixer  # noqa: F401
        from openmmforcefields.generators import SMIRNOFFTemplateGenerator  # noqa: F401
        from openff.toolkit import Molecule  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "MD preparation requires: openmm pdbfixer openmmforcefields openff-toolkit. "
            f"Install via conda-forge.  Missing: {exc.name}"
        ) from exc


def _receptor_pdbqt_to_pdb(pdbqt_path: Path, out_pdb: Path) -> None:
    """Convert receptor PDBQT → PDB using the same atom mapping as interactions.py."""
    from .interactions import _pdbqt_atom_to_pdb

    lines: list[str] = []
    for line in pdbqt_path.read_text().splitlines():
        if line.startswith(("ATOM  ", "HETATM")):
            lines.append(_pdbqt_atom_to_pdb(line, hetatm=False))
    lines.append("END")
    out_pdb.write_text("\n".join(lines) + "\n")


def _fix_protein(
    input_pdb: Path,
    output_pdb: Path,
    ph: float = 7.4,
    keep_water: bool = False,
) -> None:
    """Run PDBFixer on the protein structure."""
    from pdbfixer import PDBFixer
    from openmm.app import PDBFile

    fixer = PDBFixer(filename=str(input_pdb))
    fixer.findMissingResidues()
    fixer.findNonstandardResidues()
    fixer.replaceNonstandardResidues()
    fixer.removeHeterogens(keepWater=keep_water)
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(ph)

    with output_pdb.open("w") as fh:
        PDBFile.writeFile(fixer.topology, fixer.positions, fh)


def _docked_pdbqt_to_rdmol(
    docked_pdbqt: Path,
    smiles: str,
    ligand_sdf: Path,
    warnings: list[str],
):
    """Return an RDKit Mol with the docked 3-D coordinates.

    Strategy
    --------
    1. Try meeko PDBQTMolecule → rdkit export (preserves docked coords + torsion info).
    2. Fall back: embed a conformer from the provided SMILES with ETKDGv3.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem, SDWriter

    rdmol = None

    # --- attempt 1: meeko ---
    try:
        from meeko import PDBQTMolecule, RDKitMolCreate
        pdbqtmol = PDBQTMolecule.from_file(str(docked_pdbqt), skip_typing=True)
        mols = RDKitMolCreate.from_pdbqt_mol(pdbqtmol)
        rdmol = mols[0] if mols else None
        if rdmol is None or rdmol.GetNumAtoms() == 0:
            rdmol = None
            warnings.append("meeko export produced empty mol; falling back to SMILES conformer.")
    except Exception as exc:
        warnings.append(f"meeko docked-PDBQT export failed ({exc}); using SMILES conformer.")
        rdmol = None

    # --- attempt 2: SMILES + ETKDGv3 ---
    if rdmol is None:
        set_rdkit_seed()
        rdmol = Chem.MolFromSmiles(smiles)
        if rdmol is None:
            raise ValueError(f"Cannot parse SMILES: {smiles!r}")
        rdmol = Chem.AddHs(rdmol)
        params = AllChem.ETKDGv3()
        params.randomSeed = DEFAULT_RDKIT_SEED
        rc = AllChem.EmbedMolecule(rdmol, params)
        if rc != 0:
            retry_params = AllChem.ETKDGv3()
            retry_params.randomSeed = DEFAULT_RDKIT_SEED
            AllChem.EmbedMolecule(rdmol, retry_params)
        AllChem.MMFFOptimizeMolecule(rdmol)
        warnings.append(
            "Ligand starting coordinates are from SMILES 3-D embedding, not the docked pose. "
            "Consider verifying the docked PDBQT before production MD."
        )

    # Write SDF for record-keeping
    with SDWriter(str(ligand_sdf)) as writer:
        writer.write(rdmol)

    return rdmol


def _assemble_and_solvate(
    protein_pdb: Path,
    ligand_rdmol,
    topology_pdb: Path,
    system_xml: Path,
    options: "MdPrepOptions",
    warnings: list[str],
) -> None:
    """Assemble complex, solvate, minimise, write topology.pdb and system.xml."""
    from openmm import XmlSerializer, LangevinMiddleIntegrator, Platform, unit
    from openmm.app import (
        ForceField,
        Modeller,
        PDBFile,
        Simulation,
        PME,
        HBonds,
    )
    from openff.toolkit import Molecule, Topology as OFFTopology
    from openmmforcefields.generators import SMIRNOFFTemplateGenerator

    # --- protein ---
    protein = PDBFile(str(protein_pdb))
    modeller = Modeller(protein.topology, protein.positions)

    # --- ligand openff Molecule (SMIRNOFF Sage for charges + bonded params) ---
    offmol = _rdmol_to_offmol(ligand_rdmol, warnings)

    # --- forcefields ---
    smirnoff = SMIRNOFFTemplateGenerator(molecules=[offmol], forcefield=options.smirnoff_forcefield)
    ff = ForceField("amber14-all.xml", "amber14/tip3pfb.xml")
    ff.registerTemplateGenerator(smirnoff.generator)

    # --- add ligand to modeller ---
    off_topology = OFFTopology.from_molecules([offmol])
    omm_lig_topology = off_topology.to_openmm()
    # positions: openff conformer in nanometres
    import numpy as np
    conf = offmol.conformers[0]
    # openff stores in Angstroms (openff.units); convert to nm for OpenMM
    lig_positions_nm = [
        (float(conf[i, 0].magnitude) / 10.0,
         float(conf[i, 1].magnitude) / 10.0,
         float(conf[i, 2].magnitude) / 10.0) * unit.nanometer
        for i in range(conf.shape[0])
    ]
    modeller.add(omm_lig_topology, lig_positions_nm)

    # Rename the ligand residue to LIG so downstream tools can find it
    for res in modeller.topology.residues():
        if res.name == "UNK":
            res.name = "LIG"

    # --- solvate ---
    modeller.addSolvent(
        ff,
        padding=options.water_padding_nm * unit.nanometer,
        ionicStrength=options.ionic_strength_m * unit.molar,
        neutralize=True,
    )

    # --- create system ---
    system = ff.createSystem(
        modeller.topology,
        nonbondedMethod=PME,
        nonbondedCutoff=1.0 * unit.nanometer,
        constraints=HBonds,
    )

    # --- minimise ---
    integrator = LangevinMiddleIntegrator(
        options.temperature_k * unit.kelvin,
        1.0 / unit.picosecond,
        0.002 * unit.picoseconds,
    )
    platform, platform_properties = openmm_platform_from_env(Platform)
    if platform is None:
        simulation = Simulation(modeller.topology, system, integrator)
    else:
        simulation = Simulation(modeller.topology, system, integrator, platform, platform_properties)
    simulation.context.setPositions(modeller.positions)
    simulation.minimizeEnergy(maxIterations=options.minimization_steps)

    state = simulation.context.getState(getPositions=True)

    # --- write outputs ---
    with topology_pdb.open("w") as fh:
        PDBFile.writeFile(modeller.topology, state.getPositions(), fh)

    with system_xml.open("w") as fh:
        fh.write(XmlSerializer.serialize(system))


def _rdmol_to_offmol(rdmol, warnings: list[str]):
    """Convert RDKit Mol → openff Molecule, preserving 3-D conformer."""
    from openff.toolkit import Molecule
    import numpy as np

    try:
        offmol = Molecule.from_rdkit(rdmol, allow_undefined_stereo=True)
    except Exception as exc:
        warnings.append(
            f"openff Molecule.from_rdkit failed ({exc}); trying from SMILES fallback."
        )
        smiles = _rdmol_to_smiles(rdmol)
        offmol = Molecule.from_smiles(smiles, allow_undefined_stereo=True)

    # Make sure we have a conformer set to the docked/embedded coords
    if offmol.n_conformers == 0 and rdmol.GetNumConformers() > 0:
        from openff.units import unit as offunit
        conf = rdmol.GetConformer(0)
        positions = np.array(
            [[conf.GetAtomPosition(i).x,
              conf.GetAtomPosition(i).y,
              conf.GetAtomPosition(i).z]
             for i in range(rdmol.GetNumAtoms())]
        ) * offunit.angstrom
        offmol.add_conformer(positions)

    if offmol.n_conformers == 0:
        warnings.append("No 3-D conformer on ligand; generating one with ETKDGv3.")
        offmol.generate_conformers(n_conformers=1)

    # Assign AM1-BCC charges (GAFF2 standard; cached after first call)
    try:
        offmol.assign_partial_charges("gasteiger")
    except Exception as exc:
        warnings.append(f"Gasteiger charge assignment failed ({exc}); using zeros.")
        offmol.assign_partial_charges("zeros")

    return offmol


def _rdmol_to_smiles(rdmol) -> str:
    from rdkit import Chem
    return Chem.MolToSmiles(Chem.RemoveHs(rdmol))
