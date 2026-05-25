"""
MMGBSA binding energy estimation using OpenMM implicit solvent.

Computes an approximate ΔG_bind by evaluating potential energies of complex,
apo-protein, and isolated ligand under the GB-OBC2 implicit solvent model, then
applying:

    ΔG_bind ≈ <E_complex> − <E_protein> − <E_ligand>

Frames are sampled uniformly from the explicit-solvent MD trajectory.  The
solvent is stripped before implicit-solvent energy evaluation.

Note
----
MMGBSA gives a *relative* ranking signal.  Results are not calibrated absolute
binding free energies.  Use them to re-rank a set of hits from the same
series, not as absolute ΔG predictions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .gpu import openmm_platform_from_env
from .schemas import MmgbsaOptions, MmgbsaRecord


def estimate_mmgbsa(
    topology_pdb: Path,
    trajectory_dcd: Path,
    output_dir: Path,
    options: MmgbsaOptions | None = None,
) -> MmgbsaRecord:
    """Estimate MMGBSA binding energy from an explicit-solvent MD trajectory.

    Parameters
    ----------
    topology_pdb:
        Solvated complex PDB (from ``prepare_md_system``).
    trajectory_dcd:
        Production DCD trajectory (from ``run_md``).
    output_dir:
        Where results are written.
    options:
        MMGBSA settings; uses defaults if None.

    Returns
    -------
    MmgbsaRecord written to output_dir/mmgbsa_record.json.
    """
    _require_stack()
    options = options or MmgbsaOptions()
    topology_pdb = Path(topology_pdb)
    trajectory_dcd = Path(trajectory_dcd)
    output_dir = Path(output_dir)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    import MDAnalysis as mda
    import numpy as np
    from openmm import unit

    # ------------------------------------------------------------------ #
    # Load trajectory and select frames                                  #
    # ------------------------------------------------------------------ #
    u = mda.Universe(str(topology_pdb), str(trajectory_dcd))
    n_total = len(u.trajectory)
    if n_total == 0:
        raise RuntimeError("Trajectory has no frames.")

    # Sample frames uniformly; skip the first 10 % as burn-in
    burn_in = max(1, n_total // 10)
    sampled_indices = _uniform_sample(list(range(burn_in, n_total)), options.n_frames)
    print(
        f"[MMGBSA] Sampling {len(sampled_indices)} frames "
        f"from {n_total} total (burn-in: {burn_in})."
    )

    # ------------------------------------------------------------------ #
    # PBC correction: center protein in box, wrap ligand into same image  #
    # ------------------------------------------------------------------ #
    # Without this, the ligand can sit in a periodic image 40+ Å from the
    # protein, making all energy differences artefacts of solvation geometry.
    _prot_sel = u.select_atoms("protein")
    _lig_sel = u.select_atoms("resname LIG")
    if len(_lig_sel) == 0:
        _lig_sel = u.select_atoms(
            "not protein and not resname HOH WAT SOL NA CL MG CA ZN"
        )
    if len(_prot_sel) > 0 and len(_lig_sel) > 0 and u.dimensions is not None:
        from MDAnalysis.transformations import unwrap, center_in_box, wrap
        u.trajectory.add_transformations(
            unwrap(_prot_sel | _lig_sel),
            center_in_box(_prot_sel),
            wrap(_lig_sel, compound="residues"),
        )

    # ------------------------------------------------------------------ #
    # Build implicit-solvent force field for complex, protein, ligand    #
    # ------------------------------------------------------------------ #
    ff_complex, ff_protein, ff_ligand, strip_indices = _build_implicit_ff(
        topology_pdb, options
    )

    # ------------------------------------------------------------------ #
    # Evaluate energies per frame                                        #
    # ------------------------------------------------------------------ #
    e_complex: list[float] = []
    e_protein: list[float] = []
    e_ligand: list[float] = []

    for idx in sampled_indices:
        u.trajectory[idx]
        positions = u.atoms.positions  # (N, 3) in Angstroms

        ec = _eval_energy_kj(ff_complex["sim"], positions, strip_indices["complex"])
        ep = _eval_energy_kj(ff_protein["sim"], positions, strip_indices["protein"])
        el = _eval_energy_kj(ff_ligand["sim"], positions, strip_indices["ligand"])

        e_complex.append(ec)
        e_protein.append(ep)
        e_ligand.append(el)

    ddg_frames = [
        ec - ep - el for ec, ep, el in zip(e_complex, e_protein, e_ligand)
    ]

    mean_ddg = float(np.mean(ddg_frames))
    std_ddg = float(np.std(ddg_frames))
    mean_ec = float(np.mean(e_complex))
    mean_ep = float(np.mean(e_protein))
    mean_el = float(np.mean(e_ligand))

    print(
        f"[MMGBSA] ΔG_bind ≈ {mean_ddg:.2f} ± {std_ddg:.2f} kJ/mol  "
        f"(complex: {mean_ec:.1f}, protein: {mean_ep:.1f}, ligand: {mean_el:.1f})"
    )

    # ------------------------------------------------------------------ #
    # Write per-frame energies                                           #
    # ------------------------------------------------------------------ #
    frames_json = output_dir / "mmgbsa_frames.json"
    frames_data = [
        {
            "frame_index": idx,
            "e_complex_kj": ec,
            "e_protein_kj": ep,
            "e_ligand_kj": el,
            "ddg_kj": ec - ep - el,
        }
        for idx, ec, ep, el in zip(sampled_indices, e_complex, e_protein, e_ligand)
    ]
    frames_json.write_text(json.dumps(frames_data, indent=2) + "\n")

    # ------------------------------------------------------------------ #
    # Record                                                             #
    # ------------------------------------------------------------------ #
    from openmm import version as _ov

    record = MmgbsaRecord(
        topology_pdb=str(topology_pdb.resolve()),
        trajectory_dcd=str(trajectory_dcd.resolve()),
        frames_json=str(frames_json),
        output_dir=str(output_dir),
        metadata_path=str(output_dir / "mmgbsa_record.json"),
        n_frames_sampled=len(sampled_indices),
        mean_ddg_kj=mean_ddg,
        std_ddg_kj=std_ddg,
        mean_ddg_kcal=mean_ddg / 4.184,
        std_ddg_kcal=std_ddg / 4.184,
        mean_e_complex_kj=mean_ec,
        mean_e_protein_kj=mean_ep,
        mean_e_ligand_kj=mean_el,
        options=options,
        tool_versions={"openmm": str(_ov.full_version)},
        created_at=datetime.now(timezone.utc),
    )
    (output_dir / "mmgbsa_record.json").write_text(
        json.dumps(record.model_dump(mode="json"), indent=2) + "\n"
    )
    return record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_stack() -> None:
    try:
        import openmm  # noqa: F401
        import MDAnalysis  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "MMGBSA requires: openmm MDAnalysis. Install via conda-forge. "
            f"Missing: {exc.name}"
        ) from exc


def _uniform_sample(indices: list[int], n: int) -> list[int]:
    import numpy as np
    if len(indices) <= n:
        return indices
    chosen = np.linspace(0, len(indices) - 1, n, dtype=int)
    return [indices[i] for i in chosen]


def _build_implicit_ff(topology_pdb: Path, options: "MmgbsaOptions") -> tuple:
    """Build one OpenMM Simulation per component (complex/protein/ligand)
    using GB-OBC2 implicit solvent.

    Returns (complex_dict, protein_dict, ligand_dict, strip_indices).
    strip_indices contains the atom index arrays for each component used to
    slice the full position array.
    """
    from openmm import LangevinMiddleIntegrator, Platform, unit
    from openmm.app import ForceField, Modeller, NoCutoff, PDBFile, Simulation
    from openff.toolkit import Molecule, Topology as OFFTopology
    from openmmforcefields.generators import SMIRNOFFTemplateGenerator
    import MDAnalysis as mda
    import numpy as np

    # Identify ligand SMILES: check topology PDB REMARK, then prep_record.json
    ligand_smiles = _smiles_from_pdb_remark(topology_pdb)
    if not ligand_smiles:
        prep_record_json = topology_pdb.parent / "prep_record.json"
        if prep_record_json.exists():
            try:
                import json as _json
                pr = _json.loads(prep_record_json.read_text())
                ligand_smiles = pr.get("ligand_smiles", "")
            except Exception:
                pass

    # Load with MDAnalysis to categorise atoms
    u = mda.Universe(str(topology_pdb))
    protein_mask = u.select_atoms("protein").indices
    lig_mask = u.select_atoms("resname LIG").indices
    if len(lig_mask) == 0:
        lig_mask = u.select_atoms(
            "not protein and not resname HOH WAT SOL NA CL MG CA ZN"
        ).indices
    complex_mask = np.concatenate([protein_mask, lig_mask])

    strip_indices = {
        "complex": complex_mask,
        "protein": protein_mask,
        "ligand": lig_mask,
    }

    # Build forcefields
    ff_base = ForceField("amber14-all.xml", "implicit/obc2.xml")
    if ligand_smiles:
        try:
            offmol = Molecule.from_smiles(ligand_smiles, allow_undefined_stereo=True)
            offmol.assign_partial_charges("gasteiger")
            smirnoff = SMIRNOFFTemplateGenerator(
                molecules=[offmol], forcefield=options.smirnoff_forcefield
            )
            ff_base.registerTemplateGenerator(smirnoff.generator)
        except Exception as exc:
            print(f"[MMGBSA] SMIRNOFF registration failed ({exc}); using generic forcefield.")

    pdb = PDBFile(str(topology_pdb))
    integrator = LangevinMiddleIntegrator(
        300 * unit.kelvin, 1.0 / unit.picosecond, 0.002 * unit.picoseconds
    )

    platform, platform_properties = openmm_platform_from_env(Platform)

    # Build simulation objects per component
    result: dict[str, dict] = {}
    for component, mask in [
        ("complex", complex_mask),
        ("protein", protein_mask),
        ("ligand", lig_mask),
    ]:
        # Extract topology for this component
        all_atoms = list(pdb.topology.atoms())
        keep_atoms = {int(i) for i in mask}
        modeller = Modeller(pdb.topology, pdb.positions)
        to_delete = [
            a for a in modeller.topology.atoms() if a.index not in keep_atoms
        ]
        modeller.delete(to_delete)

        system = ff_base.createSystem(
            modeller.topology,
            nonbondedMethod=NoCutoff,
        )
        integ = LangevinMiddleIntegrator(
            300 * unit.kelvin, 1.0 / unit.picosecond, 0.002 * unit.picoseconds
        )
        if platform is None:
            sim = Simulation(modeller.topology, system, integ)
        else:
            sim = Simulation(modeller.topology, system, integ, platform, platform_properties)
        result[component] = {"sim": sim, "topology": modeller.topology}

    return (
        result["complex"],
        result["protein"],
        result["ligand"],
        strip_indices,
    )


def _eval_energy_kj(sim, all_positions_angstrom, atom_indices) -> float:
    """Set positions for ``atom_indices`` subset and return potential energy in kJ/mol."""
    from openmm import unit
    import numpy as np

    positions_nm = all_positions_angstrom[atom_indices] / 10.0  # Å → nm
    omm_positions = [
        (float(p[0]), float(p[1]), float(p[2])) * unit.nanometer
        for p in positions_nm
    ]
    sim.context.setPositions(omm_positions)
    state = sim.context.getState(getEnergy=True)
    return state.getPotentialEnergy().value_in_unit(unit.kilojoules_per_mole)


def _smiles_from_pdb_remark(pdb_path: Path) -> str | None:
    for line in pdb_path.read_text().splitlines():
        if line.startswith("REMARK") and "SMILES" in line:
            parts = line.split(None, 2)
            if len(parts) >= 3:
                return parts[2].strip()
    return None
