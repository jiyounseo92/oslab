from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

from .project import ensure_project_layout


DEMO_DATASET = "foxp3_zinc_drug_like"


def install_demo_results(root: Path, *, overwrite: bool = False) -> dict:
    """Install the bundled FOXP3 example into a project root.

    The bundled files are intentionally compact: they include the prepared
    target metadata, ligand-prep summary, docking report, result table, and a
    small set of top docked poses so a new user can explore expected outputs
    without downloading tens of thousands of ligands.
    """

    root = root.expanduser().resolve()
    ensure_project_layout(root)
    source_root = resources.files("oslab").joinpath("demo", DEMO_DATASET)
    manifest = json.loads(source_root.joinpath("manifest.json").read_text())
    installed: list[str] = []
    skipped: list[str] = []

    for relative_path in manifest.get("files", []):
        rel = Path(str(relative_path))
        destination = root / rel
        if destination.exists() and not overwrite:
            skipped.append(str(rel))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = source_root.joinpath(str(rel)).read_bytes()
        destination.write_bytes(content)
        installed.append(str(rel))

    for relative_path in manifest.get("tokenized_files", []):
        path = root / str(relative_path)
        if not path.exists():
            continue
        text = path.read_text()
        text = text.replace("__OSLAB_ROOT__", str(root))
        path.write_text(text)

    return {
        "dataset": manifest.get("dataset", DEMO_DATASET),
        "description": manifest.get("description"),
        "root": str(root),
        "installed": installed,
        "skipped": skipped,
        "report": str(root / manifest.get("primary_report", "")),
        "results_json": str(root / manifest.get("primary_results_json", "")),
    }


def remove_demo_results(root: Path) -> None:
    root = root.expanduser().resolve()
    for rel in [
        "reports/foxp3-zinc-drug-like-demo",
        "runs/foxp3-zinc-drug-like-demo",
        "runs/target-prep-AF-B7ZLG1-F1-model_v6-demo",
        "runs/binding-site-AF-B7ZLG1-F1-model_v6-pocket-1-demo",
        "runs/ligand-prep-zinc_drug_like_starter-demo",
    ]:
        path = root / rel
        if path.exists():
            shutil.rmtree(path)
