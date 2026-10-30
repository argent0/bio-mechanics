"""Every file the merge recipe names is a declared read of stage `buildModel`, so ninja reruns it when one changes."""

from pathlib import Path
from typing import Any

import yaml

from pipeline_paths import BUILD_MODEL

ROOT = Path(__file__).resolve().parent.parent
RECIPE = ROOT / "pipeline" / "config" / "model.yaml"


def paths_in(value: Any) -> list[str]:
    """Every string under `data/raw/` in a parsed YAML value."""
    if isinstance(value, str):
        return [value] if value.startswith("data/raw/") else []
    if isinstance(value, dict):
        return [p for v in value.values() for p in paths_in(v)]
    if isinstance(value, list):
        return [p for v in value for p in paths_in(v)]
    return []


def test_recipe_paths_are_buildmodel_reads() -> None:
    named = paths_in(yaml.safe_load(RECIPE.read_text()))
    assert named, "the recipe names its source files"
    inputs = [i.rstrip("/") for i in BUILD_MODEL.inputs]
    for p in named:
        p = p.rstrip("/")
        assert any(p == i or p.startswith(i + "/") for i in inputs), f"{p} is a read of buildModel"
