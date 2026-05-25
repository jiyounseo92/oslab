from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CommandStep:
    name: str
    argv: list[str]
    outputs: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Workflow:
    receptor: str
    ligands: str
    output_dir: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    steps: list[CommandStep]
    ligand_source: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "receptor": self.receptor,
            "ligands": self.ligands,
            "output_dir": self.output_dir,
            "center": list(self.center),
            "size": list(self.size),
            "ligand_source": self.ligand_source,
            "steps": [step.to_dict() for step in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        return cls(
            receptor=data["receptor"],
            ligands=data["ligands"],
            output_dir=data["output_dir"],
            center=tuple(data["center"]),
            size=tuple(data["size"]),
            steps=[CommandStep(**step) for step in data["steps"]],
            ligand_source=data.get("ligand_source"),
        )

    @property
    def manifest_path(self) -> Path:
        return Path(self.output_dir) / "workflow.json"
