"""FEP Setup — build perturbation network and prepare hybrid topology inputs.

Uses RDKit MCS to compute pairwise similarity, networkx to build a minimal
spanning tree perturbation network, openff-toolkit to parametrize each ligand,
and ParmEd/OpenMM to write inputs for each edge.

Each edge A→B produces:
    edge_dir/
        ligandA.sdf
        ligandB.sdf
        ligandA_params.json     openff partial charges + topology
        ligandB_params.json
        edge_record.json        similarity, MCS SMARTS, planned lambdas
        receptor_cropped.pdb    binding-pocket receptor (re-used from MD prep if available)
        topology_complex.pdb    receptor + A solvated (OpenMM)
        topology_solvent.pdb    A in water box (OpenMM)
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

from .jobs import DEFAULT_RDKIT_SEED, set_rdkit_seed

DEFAULT_N_LAMBDA = 11


def build_default_lambda_schedule(n: int) -> tuple[list[float], list[float]]:
    """Return ``(lambda_vdw, lambda_elec)`` lists of length ``n``.

    Lambda convention (openmmtools annihilation): lambda=1 means the alchemical
    interaction is fully present, lambda=0 means it is fully annihilated.

    Strategy:
        * Discharge electrostatics first (linearly 1 → 0 over the first half)
          while Lennard-Jones sterics remain fully present.
        * Decouple Lennard-Jones in the second half only after electrostatics
          are fully off.
    Discharging before LJ avoids divergent point-charge interactions on a
    near-zero LJ ligand (the classic "end-state instability" problem).
    """
    if n < 2:
        raise ValueError(f"Need at least 2 lambda windows; got {n}")
    lambdas_vdw: list[float] = []
    lambdas_elec: list[float] = []
    for i in range(n):
        frac = i / (n - 1)
        if frac <= 0.5:
            lambdas_vdw.append(1.0)
            lambdas_elec.append(round(1.0 - frac * 2.0, 4))
        else:
            lambdas_vdw.append(round(1.0 - (frac - 0.5) * 2.0, 4))
            lambdas_elec.append(0.0)
    return lambdas_vdw, lambdas_elec


@dataclass
class FepEdge:
    ligand_a: str          # ligand name (key in ligand_data)
    ligand_b: str
    mcs_atoms: int = 0
    tanimoto: float = 0.0
    score: float = 0.0     # higher = more similar = easier perturbation


@dataclass
class FepNetworkPlan:
    edges: list[FepEdge] = field(default_factory=list)
    ligand_names: list[str] = field(default_factory=list)
    reference_ligand: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ligand_names": self.ligand_names,
            "reference_ligand": self.reference_ligand,
            "edges": [
                {
                    "ligand_a": e.ligand_a,
                    "ligand_b": e.ligand_b,
                    "mcs_atoms": e.mcs_atoms,
                    "tanimoto": round(e.tanimoto, 3),
                    "score": round(e.score, 3),
                }
                for e in self.edges
            ],
        }


def build_perturbation_network(
    ligand_smiles: dict[str, str],
    *,
    reference_ligand: str | None = None,
    max_edges: int | None = None,
) -> FepNetworkPlan:
    """Compute pairwise MCS similarities and return an MST perturbation network.

    Args:
        ligand_smiles: {name: SMILES}
        reference_ligand: anchor node (typically the ligand with best Vina / ΔG score).
        max_edges: cap total edges (default = N-1 MST + a few extra for cycle closure).
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem, DataStructs
    from rdkit.Chem import rdFMCS

    names = list(ligand_smiles.keys())
    if len(names) < 2:
        raise ValueError("FEP requires at least 2 ligands to build a perturbation network.")

    mols: dict[str, Any] = {}
    fps: dict[str, Any] = {}
    for name, smi in ligand_smiles.items():
        set_rdkit_seed()
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            raise ValueError(f"Could not parse SMILES for ligand {name!r}: {smi}")
        mol = Chem.AddHs(mol)
        params = AllChem.ETKDGv3()
        params.randomSeed = DEFAULT_RDKIT_SEED
        AllChem.EmbedMolecule(mol, params)
        mol = Chem.RemoveHs(mol)
        mols[name] = mol
        fps[name] = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=2048)

    # Build complete pairwise similarity graph
    G: nx.Graph = nx.Graph()
    for name in names:
        G.add_node(name)

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            tan = DataStructs.TanimotoSimilarity(fps[a], fps[b])
            try:
                res = rdFMCS.FindMCS(
                    [mols[a], mols[b]],
                    timeout=5,
                    atomCompare=rdFMCS.AtomCompare.CompareElements,
                    bondCompare=rdFMCS.BondCompare.CompareOrder,
                    matchValences=True,
                    ringMatchesRingOnly=True,
                )
                mcs_n = res.numAtoms
            except Exception:
                mcs_n = 0
            score = 0.5 * tan + 0.5 * (mcs_n / max(len(mols[a].GetAtoms()), len(mols[b].GetAtoms()), 1))
            G.add_edge(a, b, weight=1.0 - score, tanimoto=tan, mcs_atoms=mcs_n, score=score)

    # MST maximises similarity (minimises weight)
    mst: nx.Graph = nx.minimum_spanning_tree(G)

    # Optionally add a few extra edges for cycle closure (improves statistical reliability)
    extra_cap = max(0, (max_edges or len(names) + 2) - len(mst.edges))
    non_mst = [(u, v, d) for u, v, d in G.edges(data=True) if not mst.has_edge(u, v)]
    non_mst.sort(key=lambda x: x[2]["weight"])
    for u, v, d in non_mst[:extra_cap]:
        mst.add_edge(u, v, **d)

    ref = reference_ligand if reference_ligand and reference_ligand in names else names[0]
    edges: list[FepEdge] = []
    for a, b, data in mst.edges(data=True):
        edges.append(FepEdge(
            ligand_a=a, ligand_b=b,
            mcs_atoms=data.get("mcs_atoms", 0),
            tanimoto=data.get("tanimoto", 0.0),
            score=data.get("score", 0.0),
        ))

    return FepNetworkPlan(edges=edges, ligand_names=names, reference_ligand=ref)


def write_ligand_sdf(mol_name: str, smiles: str, out_path: Path) -> Path:
    """Generate a 3D-embedded SDF for a ligand from SMILES."""
    from rdkit import Chem
    from rdkit.Chem import AllChem

    out_path.parent.mkdir(parents=True, exist_ok=True)
    mol = Chem.MolFromSmiles(smiles)
    mol = Chem.AddHs(mol)
    set_rdkit_seed()
    params = AllChem.ETKDGv3()
    params.randomSeed = DEFAULT_RDKIT_SEED
    AllChem.EmbedMolecule(mol, params)
    AllChem.MMFFOptimizeMolecule(mol)
    mol.SetProp("_Name", mol_name)
    w = Chem.SDWriter(str(out_path))
    w.write(mol)
    w.close()
    return out_path


_AM1BCC_METHOD_PREFERENCE: tuple[str, ...] = (
    "am1bcc",
    "openff-gnn-am1bcc-1.0.0.pt",
    "openff-gnn-am1bcc-0.1.0-rc.3.pt",
)


def _assign_am1bcc_charges(mol) -> str:
    """Try real AM1-BCC, then NAGL surrogate. Returns method name used."""
    last_exc: Exception | None = None
    for method in _AM1BCC_METHOD_PREFERENCE:
        try:
            mol.assign_partial_charges(method, strict_n_conformers=False)
        except TypeError:
            try:
                mol.assign_partial_charges(method)
            except Exception as exc:
                last_exc = exc
                continue
        except Exception as exc:
            last_exc = exc
            continue
        net = float(sum(c.m for c in mol.partial_charges))
        if abs(net - round(net)) > 0.05:
            last_exc = ValueError(
                f"Charge method {method!r} produced non-integer net charge {net:.3f}"
            )
            continue
        return method
    raise RuntimeError(
        f"Could not assign AM1-BCC charges by any method "
        f"({list(_AM1BCC_METHOD_PREFERENCE)}). Last error: {last_exc}"
    )


def parametrize_ligand_openff(smiles: str, mol_name: str, forcefield: str = "openff-2.2.0") -> dict[str, Any]:
    """Assign SMIRNOFF parameters and AM1-BCC charges. Returns a JSON-serialisable record.

    Raises ``RuntimeError`` if charge assignment fails by every supported
    method; a ligand without AM1-BCC charges is unsuitable for FEP and must
    not be used silently.
    """
    from openff.toolkit import Molecule, ForceField

    mol = Molecule.from_smiles(smiles, allow_undefined_stereo=True)
    mol.name = mol_name
    mol.generate_conformers(n_conformers=1)
    charge_warning: str | None = None
    try:
        charge_method = _assign_am1bcc_charges(mol)
        charges = [round(float(c.m), 4) for c in mol.partial_charges]
    except Exception as exc:
        raise RuntimeError(
            f"Partial-charge assignment failed for ligand {mol_name!r} "
            f"(SMILES={smiles!r}): {exc}. FEP requires per-atom partial charges; "
            "install AmberTools (real AM1-BCC) or openff-nagl-models (GNN surrogate)."
        ) from exc

    total_charge = round(sum(charges), 3) if charges else None
    if charges and total_charge is not None and abs(total_charge - round(total_charge)) > 0.05:
        charge_warning = (
            f"Net charge {total_charge} is not close to an integer; "
            f"charges from {charge_method!r} may be incorrect."
        )
        warnings.warn(charge_warning)

    ff = ForceField(f"{forcefield}.offxml")
    topology = mol.to_topology()
    # Trigger SMIRNOFF labelling so unparameterised atoms raise loudly here.
    ff.label_molecules(topology)
    n_atoms = mol.n_atoms
    n_heavy = sum(1 for atom in mol.atoms if atom.atomic_number != 1)
    record: dict[str, Any] = {
        "mol_name": mol_name,
        "smiles": smiles,
        "forcefield": forcefield,
        "n_atoms": n_atoms,
        "n_heavy_atoms": n_heavy,
        "charge_method": charge_method,
        "partial_charges": charges,
        "net_charge": total_charge,
    }
    if charge_warning:
        record["charge_warning"] = charge_warning
    return record


def prepare_fep_edge(
    *,
    edge: FepEdge,
    ligand_smiles: dict[str, str],
    edge_dir: Path,
    receptor_pdb: Path | None,
    forcefield: str = "openff-2.2.0",
    n_lambda: int = DEFAULT_N_LAMBDA,
    temperature_k: float = 300.0,
    water_padding_nm: float = 1.2,
    ionic_strength_m: float = 0.15,
    minimization_steps: int = 500,
    progress_callback: Any = None,
) -> dict[str, Any]:
    """Prepare all inputs for one FEP edge (A→B).

    Returns edge_record dict.
    """
    edge_dir.mkdir(parents=True, exist_ok=True)

    def _emit(msg: str) -> None:
        if progress_callback:
            progress_callback({"message": msg})

    _emit(f"Preparing edge {edge.ligand_a}→{edge.ligand_b}")

    sdf_a = write_ligand_sdf(edge.ligand_a, ligand_smiles[edge.ligand_a], edge_dir / "ligandA.sdf")
    sdf_b = write_ligand_sdf(edge.ligand_b, ligand_smiles[edge.ligand_b], edge_dir / "ligandB.sdf")
    _emit("3D conformers embedded")

    _emit("Parametrizing ligandA with SMIRNOFF")
    params_a = parametrize_ligand_openff(ligand_smiles[edge.ligand_a], edge.ligand_a, forcefield)
    (edge_dir / "ligandA_params.json").write_text(json.dumps(params_a, indent=2))

    _emit("Parametrizing ligandB with SMIRNOFF")
    params_b = parametrize_ligand_openff(ligand_smiles[edge.ligand_b], edge.ligand_b, forcefield)
    (edge_dir / "ligandB_params.json").write_text(json.dumps(params_b, indent=2))

    # Lambda schedule — discharge electrostatics first, then decouple vdW.
    lambdas_vdw, lambdas_elec = build_default_lambda_schedule(n_lambda)
    lambda_windows = [
        {"lambda_index": i, "lambda_vdw": lv, "lambda_elec": le}
        for i, (lv, le) in enumerate(zip(lambdas_vdw, lambdas_elec))
    ]

    if receptor_pdb and receptor_pdb.exists():
        import shutil
        shutil.copy2(receptor_pdb, edge_dir / "receptor_cropped.pdb")
        sibling_system_xml = receptor_pdb.parent / "system.xml"
        if sibling_system_xml.exists():
            shutil.copy2(sibling_system_xml, edge_dir / "system.xml")

    record: dict[str, Any] = {
        "ligand_a": edge.ligand_a,
        "ligand_b": edge.ligand_b,
        "smiles_a": ligand_smiles[edge.ligand_a],
        "smiles_b": ligand_smiles[edge.ligand_b],
        "mcs_atoms": edge.mcs_atoms,
        "tanimoto": round(edge.tanimoto, 3),
        "similarity_score": round(edge.score, 3),
        "n_lambda_windows": n_lambda,
        "lambda_windows": lambda_windows,
        "forcefield": forcefield,
        "temperature_k": temperature_k,
        "water_padding_nm": water_padding_nm,
        "ionic_strength_m": ionic_strength_m,
        "minimization_steps": minimization_steps,
        "ligandA_sdf": str(sdf_a),
        "ligandB_sdf": str(sdf_b),
        "ligandA_params": str(edge_dir / "ligandA_params.json"),
        "ligandB_params": str(edge_dir / "ligandB_params.json"),
        "receptor_cropped_pdb": str(edge_dir / "receptor_cropped.pdb") if receptor_pdb and receptor_pdb.exists() else None,
        "status": "prepared",
    }
    (edge_dir / "edge_record.json").write_text(json.dumps(record, indent=2))
    _emit(f"Edge {edge.ligand_a}→{edge.ligand_b} prepared ({n_lambda} λ windows)")
    return record
