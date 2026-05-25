from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS compounds (
  inchi_key TEXT PRIMARY KEY,
  canonical_smiles TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  source_path TEXT,
  source_label TEXT,
  screen_count INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_compounds_smiles ON compounds(canonical_smiles);
"""


def _connect(root: Path) -> sqlite3.Connection:
    db = root.resolve() / "oslab.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.executescript(SCHEMA)
    return conn


def canonicalize_smiles(smiles: str) -> tuple[str, str] | None:
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(str(smiles or "").strip())
        if mol is None:
            return None
        canonical = Chem.MolToSmiles(mol, isomericSmiles=True)
        inchi_key = Chem.MolToInchiKey(mol)
        return canonical, inchi_key
    except Exception:
        return None


def register_compound(
    root: Path,
    smiles: str,
    *,
    source_path: str = "",
    source_label: str = "",
    metadata: dict[str, Any] | None = None,
    increment_screen_count: bool = False,
) -> str | None:
    normalized = canonicalize_smiles(smiles)
    if normalized is None:
        return None
    canonical, inchi_key = normalized
    now = datetime.now(timezone.utc).isoformat()
    import json

    with _connect(root) as conn:
        conn.execute(
            """
            INSERT INTO compounds
              (inchi_key, canonical_smiles, first_seen_at, last_seen_at, source_path, source_label, screen_count, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(inchi_key) DO UPDATE SET
              last_seen_at=excluded.last_seen_at,
              source_path=COALESCE(NULLIF(excluded.source_path, ''), compounds.source_path),
              source_label=COALESCE(NULLIF(excluded.source_label, ''), compounds.source_label),
              screen_count=compounds.screen_count + excluded.screen_count
            """,
            (
                inchi_key,
                canonical,
                now,
                now,
                source_path,
                source_label,
                1 if increment_screen_count else 0,
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
    return inchi_key


def lookup_compound(root: Path, smiles: str) -> dict[str, Any] | None:
    normalized = canonicalize_smiles(smiles)
    if normalized is None:
        return None
    _canonical, inchi_key = normalized
    with _connect(root) as conn:
        row = conn.execute(
            "SELECT inchi_key, canonical_smiles, first_seen_at, last_seen_at, source_path, source_label, screen_count FROM compounds WHERE inchi_key=?",
            (inchi_key,),
        ).fetchone()
    if row is None:
        return None
    keys = ["inchi_key", "canonical_smiles", "first_seen_at", "last_seen_at", "source_path", "source_label", "screen_count"]
    return dict(zip(keys, row, strict=True))
