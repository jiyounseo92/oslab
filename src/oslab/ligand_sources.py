from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


PrepRequirement = Literal["none", "recommended", "required"]


@dataclass(frozen=True)
class LigandSource:
    key: str
    name: str
    source_type: str
    molecule_count: str
    typical_size: str
    drug_like_filtering: str
    formats: tuple[str, ...]
    vina_ready: bool
    rdkit_meeko_prep: PrepRequirement
    best_for: str
    caveats: str
    url: str

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["formats"] = list(self.formats)
        return data


LIGAND_SOURCES: dict[str, LigandSource] = {
    "zinc3d-pdbqt": LigandSource(
        key="zinc3d-pdbqt",
        name="ZINC tranche files (SMILES/PDBQT)",
        source_type="public purchasable compound database",
        molecule_count="subset-dependent; ZINC22 reports billions of tangible compounds and >4.5B built in ready-to-dock 3D formats",
        typical_size="selectable tranches by heavy atom count, logP/polarity, charge, pH, reactivity, purchasability",
        drug_like_filtering="user-selectable; common picks are fragment-like, lead-like, and drug-like tranches",
        formats=("pdbqt", "sdf", "mol2", "db2", "smi"),
        vina_ready=True,
        rdkit_meeko_prep="none",
        best_for="first-pass screens with purchasable compounds; use PDBQT tranches when available to skip local ligand prep",
        caveats="download filtered subsets; major redistribution is restricted; quality still depends on chosen tranche and target",
        url="https://cache.docking.org/3D/",
    ),
    "virtualflow-enamine-real": LigandSource(
        key="virtualflow-enamine-real",
        name="VirtualFlow / Enamine REAL Ready-to-Dock",
        source_type="ready-to-dock make-on-demand commercial library",
        molecule_count="over 1.4B molecules reported for the ready-to-dock VirtualFlow REAL library",
        typical_size="very large make-on-demand chemical space; use focused subsets",
        drug_like_filtering="VirtualFlow subset selection; depends on chosen REAL subset and filters",
        formats=("pdbqt",),
        vina_ready=True,
        rdkit_meeko_prep="none",
        best_for="large-scale screens after the pipeline is validated on smaller libraries",
        caveats="too large for a first local test; storage and scheduling need planning",
        url="https://virtual-flow.org/real-library",
    ),
    "enamine-sdf": LigandSource(
        key="enamine-sdf",
        name="Enamine Catalogs",
        source_type="commercial purchasable compound catalogs",
        molecule_count="catalog/subset-dependent",
        typical_size="fragments, lead-like sets, focused libraries, and REAL compounds depending on catalog",
        drug_like_filtering="often available as curated subsets, but verify per catalog",
        formats=("sdf", "smi", "csv"),
        vina_ready=False,
        rdkit_meeko_prep="required",
        best_for="commercial hit follow-up and focused purchasable screens",
        caveats="prepare locally for consistent protonation, stereochemistry, conformers, and PDBQT atom typing",
        url="https://enamine.net/compound-collections",
    ),
    "chembl": LigandSource(
        key="chembl",
        name="ChEMBL",
        source_type="public bioactivity database",
        molecule_count="millions of bioactive molecules; exact count changes with each ChEMBL release",
        typical_size="bioactive drug-like and probe-like compounds with target/activity annotations",
        drug_like_filtering="not uniformly drug-like; filter by assay confidence, activity, PAINS/reactivity, size, and properties",
        formats=("sdf", "smi", "csv"),
        vina_ready=False,
        rdkit_meeko_prep="required",
        best_for="known actives, controls, target-family enrichment, and repurposing sets",
        caveats="bioactivity annotations require curation; structures need standardization before docking",
        url="https://www.ebi.ac.uk/chembl/",
    ),
    "pubchem": LigandSource(
        key="pubchem",
        name="PubChem",
        source_type="public chemical structure database",
        molecule_count="very large public database; exact compound/substance counts change continuously",
        typical_size="broad chemical space, not necessarily purchasable or drug-like",
        drug_like_filtering="not guaranteed; must filter locally",
        formats=("sdf", "smi", "json", "csv"),
        vina_ready=False,
        rdkit_meeko_prep="required",
        best_for="broad lookup, literature compounds, and custom user-selected compounds",
        caveats="requires more aggressive filtering and provenance tracking than ZINC/Enamine",
        url="https://pubchem.ncbi.nlm.nih.gov/",
    ),
    "pdb-native-ligands": LigandSource(
        key="pdb-native-ligands",
        name="PDB Native Ligands",
        source_type="ligands extracted from experimental protein-ligand structures",
        molecule_count="target-dependent",
        typical_size="co-crystallized ligands, cofactors, fragments, ions, and crystallization additives",
        drug_like_filtering="not guaranteed; includes non-drug cofactors, buffers, fragments, and artifacts",
        formats=("cif", "pdb", "sdf"),
        vina_ready=False,
        rdkit_meeko_prep="required",
        best_for="redocking validation, binding-site definition, and positive controls",
        caveats="must separate true ligands from waters, ions, cofactors, and crystallization artifacts",
        url="https://www.rcsb.org/",
    ),
    "custom-sdf": LigandSource(
        key="custom-sdf",
        name="Custom SMILES/SDF Library",
        source_type="user-supplied molecules",
        molecule_count="user-defined",
        typical_size="user-defined",
        drug_like_filtering="user-defined; local RDKit filters recommended",
        formats=("sdf", "smi", "csv"),
        vina_ready=False,
        rdkit_meeko_prep="required",
        best_for="user compounds, purchased hits, focused medicinal chemistry sets",
        caveats="all chemistry assumptions should be recorded in the workflow manifest",
        url="",
    ),
    "custom-pdbqt": LigandSource(
        key="custom-pdbqt",
        name="Custom Vina-Ready PDBQT Library",
        source_type="user-supplied prepared molecules",
        molecule_count="user-defined",
        typical_size="user-defined",
        drug_like_filtering="user-defined",
        formats=("pdbqt",),
        vina_ready=True,
        rdkit_meeko_prep="recommended",
        best_for="preprepared Vina libraries from trusted workflows",
        caveats="skip prep only when provenance and preparation parameters are trusted",
        url="",
    ),
}


def get_ligand_source(key: str) -> LigandSource:
    try:
        return LIGAND_SOURCES[key]
    except KeyError as exc:
        choices = ", ".join(sorted(LIGAND_SOURCES))
        raise ValueError(f"unknown ligand source '{key}'. Available sources: {choices}") from exc


def ligand_source_rows() -> list[dict[str, object]]:
    return [source.to_dict() for source in LIGAND_SOURCES.values()]
