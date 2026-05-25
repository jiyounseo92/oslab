from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .jobs import campaign_context
from .schemas import ProjectLayout


ROOT_ENV_VARS = ("OSLAB_ROOT", "OPEN_STRUCTURE_LAB_ROOT")
CONFIG_ENV_VAR = "OSLAB_CONFIG_DIR"
DEFAULT_PROJECT_ROOT_NAME = "Open Structure Lab"


def safe_user_name(username: str | None) -> str:
    """Return a filesystem-safe user identifier for user-scoped OSLab folders."""

    text = str(username or "").strip()
    if not text:
        text = "default-user"
    text = re.sub(r"[^A-Za-z0-9_.@-]+", "-", text).strip(".-")
    return text or "default-user"


def config_dir() -> Path:
    configured = os.environ.get(CONFIG_ENV_VAR)
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home().expanduser().resolve() / ".config" / "open-structure-lab"


def config_path() -> Path:
    return config_dir() / "config.json"


def _read_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def set_default_project_root(root: Path) -> Path:
    root = root.expanduser().resolve()
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    data = _read_config()
    data["project_root"] = str(root)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    config_path().write_text(json.dumps(data, indent=2) + "\n")
    return root


def default_project_root() -> Path:
    for name in ROOT_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser().resolve()

    configured = _read_config().get("project_root")
    if configured:
        return Path(str(configured)).expanduser().resolve()

    documents = Path.home().expanduser() / "Documents"
    if documents.exists():
        return (documents / DEFAULT_PROJECT_ROOT_NAME).resolve()
    return (Path.home().expanduser() / DEFAULT_PROJECT_ROOT_NAME).resolve()


def ensure_project_layout(root: Path) -> ProjectLayout:
    root = root.expanduser().resolve()
    data_cache = root / "data-cache"
    paths = {
        "data_cache": data_cache,
        "runs": root / "runs",
        "logs": root / "logs",
        "reports": root / "reports",
    }
    data_subdirs = ["pdb", "alphafold", "zinc", "validation", "user", "demo"]

    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    for subdir in data_subdirs:
        (data_cache / subdir).mkdir(parents=True, exist_ok=True)

    metadata_dir = root / ".oslab"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = metadata_dir / "project.json"
    if not metadata_path.exists():
        campaign = campaign_context()
        metadata_path.write_text(
            json.dumps(
                {
                    "schema": "open-structure-lab.project.v1",
                    "root": str(root),
                    **campaign,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n"
        )

    database = root / "oslab.sqlite"
    return ProjectLayout(
        root=str(root),
        data_cache=str(data_cache),
        runs=str(paths["runs"]),
        logs=str(paths["logs"]),
        reports=str(paths["reports"]),
        database=str(database),
    )


def ensure_user_project_layout(root: Path, username: str | None) -> dict[str, str]:
    """Create and return the per-user OSLab workspace layout.

    The top-level project root remains the shared installation/workspace root.
    Large shared caches such as PDB, AlphaFold, and ZINC live under
    ``root/data-cache``. User-generated outputs live under
    ``root/users/<username>`` so multiple private-key users can run OSLab
    without colliding on run labels, reports, logs, or dashboard jobs.
    """

    root = root.expanduser().resolve()
    ensure_project_layout(root)
    user = safe_user_name(username)
    user_root = root / "users" / user
    paths = {
        "root": user_root,
        "runs": user_root / "runs",
        "reports": user_root / "reports",
        "logs": user_root / "logs",
        "data_cache": user_root / "data-cache",
        "ligand_libraries": user_root / "ligand_libraries",
        "packages": user_root / "packages",
        "metadata": user_root / ".oslab",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)

    metadata_path = paths["metadata"] / "project.json"
    if not metadata_path.exists():
        campaign = campaign_context()
        metadata_path.write_text(
            json.dumps(
                {
                    "schema": "open-structure-lab.user-project.v1",
                    "project_root": str(root),
                    "user": user,
                    "root": str(user_root),
                    "shared_data_cache": str(root / "data-cache"),
                    **campaign,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            )
            + "\n"
        )

    return {key: str(value) for key, value in paths.items()} | {"user": user, "project_root": str(root)}
