"""Automated analog library generation for FEP campaigns.

Given a parent ligand SMILES, enumerates analogs by R-group substitution,
filters them for druglikeness / synthesizability / novelty, and returns a
curated set ready for relative free-energy perturbation simulations.

Pipeline:
    1. rdMMPA single- and double-cut decomposition produces (core, R-group)
       SMILES pairs with [*:N] dummy atoms marking the cut sites.
    2. For each cut, every dummy slot is replaced with each substituent
       from the curated library (~30 drug-like groups).
    3. Filter cascade:
        * RDKit QED ≥ 0.3 (druglikeness)
        * Lipinski-style: MW 200–500, logP −1..5, HBD ≤ 5, HBA ≤ 10, TPSA ≤ 140
        * No PAINS / Brenk / NIH catalogue alerts
        * Tanimoto to parent in [min_similarity, max_similarity] —
          drops both trivial duplicates and full-scaffold-hops
        * Optional SAScore < max_sa_score when the Contrib module is present
    4. Records are ranked by a composite score that prefers analogs near
       Tanimoto ≈ 0.7 to the parent (sweet spot for FEP edge similarity).

Only RDKit is required; the optional SAScore Contrib module is used if
importable.
"""
from __future__ import annotations

import json
import math
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Curated substituent library
#
# Each entry is (smiles_with_dummy, label). The dummy atom carries map
# number 1; molzip uses the map number to attach the substituent to the
# corresponding [*:1] in the scaffold core.
# ---------------------------------------------------------------------------
DEFAULT_SUBSTITUENTS: list[tuple[str, str]] = [
    # Hydrogen / small alkyl
    ("[*:1][H]", "H"),
    ("[*:1]C", "Me"),
    ("[*:1]CC", "Et"),
    ("[*:1]C(C)C", "iPr"),
    ("[*:1]C(C)(C)C", "tBu"),
    ("[*:1]CC(C)C", "iBu"),
    # Halogens
    ("[*:1]F", "F"),
    ("[*:1]Cl", "Cl"),
    ("[*:1]Br", "Br"),
    # Polar / H-bond
    ("[*:1]O", "OH"),
    ("[*:1]OC", "OMe"),
    ("[*:1]OCC", "OEt"),
    ("[*:1]OC(F)(F)F", "OCF3"),
    ("[*:1]N", "NH2"),
    ("[*:1]NC", "NHMe"),
    ("[*:1]N(C)C", "NMe2"),
    ("[*:1]NC(=O)C", "NHAc"),
    # Strongly electron-withdrawing / lipophilic
    ("[*:1]C#N", "CN"),
    ("[*:1]C(F)(F)F", "CF3"),
    ("[*:1][N+](=O)[O-]", "NO2"),
    # Carboxylates / amides / esters
    ("[*:1]C(=O)O", "COOH"),
    ("[*:1]C(=O)OC", "CO2Me"),
    ("[*:1]C(=O)N", "CONH2"),
    ("[*:1]C(=O)NC", "CONHMe"),
    # Sulfonyls
    ("[*:1]S(=O)(=O)C", "SO2Me"),
    ("[*:1]S(=O)(=O)N", "SO2NH2"),
    # Aromatic / heteroaromatic
    ("[*:1]c1ccccc1", "Ph"),
    ("[*:1]c1ccc(F)cc1", "4-F-Ph"),
    ("[*:1]c1ccc(Cl)cc1", "4-Cl-Ph"),
    ("[*:1]c1ccncc1", "4-Py"),
    # Saturated rings
    ("[*:1]C1CC1", "cPr"),
    ("[*:1]C1CCCC1", "cPent"),
    ("[*:1]C1CCCCC1", "cHex"),
    ("[*:1]N1CCCC1", "pyrrolidinyl"),
    ("[*:1]N1CCOCC1", "morpholinyl"),
]


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
@dataclass
class AnalogRecord:
    smiles: str
    name: str
    parent_smiles: str
    parent_name: str
    substituent_label: str = ""
    cut_pattern: str = ""
    mw: float = 0.0
    logp: float = 0.0
    hbd: int = 0
    hba: int = 0
    tpsa: float = 0.0
    rotatable_bonds: int = 0
    qed: float = 0.0
    sa_score: float | None = None
    tanimoto_to_parent: float = 0.0
    pains_alert: bool = False
    composite_score: float = 0.0
    rejected_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalogLibrary:
    parent_smiles: str
    parent_name: str
    requested_n: int
    n_raw: int
    n_filtered: int
    analogs: list[AnalogRecord] = field(default_factory=list)
    rejected_summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_smiles": self.parent_smiles,
            "parent_name": self.parent_name,
            "requested_n": self.requested_n,
            "n_raw": self.n_raw,
            "n_filtered": self.n_filtered,
            "rejected_summary": self.rejected_summary,
            "analogs": [a.to_dict() for a in self.analogs],
        }

    def smiles_map(self) -> dict[str, str]:
        """Return ``{name: SMILES}`` including the parent."""
        m = {self.parent_name: self.parent_smiles}
        for a in self.analogs:
            m[a.name] = a.smiles
        return m


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def generate_analogs(
    parent_smiles: str,
    parent_name: str = "parent",
    *,
    n_max: int = 30,
    min_similarity: float = 0.5,
    max_similarity: float = 0.95,
    qed_min: float = 0.3,
    max_sa_score: float = 4.5,
    skip_pains: bool = True,
    substituents: list[tuple[str, str]] | None = None,
    max_cuts: int = 1,
    progress_callback: Any = None,
) -> AnalogLibrary:
    """Enumerate, filter, and rank analogs of ``parent_smiles``.

    Args:
        parent_smiles: SMILES of the hit ligand to start from.
        parent_name: Tag used as the prefix for analog names (e.g. ``hit_a01``).
        n_max: Maximum number of analogs to keep after ranking.
        min_similarity / max_similarity: Tanimoto bounds (vs. parent) for
            keeping an analog. Defaults of 0.5–0.95 keep recognisably
            related analogs without keeping near-duplicates of the parent.
        qed_min: Minimum quantitative druglikeness (Bickerton).
        max_sa_score: Synthetic-accessibility cutoff (1 = easy, 10 = hard).
            Ignored if the SAScore Contrib module isn't importable.
        skip_pains: Drop analogs flagged by PAINS / Brenk / NIH catalogues.
        substituents: Override the substituent library; defaults to
            ``DEFAULT_SUBSTITUENTS``.
        max_cuts: 1 (single-bond R-group swaps) or 2 (linker swaps).
        progress_callback: Optional ``callable(dict)`` for streaming UI updates.

    Returns:
        ``AnalogLibrary`` with ranked analogs plus rejection summary.
    """
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors, QED, rdFingerprintGenerator, rdMMPA, rdMolDescriptors
    from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams
    from rdkit.DataStructs import TanimotoSimilarity

    def _emit(stage: str, **extra: Any) -> None:
        if progress_callback:
            progress_callback({"stage": stage, **extra})

    parent = Chem.MolFromSmiles(parent_smiles)
    if parent is None:
        raise ValueError(f"Could not parse parent SMILES: {parent_smiles!r}")

    RDLogger.DisableLog("rdApp.warning")
    RDLogger.DisableLog("rdApp.error")
    morgan_generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    parent_canonical = Chem.MolToSmiles(parent)
    parent_fp = morgan_generator.GetFingerprint(parent)
    subs = substituents or DEFAULT_SUBSTITUENTS

    pains_catalog = None
    if skip_pains:
        try:
            params = FilterCatalogParams()
            params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
            params.AddCatalog(FilterCatalogParams.FilterCatalogs.BRENK)
            params.AddCatalog(FilterCatalogParams.FilterCatalogs.NIH)
            pains_catalog = FilterCatalog(params)
        except Exception:
            pains_catalog = None

    sa_scorer = _try_import_sa_scorer()

    # -----------------------------------------------------------------------
    # 1. Decompose parent into scaffold-with-[*:1] strings (one per cut site)
    # -----------------------------------------------------------------------
    _emit("decomposing")
    scaffolds = _decompose_with_mmpa(parent, max_cuts=max_cuts)
    if not scaffolds:
        raise ValueError(
            f"rdMMPA produced no cut sites for parent {parent_name!r} "
            f"(SMILES={parent_smiles!r}). The molecule may be too small or "
            "may consist entirely of ring atoms with no breakable bonds."
        )
    _emit("decomposed", cuts=len(scaffolds))

    # -----------------------------------------------------------------------
    # 2. Enumerate analogs
    # -----------------------------------------------------------------------
    _emit("enumerating")
    raw: list[tuple[str, str, str]] = []  # (analog_smiles, sub_label, scaffold_smi)
    seen: set[str] = {parent_canonical}

    for scaffold_smi in scaffolds:
        for sub_smiles, sub_label in subs:
            try:
                analog_smiles = _splice_substituent(scaffold_smi, sub_smiles)
            except Exception:
                continue
            if not analog_smiles or analog_smiles in seen:
                continue
            seen.add(analog_smiles)
            raw.append((analog_smiles, sub_label, scaffold_smi))
    _emit("enumerated", raw_analogs=len(raw))

    # -----------------------------------------------------------------------
    # 3. Filter + score
    # -----------------------------------------------------------------------
    _emit("filtering")
    accepted: list[AnalogRecord] = []
    rejected: dict[str, int] = {}

    def _bump(reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1

    for analog_smiles, sub_label, cut_pattern in raw:
        mol = Chem.MolFromSmiles(analog_smiles)
        if mol is None:
            _bump("invalid_smiles")
            continue
        try:
            mol = Chem.RemoveHs(mol)
            Chem.SanitizeMol(mol)
        except Exception:
            _bump("sanitisation_failed")
            continue

        mw = Descriptors.MolWt(mol)
        logp = Descriptors.MolLogP(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        rotb = rdMolDescriptors.CalcNumRotatableBonds(mol)
        qed = QED.qed(mol)
        fp = morgan_generator.GetFingerprint(mol)
        tanimoto = TanimotoSimilarity(parent_fp, fp)

        sa_score: float | None = None
        if sa_scorer is not None:
            try:
                sa_score = float(sa_scorer.calculateScore(mol))
            except Exception:
                sa_score = None

        pains = False
        if pains_catalog is not None:
            try:
                pains = pains_catalog.HasMatch(mol)
            except Exception:
                pains = False

        canonical = Chem.MolToSmiles(mol)
        record = AnalogRecord(
            smiles=canonical,
            name="",  # filled in after ranking
            parent_smiles=parent_canonical,
            parent_name=parent_name,
            substituent_label=sub_label,
            cut_pattern=cut_pattern,
            mw=round(mw, 2),
            logp=round(logp, 2),
            hbd=hbd,
            hba=hba,
            tpsa=round(tpsa, 1),
            rotatable_bonds=rotb,
            qed=round(qed, 3),
            sa_score=round(sa_score, 2) if sa_score is not None else None,
            tanimoto_to_parent=round(tanimoto, 3),
            pains_alert=pains,
        )

        # Filter cascade — record but skip rejected analogs.
        reasons: list[str] = []
        if not (200.0 <= mw <= 500.0):
            reasons.append("mw_out_of_range")
        if not (-1.0 <= logp <= 5.0):
            reasons.append("logp_out_of_range")
        if hbd > 5:
            reasons.append("hbd_too_high")
        if hba > 10:
            reasons.append("hba_too_high")
        if tpsa > 140.0:
            reasons.append("tpsa_too_high")
        if qed < qed_min:
            reasons.append("low_qed")
        if sa_score is not None and sa_score > max_sa_score:
            reasons.append("low_synthesizability")
        if pains and skip_pains:
            reasons.append("pains")
        if tanimoto < min_similarity:
            reasons.append("too_dissimilar")
        if tanimoto >= max_similarity:
            reasons.append("near_duplicate")

        if reasons:
            for r in reasons:
                _bump(r)
            record.rejected_reason = ",".join(reasons)
            continue

        # Composite score: peak at Tanimoto ~0.7, weighted by druglikeness.
        sweet_spot = 1.0 - abs(tanimoto - 0.70) / 0.45  # 0..1; 1 at 0.7
        sa_term = 1.0 if sa_score is None else max(0.0, 1.0 - (sa_score - 1.0) / 5.0)
        record.composite_score = round(0.5 * sweet_spot + 0.3 * qed + 0.2 * sa_term, 4)
        accepted.append(record)

    _emit("filtered", kept=len(accepted), rejected=sum(rejected.values()))

    # -----------------------------------------------------------------------
    # 4. Rank + truncate + name
    # -----------------------------------------------------------------------
    accepted.sort(key=lambda r: r.composite_score, reverse=True)
    final = accepted[:n_max]
    width = max(2, len(str(len(final))))
    for i, rec in enumerate(final, 1):
        rec.name = f"{parent_name}_a{i:0{width}d}"

    _emit("done", kept=len(final))
    return AnalogLibrary(
        parent_smiles=parent_canonical,
        parent_name=parent_name,
        requested_n=n_max,
        n_raw=len(raw),
        n_filtered=len(final),
        analogs=final,
        rejected_summary=rejected,
    )


def write_analog_library(library: AnalogLibrary, output_dir: Path) -> Path:
    """Persist the library as ``analog_library.json``. Returns the path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "analog_library.json"
    out_path.write_text(json.dumps(library.to_dict(), indent=2))
    return out_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _decompose_with_mmpa(parent, max_cuts: int) -> list[str]:
    """Return scaffold SMILES (one ``[*:1]`` dummy each) for every single-cut.

    rdMMPA's ``FragmentMol`` returns ``(sidechain, core)`` where ``core``
    is a *disconnected* SMILES of the form ``"sidechain.scaffold"`` — both
    fragments carry matching ``[*:N]`` dummies, ready to be reassembled
    with ``molzip``. We isolate the larger fragment (the scaffold) so it
    can be zipped against an arbitrary substituent.

    Currently only single cuts are returned; double-cut linker swaps would
    require substituent libraries with paired ``[*:1]`` / ``[*:2]`` dummies.
    """
    from rdkit import Chem
    from rdkit.Chem import rdMMPA

    scaffolds: list[str] = []
    seen: set[str] = set()
    for cut_count in range(1, min(max_cuts, 1) + 1):
        try:
            frags = rdMMPA.FragmentMol(
                parent, maxCuts=cut_count, resultsAsMols=False
            )
        except Exception:
            frags = []
        for sidechain, core in frags or []:
            joined = core or sidechain
            if not joined:
                continue
            parts = joined.split(".")
            atomcounts: list[tuple[str, int]] = []
            for p in parts:
                m = Chem.MolFromSmiles(p)
                if m is None:
                    continue
                atomcounts.append((p, m.GetNumHeavyAtoms()))
            if len(atomcounts) < 2:
                # No real cut (only one fragment after parsing)
                continue
            atomcounts.sort(key=lambda x: x[1], reverse=True)
            scaffold_smi = atomcounts[0][0]
            if scaffold_smi not in seen:
                seen.add(scaffold_smi)
                scaffolds.append(scaffold_smi)
    return scaffolds


def _splice_substituent(scaffold_smi: str, sub_smi: str) -> str | None:
    """Combine scaffold + substituent (both have ``[*:1]``) and molzip.

    Returns the canonical SMILES of the resulting analog or ``None`` if
    the splice is chemically invalid.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    scaffold = Chem.MolFromSmiles(scaffold_smi)
    sub = Chem.MolFromSmiles(sub_smi)
    if scaffold is None or sub is None:
        return None
    # molzip operates on a single molecule that contains both fragments
    # (matched [*:N] dummies). Combine via disconnected SMILES.
    try:
        combined = Chem.MolFromSmiles(
            Chem.MolToSmiles(scaffold) + "." + Chem.MolToSmiles(sub)
        )
        if combined is None:
            return None
        zipped = AllChem.molzip(combined)
    except Exception:
        return None
    if zipped is None:
        return None
    try:
        Chem.SanitizeMol(zipped)
    except Exception:
        return None
    return Chem.MolToSmiles(zipped)


def _try_import_sa_scorer() -> Any:
    """Return the SA-Score module if importable, else ``None``."""
    candidates = (
        "rdkit.Chem.Contrib.SA_Score.sascorer",
        "rdkit.Contrib.SA_Score.sascorer",
    )
    for path in candidates:
        try:
            module_path, attr = path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[attr])
            return getattr(module, attr) if attr in dir(module) else module
        except Exception:
            continue
    return None
