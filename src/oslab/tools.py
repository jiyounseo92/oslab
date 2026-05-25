from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


CLI_TOOLS = {
    "python3": "Runtime for dashboard, CLI orchestration, RDKit, OpenMM, OpenFE, and reporting",
    "micromamba": "Environment manager used by the dashboard update button",
    "obabel": "Open Babel ligand conversion and file repair fallback",
    "mk_prepare_receptor.py": "Meeko receptor conversion to PDBQT",
    "mk_prepare_ligand.py": "Meeko ligand conversion to PDBQT",
    "vina": "AutoDock Vina docking engine for screening and hit refinement",
    "fpocket": "Blind binding-pocket detector used in Binding Sites and terminal docking",
    "plip": "Protein-Ligand Interaction Profiler used for interaction analysis and pose figures",
}

CLI_ALIASES = {
    "plip": ("plipcmd",),
}

PYTHON_IMPORTS = {
    "meeko": "PDBQT ligand/receptor preparation for AutoDock Vina",
    "openmm": "OpenMM molecular mechanics, MD, and minimization",
    "pdbfixer": "PDBFixer protein repair",
    "rdkit": "RDKit cheminformatics",
    "gemmi": "Robust PDB/mmCIF structure parsing",
    "MDAnalysis": "Trajectory and structure analysis",
    "prolif": "Protein-ligand interaction fingerprints for MD analysis",
    "spyrmsd": "Symmetry-corrected ligand RMSD",
    "pydantic": "Validated configs and manifests",
}


@dataclass(frozen=True)
class ToolStatus:
    name: str
    available: bool
    detail: str


def check_cli_tools() -> list[ToolStatus]:
    statuses: list[ToolStatus] = []
    env_bin = Path(sys.executable).resolve().parent
    for name, description in CLI_TOOLS.items():
        path = shutil.which(name)
        if not path:
            for alias in CLI_ALIASES.get(name, ()):
                path = shutil.which(alias)
                if path:
                    break
        if not path:
            candidate = env_bin / name
            if candidate.exists():
                path = str(candidate)
        if not path:
            for alias in CLI_ALIASES.get(name, ()):
                candidate = env_bin / alias
                if candidate.exists():
                    path = str(candidate)
                    break
        if name == "micromamba" and not path:
            candidates = [Path.home() / ".open-structure-lab" / ".micromamba" / "bin" / "micromamba", Path.home() / ".local" / "bin" / "micromamba"]
            root_prefix = os.environ.get("MAMBA_ROOT_PREFIX", "")
            if root_prefix:
                candidates.insert(0, Path(root_prefix) / "bin" / "micromamba")
            for candidate in candidates:
                if candidate.exists():
                    path = str(candidate)
                    break
        statuses.append(ToolStatus(name, path is not None, path or description))
    return statuses


def check_python_imports() -> list[ToolStatus]:
    statuses: list[ToolStatus] = []
    for module, description in PYTHON_IMPORTS.items():
        try:
            __import__(module)
        except Exception as exc:  # pragma: no cover - environment-specific
            statuses.append(ToolStatus(module, False, f"{description}; import failed: {exc}"))
        else:
            statuses.append(ToolStatus(module, True, description))
    return statuses
