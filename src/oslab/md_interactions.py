"""
ProLIF protein-ligand interaction fingerprinting on MD trajectories.

Runs ProLIF over an MDAnalysis trajectory to compute per-residue interaction
occupancies (H-bond donor/acceptor, hydrophobic, pi-stacking, etc.).  Results
are compared to any static PLIP analysis if one is available.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .schemas import MdInteractionsRecord


def analyze_trajectory(
    topology_pdb: Path,
    trajectory_dcd: Path,
    output_dir: Path,
    plip_interaction_json: Path | None = None,
    step: int = 1,
) -> MdInteractionsRecord:
    """Run ProLIF fingerprinting over a DCD trajectory.

    Parameters
    ----------
    topology_pdb:
        PDB topology file (from ``prepare_md_system`` or ``run_md`` final frame).
    trajectory_dcd:
        DCD trajectory from ``run_md``.
    output_dir:
        Directory where results are written.
    plip_interaction_json:
        Optional path to a static PLIP ``interaction_summary.json`` for
        comparison.
    step:
        Analyse every ``step``-th frame to reduce compute; default 1 (all frames).

    Returns
    -------
    MdInteractionsRecord (also written to output_dir/md_interactions_record.json).
    """
    _require_prolif()
    topology_pdb = Path(topology_pdb)
    trajectory_dcd = Path(trajectory_dcd)
    output_dir = Path(output_dir)
    plip_interaction_json = Path(plip_interaction_json) if plip_interaction_json is not None else None
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    import MDAnalysis as mda
    import prolif as plf
    import numpy as np

    # ------------------------------------------------------------------ #
    # Load trajectory                                                     #
    # ------------------------------------------------------------------ #
    u = mda.Universe(str(topology_pdb), str(trajectory_dcd))

    # Select protein and ligand
    protein_sel = u.select_atoms("protein")
    ligand_sel = u.select_atoms("resname LIG")
    if len(ligand_sel) == 0:
        # Fallback: anything that isn't protein/water/ion
        ligand_sel = u.select_atoms(
            "not protein and not resname HOH WAT SOL NA CL MG CA ZN"
        )

    if len(protein_sel) == 0 or len(ligand_sel) == 0:
        raise RuntimeError(
            "Cannot identify protein or ligand residues in the trajectory topology. "
            "Check that the topology PDB contains 'protein' atoms and a 'LIG' residue."
        )

    # Guess bonds if not present (OpenMM PDB output doesn't write CONECT records)
    if not hasattr(u, "bonds") or len(u.bonds) == 0:
        protein_sel.guess_bonds()
        ligand_sel.guess_bonds()

    # Add on-the-fly PBC correction:
    # 1. unwrap — re-join any protein/ligand fragments split across the box boundary
    # 2. center_in_box(protein) — put the cropped receptor (and its binding pocket) at box centre
    # 3. wrap(ligand, compound='residues') — move the ligand as a rigid unit into that same image
    # center_in_box on the full complex is wrong here because the protein centroid dominates,
    # leaving a small ligand stranded on the opposite side of the box.
    from MDAnalysis.transformations import unwrap, center_in_box, wrap
    u.trajectory.add_transformations(
        unwrap(protein_sel | ligand_sel),
        center_in_box(protein_sel),
        wrap(ligand_sel, compound="residues"),
    )

    # ------------------------------------------------------------------ #
    # Run ProLIF                                                          #
    # ------------------------------------------------------------------ #
    prot_mol = plf.Molecule.from_mda(protein_sel)
    fp = plf.Fingerprint(
        interactions=[
            "HBDonor", "HBAcceptor",
            "Hydrophobic",
            "PiStacking", "PiCation",
            "CationPi", "Anionic", "Cationic",
            "VdWContact",
        ],
        count=False,
    )
    fp.run(u.trajectory[::step], ligand_sel, protein_sel)

    # ------------------------------------------------------------------ #
    # Compute occupancies                                                 #
    # ------------------------------------------------------------------ #
    df = fp.to_dataframe()
    n_frames = len(df)
    occupancies: list[dict] = []
    if n_frames > 0 and len(df.columns) > 0:
        # ProLIF 2.x columns are tuples (ligand_resid, protein_resid, interaction)
        mean_occ = df.mean()
        for col_key, occ_val in mean_occ.items():
            if float(occ_val) > 0:
                # col_key may be a tuple (lig, res, interaction) or a string
                if isinstance(col_key, tuple) and len(col_key) == 3:
                    _, res, interaction = col_key
                else:
                    res, interaction = str(col_key), "Unknown"
                occupancies.append(
                    {
                        "residue": str(res),
                        "interaction": str(interaction),
                        "occupancy": round(float(occ_val), 4),
                    }
                )
        occupancies.sort(key=lambda r: -r["occupancy"])

    # ------------------------------------------------------------------ #
    # Save fingerprint dataframe                                         #
    # ------------------------------------------------------------------ #
    fingerprint_csv = output_dir / "fingerprint.csv"
    df.to_csv(str(fingerprint_csv))

    occupancy_json = output_dir / "occupancy.json"
    occupancy_json.write_text(json.dumps(occupancies, indent=2) + "\n")

    # ------------------------------------------------------------------ #
    # Compare with PLIP static analysis                                  #
    # ------------------------------------------------------------------ #
    comparison: list[dict] | None = None
    if plip_interaction_json and plip_interaction_json.exists():
        comparison = _compare_with_plip(occupancies, plip_interaction_json)
        (output_dir / "plip_comparison.json").write_text(
            json.dumps(comparison, indent=2) + "\n"
        )

    # ------------------------------------------------------------------ #
    # Write record                                                        #
    # ------------------------------------------------------------------ #
    import prolif as plf_version

    record = MdInteractionsRecord(
        topology_pdb=str(topology_pdb.resolve()),
        trajectory_dcd=str(trajectory_dcd.resolve()),
        fingerprint_csv=str(fingerprint_csv),
        occupancy_json=str(occupancy_json),
        plip_comparison_json=str(output_dir / "plip_comparison.json") if comparison is not None else None,
        n_frames_analyzed=n_frames,
        step=step,
        top_interactions=occupancies[:20],
        output_dir=str(output_dir),
        metadata_path=str(output_dir / "md_interactions_record.json"),
        tool_versions={"prolif": plf_version.__version__},
        created_at=datetime.now(timezone.utc),
    )
    (output_dir / "md_interactions_record.json").write_text(
        json.dumps(record.model_dump(mode="json"), indent=2) + "\n"
    )
    return record


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_prolif() -> None:
    try:
        import prolif  # noqa: F401
        import MDAnalysis  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "ProLIF trajectory analysis requires: prolif MDAnalysis. "
            f"Install via conda-forge.  Missing: {exc.name}"
        ) from exc


def _compare_with_plip(
    occupancies: list[dict],
    plip_json: Path,
) -> list[dict]:
    """Align ProLIF occupancies with PLIP static interactions for comparison.

    Maps PLIP interaction types to ProLIF equivalents where possible.
    """
    plip_type_map = {
        "hbond": ("HBDonor", "HBAcceptor"),
        "hydrophobic_interaction": ("Hydrophobic",),
        "pi_stacking": ("PiStacking",),
        "pi_cation_interaction": ("PiCation", "CationPi"),
        "salt_bridge": ("Cationic", "Anionic"),
    }

    plip_rows = json.loads(plip_json.read_text())
    # Build set of (residue_number, interaction_group) from PLIP
    plip_set: set[tuple[str, str]] = set()
    for row in plip_rows:
        resnr = str(row.get("residue_number", ""))
        itype = row.get("interaction_type", "").lower()
        for plip_key, prolif_types in plip_type_map.items():
            if plip_key in itype:
                for pt in prolif_types:
                    plip_set.add((resnr, pt))

    # Compare
    comparison = []
    for occ in occupancies:
        residue_nr = "".join(ch for ch in occ["residue"] if ch.isdigit())
        in_plip = (residue_nr, occ["interaction"]) in plip_set
        comparison.append(
            {
                "residue": occ["residue"],
                "interaction": occ["interaction"],
                "md_occupancy": occ["occupancy"],
                "in_plip_static": in_plip,
            }
        )
    return comparison
