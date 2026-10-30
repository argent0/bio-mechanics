"""`scripts/compare_graph.py --within-committed`: a graph that grows passes when its committed part holds still."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("compare_graph", ROOT / "scripts" / "compare_graph.py")
assert spec and spec.loader
cg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cg)

FIXTURE = ROOT / "data" / "fixtures" / "graph.sample.json"


def test_grown_graph_matches_within_committed() -> None:
    full = json.loads(FIXTURE.read_text())
    right = {n["id"] for n in full["nodes"] if n["region"] in ("lowerLimb", "pelvis", None) and n["side"] != "left"}
    committed = cg.restrict(full, right)
    _, agree, differing, _ = cg.differences(committed, cg.restrict(full, right), 0.0, 0.0)
    assert agree and not differing
    _, agree, _, _ = cg.differences(committed, full, 0.0, 0.0)
    assert not agree


def test_change_inside_committed_part_is_listed() -> None:
    full = json.loads(FIXTURE.read_text())
    ids = {n["id"] for n in full["nodes"]}
    changed = json.loads(FIXTURE.read_text())
    for e in changed["edges"]:
        if e["relation"] == "drivenBy" and e["target"] == "muscle:glmax1_r":
            e["role"] = "helper"
    _, agree, differing, _ = cg.differences(full, cg.restrict(changed, ids), 0.0, 0.0)
    assert agree and len(differing) == 1
