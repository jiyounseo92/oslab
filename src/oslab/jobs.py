from __future__ import annotations

import contextlib
import importlib.metadata
import json
import os
import platform
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DEFAULT_RDKIT_SEED = int(os.environ.get("OSLAB_RDKIT_SEED", "42") or 42)


def safe_slug(value: object, fallback: str = "job") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-")
    return text or fallback


def new_job_id(prefix: str = "job") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return safe_slug(f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}")


def job_run_dir(root: Path, kind: str, job_id: str) -> Path:
    return root.resolve() / "runs" / f"{safe_slug(kind)}-{safe_slug(job_id)}"


def job_progress_path(root: Path, kind: str, job_id: str) -> Path:
    return job_run_dir(root, kind, job_id) / "progress.json"


def screen_session_name(kind: str, job_id: str, *, max_len: int = 80) -> str:
    base = safe_slug(f"oslab-{kind}-{job_id}")
    return base[:max_len].rstrip(".-") or "oslab-job"


def campaign_context() -> dict[str, str]:
    return {
        "project_id": safe_slug(os.environ.get("OSLAB_PROJECT_ID") or "default-project", "default-project"),
        "campaign_id": safe_slug(os.environ.get("OSLAB_CAMPAIGN_ID") or "default-campaign", "default-campaign"),
    }


@contextlib.contextmanager
def file_lock(path: Path, *, timeout_seconds: float = 3600.0, poll_seconds: float = 0.2) -> Iterator[None]:
    """Cross-process advisory lock for shared downloads/cache writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    start = time.monotonic()
    try:
        try:
            import fcntl  # type: ignore
        except ImportError:  # pragma: no cover - Windows fallback
            yield
            return
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - start > timeout_seconds:
                    raise TimeoutError(f"Timed out waiting for file lock: {path}")
                time.sleep(poll_seconds)
        yield
    finally:
        try:
            if "fcntl" in sys.modules:
                sys.modules["fcntl"].flock(handle.fileno(), sys.modules["fcntl"].LOCK_UN)
        finally:
            handle.close()


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def runtime_provenance(*, forcefields: dict[str, Any] | None = None, structures: dict[str, Any] | None = None) -> dict[str, Any]:
    packages = {
        name: package_version(name)
        for name in (
            "rdkit",
            "openmm",
            "openff-toolkit",
            "openmmforcefields",
            "pdbfixer",
            "openfe",
            "gufe",
            "MDAnalysis",
            "prolif",
        )
    }
    return {
        "schema": "open-structure-lab.provenance.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {key: value for key, value in packages.items() if value},
        "forcefields": forcefields or {},
        "structures": structures or {},
        "rdkit_seed": DEFAULT_RDKIT_SEED,
        "openmm_platform": os.environ.get("OSLAB_OPENMM_PLATFORM", ""),
        "openfe_bin": os.environ.get("OSLAB_OPENFE_BIN", ""),
        **campaign_context(),
    }


def set_rdkit_seed(seed: int = DEFAULT_RDKIT_SEED) -> int:
    try:
        from rdkit import rdBase

        if hasattr(rdBase, "SeedRandomNumberGenerator"):
            rdBase.SeedRandomNumberGenerator(int(seed))
    except Exception:
        pass
    return int(seed)
