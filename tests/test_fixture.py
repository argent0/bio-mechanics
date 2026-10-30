"""Contract C3: the hand-made fixture is a well-typed graph under the generated schema."""

import copy
import json
from pathlib import Path

from schema import KIND, RELATIONS, validate_graph

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "graph.sample.json"


def load() -> dict[str, object]:
    graph: dict[str, object] = json.loads(FIXTURE.read_text())
    return graph


def test_fixture_is_well_typed() -> None:
    assert validate_graph(load()) == []


def test_fixture_size() -> None:
    nodes = load()["nodes"]
    assert isinstance(nodes, list)
    assert 40 <= len(nodes) <= 50


def test_fixture_uses_every_kind() -> None:
    nodes = load()["nodes"]
    assert isinstance(nodes, list)
    assert {node["kind"] for node in nodes} == set(KIND)


def test_fixture_uses_every_relation() -> None:
    edges = load()["edges"]
    assert isinstance(edges, list)
    assert {edge["relation"] for edge in edges} == set(RELATIONS)


def test_bad_edge_is_named() -> None:
    graph = copy.deepcopy(load())
    edges = graph["edges"]
    assert isinstance(edges, list)
    edges.append({"source": "bone:femur_r", "target": "joint:knee_r", "relation": "origin"})
    errors = validate_graph(graph)
    assert any(error.startswith(f"edges[{len(edges) - 1}].source") for error in errors)


def test_fixture_regions() -> None:
    """Every node carries a region except movements and phases (`Kind.regional` in Schema.lean)."""
    nodes = load()["nodes"]
    assert isinstance(nodes, list)
    for node in nodes:
        assert (node["region"] is None) == (node["kind"] in ("movement", "phase")), node["id"]
    assert {node["side"] for node in nodes} == {"left", "right", "midline"}
    assert {node["region"] for node in nodes} - {None} == {"lowerLimb", "pelvis", "trunk", "upperLimb"}
