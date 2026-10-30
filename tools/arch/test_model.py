"""Parsing and validation of the module map."""

import json
from pathlib import Path

import pytest

from tools.arch.model import MapError, load_map, parse_map

REAL_MAP = Path(__file__).resolve().parents[2] / "generated" / "modules.json"


def mod(i: str, layer: int, produces: list[str], consumes: list[str]) -> dict[str, object]:
    return {"id": i, "name": f"Module {i}", "lang": "Python", "model": "sonnet", "state": "planned",
            "layer": layer, "paths": [f"{i}/"], "acceptance": [f"test {i}"],
            "produces": produces, "consumes": consumes}


def mini() -> dict[str, object]:
    """A small valid map: X generates K for Y and Z; Y generates L for Z."""
    return {
        "$generated": "test",
        "modules": [mod("X", 0, ["K"], []), mod("Y", 1, ["L"], ["K"]), mod("Z", 2, [], ["K", "L"])],
        "apis": [
            {"id": "K", "name": "Kay", "files": ["k"], "producer": "X", "consumers": ["Y", "Z"]},
            {"id": "L", "name": "El", "files": ["l"], "producer": "Y", "consumers": ["Z"]},
        ],
    }


def test_loads_real_map() -> None:
    data = json.loads(REAL_MAP.read_text(encoding="utf-8"))
    arch = load_map(REAL_MAP)
    assert [m.id for m in arch.modules] == [m["id"] for m in data["modules"]]
    assert [a.id for a in arch.apis] == [a["id"] for a in data["apis"]]
    for a in arch.apis:
        assert arch.module(a.producer).produces.count(a.id) == 1


def test_parses_mini_map() -> None:
    arch = parse_map(mini())
    assert arch.module("Y").consumes == ("K",) and arch.api("K").consumers == ("Y", "Z")


def test_rejects_bad_json(tmp_path: Path) -> None:
    f = tmp_path / "m.json"
    f.write_text("{not json")
    with pytest.raises(MapError, match="invalid JSON"):
        load_map(f)
    with pytest.raises(MapError, match="cannot read"):
        load_map(tmp_path / "missing.json")


def mutate(change: str) -> dict[str, object]:
    d = mini()
    mods: list[dict[str, object]] = d["modules"]  # type: ignore[assignment]
    apis: list[dict[str, object]] = d["apis"]  # type: ignore[assignment]
    if change == "type":
        mods[0]["layer"] = "zero"
    elif change == "dup":
        mods.append(dict(mods[0]))
    elif change == "producer":
        apis[0]["producer"] = "nobody"
    elif change == "order":
        mods[0]["layer"] = 2
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
