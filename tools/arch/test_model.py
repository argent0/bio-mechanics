"""Parsing and validation of the module map."""

import copy
import json
from pathlib import Path

import pytest

from tools.arch.model import MapError, load_map, parse_map

REAL_MAP = Path(__file__).resolve().parents[2] / "generated" / "modules.json"


def raw() -> dict[str, object]:
    data: dict[str, object] = json.loads(REAL_MAP.read_text(encoding="utf-8"))
    return data


def test_loads_real_map() -> None:
    arch = load_map(REAL_MAP)
    assert len(arch.modules) == 13
    assert [a.id for a in arch.apis] == ["C1", "C2", "C3", "C4"]
    h = arch.module("H")
    assert (h.name, h.lang, h.consumes) == ("Arch viewer", "Python", ("C4",))
    assert arch.api("C4").consumers == ("H",)


def test_rejects_bad_json(tmp_path: Path) -> None:
    f = tmp_path / "m.json"
    f.write_text("{not json")
    with pytest.raises(MapError, match="invalid JSON"):
        load_map(f)
    with pytest.raises(MapError, match="cannot read"):
        load_map(tmp_path / "missing.json")


def mutate(change: str) -> dict[str, object]:
    d = copy.deepcopy(raw())
    mods: list[dict[str, object]] = d["modules"]  # type: ignore[assignment]
    apis: list[dict[str, object]] = d["apis"]  # type: ignore[assignment]
    if change == "type":
        mods[0]["layer"] = "zero"
    elif change == "dup":
        mods.append(dict(mods[0]))
    elif change == "producer":
        apis[0]["producer"] = "nobody"
    elif change == "order":
        apis[3]["consumers"] = ["coordinator"]
        apis[3]["producer"] = "H"
    elif change == "mismatch":
        mods[1]["consumes"] = []
    return d


@pytest.mark.parametrize("change,message", [
    ("type", "layer"), ("dup", "duplicate module"), ("producer", "unknown producer"),
    ("order", "must sit above"), ("mismatch", "disagrees"),
])
def test_validation(change: str, message: str) -> None:
    with pytest.raises(MapError, match=message):
        parse_map(mutate(change))
