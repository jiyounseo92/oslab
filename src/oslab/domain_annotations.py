"""Per-pocket domain annotation for fpocket binding-site selection.

Given an fpocket output directory plus a target identifier (PDB ID or UniProt
accession), annotate each pocket with:
  * the unique lining residues parsed from `pockets/pocket{N}_atm.pdb`
  * the UniProt features (Topological domain, Transmembrane, Domain, ...) that
    contain those residues, with the percent of the pocket each feature covers

Used by the dashboard fpocket selection UI to make pocket picking clearer
(e.g. "Pocket 3 - 78% Kinase domain" instead of bare scores).

External calls (cached process-wide):
  - PDBe SIFTS:  https://www.ebi.ac.uk/pdbe/api/mappings/uniprot/{pdb_id}
  - UniProt KB:  https://rest.uniprot.org/uniprotkb/{accession}.json

Failure modes are silent: if either API is unreachable or the target has no
UniProt mapping (custom local PDB, obsolete entry), pockets get `residues`
only and `domains` stays empty.
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import URLError

_PDB_ID_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
_UNIPROT_ACC_RE = re.compile(
    r"^(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](?:[A-Z][A-Z0-9]{2}[0-9])?)$"
)
_ALPHAFOLD_FILE_RE = re.compile(r"^AF-([A-Z0-9]+)-F\d+-model", re.IGNORECASE)

# UniProt feature types worth surfacing as pocket annotations. Order is the
# display priority — entries earlier in this tuple are shown first when a
# pocket overlaps multiple features.
_RELEVANT_FEATURES: tuple[str, ...] = (
    "Topological domain",  # Extracellular / Cytoplasmic / Lumenal
    "Transmembrane",
    "Signal peptide",
    "Domain",              # Kinase, SH2, fibronectin, forkhead, ...
    "Repeat",
    "Coiled coil",
    "Zinc finger",
    "Region",              # disordered, activation loop, etc.
)

# Minimum percent of pocket residues a feature must cover before we show it.
# Filters out incidental overlaps with small features (single binding-site
# residues, post-translational modification sites).
_MIN_PERCENT = 10

_HTTP_TIMEOUT = 8.0
_USER_AGENT = "OSLab-domain-annotator/1.0"

_SIFTS_CACHE: dict[str, dict[str, list[dict[str, Any]]]] = {}
_UNIPROT_CACHE: dict[str, list[dict[str, Any]]] = {}


def annotate_pockets(
    pockets: list[dict[str, Any]],
    *,
    fpocket_out_dir: Path,
    target_identifier: str | None = None,
) -> list[dict[str, Any]]:
    """Augment each pocket dict in-place with `residues`, `domains`, and (when
    a UniProt mapping is available) `uniprot_accession`.

    `target_identifier` can be:
      - a PDB ID (4 chars, e.g. "3PXQ")
      - a UniProt accession (e.g. "P24941")
      - an AlphaFold filename stem (e.g. "AF-P24941-F1-model_v4")
      - a path or filename (the stem is examined for the above patterns)
      - None — only the residue list is filled in; no domain annotation

    Returns the same list reference for convenience.
    """
    if not pockets:
        return pockets

    pocket_residues: dict[int, list[dict[str, Any]]] = {}
    for pocket in pockets:
        pid = pocket.get("pocket_id")
        if pid is None:
            continue
        atm_pdb = Path(fpocket_out_dir) / "pockets" / f"pocket{pid}_atm.pdb"
        residues = _parse_pocket_residues(atm_pdb) if atm_pdb.exists() else []
        pocket["residues"] = residues
        pocket_residues[pid] = residues

    pdb_id, uniprot_acc = _resolve_identifiers(target_identifier)
    chain_mappings: dict[str, list[dict[str, Any]]] = {}
    if pdb_id:
        chain_mappings = _fetch_sifts_mapping(pdb_id)
    if not uniprot_acc:
        uniprot_acc = _dominant_accession(chain_mappings)
    if not uniprot_acc:
        return pockets

    features = _fetch_uniprot_features(uniprot_acc)
    if not features:
        return pockets

    for pocket in pockets:
        pid = pocket.get("pocket_id")
        residues = pocket_residues.get(pid, [])
        if not residues:
            continue
        pocket["uniprot_accession"] = uniprot_acc
        pocket["domains"] = _summarize_pocket_domains(
            residues, chain_mappings, features, uniprot_acc
        )
    return pockets


def _parse_pocket_residues(atm_pdb: Path) -> list[dict[str, Any]]:
    """Return unique residues from an fpocket per-pocket ATOM PDB.

    Each residue is {"chain": str, "resi": int, "resn": str}. Order follows
    first appearance in the file (lining-atom order, not residue-number order).
    """
    residues: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    try:
        with atm_pdb.open() as handle:
            for line in handle:
                if not line.startswith("ATOM"):
                    continue
                if len(line) < 27:
                    continue
                resn = line[17:20].strip()
                chain = line[21:22].strip() or "A"
                try:
                    resi = int(line[22:26].strip())
                except ValueError:
                    continue
                key = (chain, resi)
                if key in seen:
                    continue
                seen.add(key)
                residues.append({"chain": chain, "resi": resi, "resn": resn})
    except OSError:
        return []
    return residues


def _resolve_identifiers(target_identifier: str | None) -> tuple[str | None, str | None]:
    """Return (pdb_id, uniprot_accession) from a filename / id string."""
    if not target_identifier:
        return None, None
    stem = str(target_identifier).strip().split("/")[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    m = _ALPHAFOLD_FILE_RE.match(stem)
    if m:
        return None, m.group(1).upper()
    if _PDB_ID_RE.match(stem):
        return stem.upper(), None
    if _UNIPROT_ACC_RE.match(stem):
        return None, stem.upper()
    return None, None


def _fetch_sifts_mapping(pdb_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return {chain_id: [{uniprot, pdb_start, pdb_end, uni_start, uni_end}, ...]}."""
    key = pdb_id.lower()
    if key in _SIFTS_CACHE:
        return _SIFTS_CACHE[key]
    url = f"https://www.ebi.ac.uk/pdbe/api/mappings/uniprot/{key}"
    raw = _safe_json_get(url)
    chain_mappings: dict[str, list[dict[str, Any]]] = {}
    if isinstance(raw, dict):
        entry = raw.get(key, {})
        for acc, info in entry.get("UniProt", {}).items():
            for mp in info.get("mappings", []) or []:
                chain = mp.get("chain_id")
                if not chain:
                    continue
                start = (mp.get("start") or {}).get("residue_number")
                end = (mp.get("end") or {}).get("residue_number")
                if start is None or end is None:
                    continue
                chain_mappings.setdefault(chain, []).append({
                    "uniprot": acc,
                    "pdb_start": int(start),
                    "pdb_end": int(end),
                    "uni_start": int(mp.get("unp_start") or start),
                    "uni_end": int(mp.get("unp_end") or end),
                })
    _SIFTS_CACHE[key] = chain_mappings
    return chain_mappings


def _fetch_uniprot_features(accession: str) -> list[dict[str, Any]]:
    """Return [{type, description, start, end}, ...] for relevant feature types."""
    key = accession.upper()
    if key in _UNIPROT_CACHE:
        return _UNIPROT_CACHE[key]
    url = f"https://rest.uniprot.org/uniprotkb/{key}.json"
    raw = _safe_json_get(url)
    features: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for f in raw.get("features", []) or []:
            ftype = f.get("type")
            if ftype not in _RELEVANT_FEATURES:
                continue
            loc = f.get("location", {}) or {}
            try:
                start = int((loc.get("start") or {}).get("value"))
                end = int((loc.get("end") or {}).get("value"))
            except (TypeError, ValueError):
                continue
            features.append({
                "type": ftype,
                "description": f.get("description") or "",
                "start": start,
                "end": end,
            })
    _UNIPROT_CACHE[key] = features
    return features


def _dominant_accession(
    chain_mappings: dict[str, list[dict[str, Any]]]
) -> str | None:
    """Pick the UniProt accession covering the most residues across all chains."""
    coverage: dict[str, int] = {}
    for mappings in chain_mappings.values():
        for m in mappings:
            ps, pe = m.get("pdb_start"), m.get("pdb_end")
            if ps is None or pe is None:
                continue
            span = max(0, int(pe) - int(ps) + 1)
            coverage[m["uniprot"]] = coverage.get(m["uniprot"], 0) + span
    if not coverage:
        return None
    return max(coverage, key=coverage.get)


def _summarize_pocket_domains(
    residues: list[dict[str, Any]],
    chain_mappings: dict[str, list[dict[str, Any]]],
    features: list[dict[str, Any]],
    uniprot_acc: str,
) -> list[dict[str, Any]]:
    """Compute domain coverage for a pocket. Returns a sorted list of hits."""
    total = len(residues)
    if total == 0:
        return []
    hits: dict[tuple[str, str], int] = {}
    for r in residues:
        uni = _map_pdb_to_uniprot(r["chain"], int(r["resi"]), chain_mappings, uniprot_acc)
        if uni is None:
            continue
        for f in features:
            if f["start"] <= uni <= f["end"]:
                desc = f["description"] or f["type"]
                key = (f["type"], desc)
                hits[key] = hits.get(key, 0) + 1
    summary: list[dict[str, Any]] = []
    for (ftype, desc), count in hits.items():
        pct = round(100.0 * count / total)
        if pct < _MIN_PERCENT:
            continue
        summary.append({
            "type": ftype,
            "label": desc,
            "residues_in_pocket": count,
            "percent": pct,
        })
    type_priority = {t: i for i, t in enumerate(_RELEVANT_FEATURES)}
    summary.sort(key=lambda h: (type_priority.get(h["type"], 999), -h["percent"]))
    return summary


def _map_pdb_to_uniprot(
    chain: str,
    resi: int,
    chain_mappings: dict[str, list[dict[str, Any]]],
    uniprot_acc: str,
) -> int | None:
    for m in chain_mappings.get(chain, []):
        if m.get("uniprot") != uniprot_acc:
            continue
        ps, pe = m.get("pdb_start"), m.get("pdb_end")
        us = m.get("uni_start")
        if ps is None or pe is None or us is None:
            continue
        if ps <= resi <= pe:
            return int(us) + (resi - int(ps))
    return None


def _safe_json_get(url: str) -> Any:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return json.load(resp)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None
