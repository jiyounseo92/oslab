from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .jobs import file_lock
from .project import ensure_project_layout
from .schemas import StructureRecord


RCSB_DOWNLOAD_BASE = "https://files.rcsb.org/download"
ALPHAFOLD_DOWNLOAD_BASE = "https://alphafold.ebi.ac.uk/files"
ALPHAFOLD_API_BASE = "https://alphafold.ebi.ac.uk/api/prediction"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_record(record: StructureRecord) -> StructureRecord:
    metadata_path = Path(record.metadata_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n")
    return record


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock_path = destination.with_suffix(destination.suffix + ".lock")
    with file_lock(lock_path):
        if destination.exists() and destination.stat().st_size > 0:
            return
        tmp_path = destination.with_name(f".{destination.name}.tmp.{os.getpid()}")
        with urllib.request.urlopen(url, timeout=60) as response:
            tmp_path.write_bytes(response.read())
        os.replace(tmp_path, destination)


def _alphafold_latest_version(accession: str) -> int:
    url = f"{ALPHAFOLD_API_BASE}/{accession}"
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload:
        raise ValueError(f"AlphaFold DB has no prediction entry for UniProt accession {accession}")
    latest = payload[0].get("latestVersion")
    if not latest:
        versions = payload[0].get("allVersions") or []
        latest = max(versions) if versions else None
    if not latest:
        raise ValueError(f"AlphaFold DB metadata for {accession} did not include a model version")
    return int(latest)


def fetch_pdb_structure(
    pdb_id: str,
    root: Path,
    file_format: str = "cif",
    overwrite: bool = False,
) -> StructureRecord:
    pdb_id = pdb_id.upper()
    if file_format not in {"cif", "pdb"}:
        raise ValueError("PDB file format must be 'cif' or 'pdb'")

    layout = ensure_project_layout(root)
    extension = "cif" if file_format == "cif" else "pdb"
    filename = f"{pdb_id}.{extension}"
    url = f"{RCSB_DOWNLOAD_BASE}/{filename}"
    cached_path = Path(layout.data_cache) / "pdb" / filename
    metadata_path = cached_path.with_suffix(cached_path.suffix + ".json")

    if overwrite or not cached_path.exists():
        _download(url, cached_path)

    record = StructureRecord(
        key=f"pdb:{pdb_id}",
        source="pdb",
        identifier=pdb_id,
        source_url=url,
        cached_path=str(cached_path),
        metadata_path=str(metadata_path),
        file_format=file_format,  # type: ignore[arg-type]
        structure_type="experimental",
        sha256=sha256_file(cached_path),
        retrieved_at=datetime.now(timezone.utc),
        license_or_terms="RCSB PDB public data; record source URL and structure ID in reports.",
        notes="Experimental structure downloaded from RCSB PDB.",
    )
    return _write_record(record)


def fetch_alphafold_structure(
    uniprot_accession: str,
    root: Path,
    model_version: int | None = None,
    overwrite: bool = False,
) -> StructureRecord:
    accession = uniprot_accession.upper()
    resolved_version = model_version or _alphafold_latest_version(accession)
    filename = f"AF-{accession}-F1-model_v{resolved_version}.pdb"
    url = f"{ALPHAFOLD_DOWNLOAD_BASE}/{filename}"
    layout = ensure_project_layout(root)
    cached_path = Path(layout.data_cache) / "alphafold" / filename
    metadata_path = cached_path.with_suffix(cached_path.suffix + ".json")

    if overwrite or not cached_path.exists():
        _download(url, cached_path)

    record = StructureRecord(
        key=f"alphafold:{accession}:v{resolved_version}",
        source="alphafold",
        identifier=accession,
        source_url=url,
        cached_path=str(cached_path),
        metadata_path=str(metadata_path),
        file_format="pdb",
        structure_type="predicted",
        sha256=sha256_file(cached_path),
        retrieved_at=datetime.now(timezone.utc),
        license_or_terms="AlphaFold DB public data; record accession, model version, source URL, and terms in reports.",
        notes=f"Predicted AlphaFold DB structure model version {resolved_version}.",
    )
    return _write_record(record)


def register_local_structure(
    input_path: Path,
    root: Path,
    identifier: str | None = None,
    file_format: str | None = None,
    copy: bool = True,
    overwrite: bool = False,
) -> StructureRecord:
    if not input_path.is_file():
        raise FileNotFoundError(input_path)

    suffix = input_path.suffix.lower()
    inferred = "cif" if suffix in {".cif", ".mmcif"} else "pdb" if suffix == ".pdb" else None
    resolved_format = file_format or inferred
    if resolved_format == "mmcif":
        resolved_format = "cif"
    if resolved_format not in {"pdb", "cif"}:
        raise ValueError("local structure format must be PDB or mmCIF/CIF")

    layout = ensure_project_layout(root)
    local_id = identifier or input_path.stem
    extension = "cif" if resolved_format == "cif" else "pdb"
    cached_path = Path(layout.data_cache) / "user" / f"{local_id}.{extension}"
    metadata_path = cached_path.with_suffix(cached_path.suffix + ".json")

    if copy:
        if overwrite or not cached_path.exists():
            cached_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(input_path, cached_path)
    else:
        cached_path = input_path.resolve()
        metadata_path = Path(layout.data_cache) / "user" / f"{local_id}.{extension}.json"

    record = StructureRecord(
        key=f"local:{local_id}",
        source="local",
        identifier=local_id,
        source_url="",
        cached_path=str(cached_path),
        metadata_path=str(metadata_path),
        file_format=resolved_format,  # type: ignore[arg-type]
        structure_type="user-provided",
        sha256=sha256_file(cached_path),
        retrieved_at=datetime.now(timezone.utc),
        license_or_terms="User-provided local file; user is responsible for provenance and permissions.",
        notes=f"Registered local structure from {input_path.resolve()}.",
    )
    return _write_record(record)


def list_structure_records(root: Path) -> list[StructureRecord]:
    layout = ensure_project_layout(root)
    records: list[StructureRecord] = []
    structure_dirs = ["pdb", "alphafold", "user"]
    for subdir in structure_dirs:
        for metadata_path in sorted((Path(layout.data_cache) / subdir).glob("*.json")):
            try:
                data = json.loads(metadata_path.read_text())
                records.append(StructureRecord.model_validate(data))
            except Exception:
                continue
    return records
