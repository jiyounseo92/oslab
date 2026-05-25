from __future__ import annotations

from importlib import resources

import yaml

from oslab.schemas import LigandFilterPreset


def load_ligand_filter_preset(key: str) -> LigandFilterPreset:
    preset_path = resources.files("oslab").joinpath("presets", "ligand_filters", f"{key}.yml")
    if not preset_path.is_file():
        choices = ", ".join(list_ligand_filter_presets())
        raise ValueError(f"unknown ligand filter preset '{key}'. Available presets: {choices}")
    data = yaml.safe_load(preset_path.read_text())
    return LigandFilterPreset.model_validate(data)


def list_ligand_filter_presets() -> list[str]:
    preset_dir = resources.files("oslab").joinpath("presets", "ligand_filters")
    return sorted(path.name.removesuffix(".yml") for path in preset_dir.iterdir() if path.name.endswith(".yml"))

