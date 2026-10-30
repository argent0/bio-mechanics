"""Stage `exportGraph`: the knowledge graph `data/out/graph.json` (contract C3).

Shape: `schema.Graph` (`generated/py/schema.py`, from `spec/BioMech/Schema.lean`); the stage
checks the result with `schema.validate_graph` and raises on any error.

Node ids: `<prefix>:<key>`, the key from `enriched.json` (anatomy.yaml keys, OpenSim muscle
names, `GaitPhase` constructors) and the prefix per kind (`PREFIX`), e.g. `muscle:glmed1_r`,
`bone:femur_r`, `joint:knee_r`, `group:quadriceps_r`, `phase:midStance`,
`action:knee_flexion_r`. Nodes come in the order of `schema.KIND`, then of anatomy.yaml.

Edges, by relation (all from `enriched.json`):
  origin, insertion   muscle → bone: the muscle's attachment bones
  crosses             muscle → joint: one edge per coordinate the muscle spans (roles
                      `crosses`), with the moment arm sampled over the stride
  partOf              muscle → muscleGroup
  innervatedBy        muscle → nerve
  stabilises          ligament → joint
  articulates         joint → bone
  hasPhase            movement → phase: order and bounds in percent of the stride
  involves            phase → jointAction: the action each coordinate takes in the phase
                      (`label_roles.choose_action`), `rangeDeg` = |change of the coordinate|
  actionAt            jointAction → joint, for every action of anatomy.yaml
  drivenBy            jointAction → muscle: one edge per phase and muscle with a role
                      (`label_roles.classify`), with role, contraction, peak activation, and
                      activation and moment-arm curves sampled over the phase
Every edge carries `source`, `target`, `relation`, and the fields of its attribute structure.

Run from the repository root: `python -m pipeline.export_graph` (pure Python).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.load_model import REPO
from pipeline.segment_phases import GENERATED

import pipeline_paths as paths  # noqa: E402  (generated/py: see `GENERATED`)
import schema  # noqa: E402

PREFIX: dict[str, str] = {
    "bone": "bone",
    "joint": "joint",
    "muscle": "muscle",
    "muscleGroup": "group",
    "ligament": "ligament",
    "nerve": "nerve",
    "movement": "movement",
    "phase": "phase",
    "jointAction": "action",
}
"""Node kind -> id prefix."""

MOVEMENT = "walking"
"""The movement the trial records (anatomy.yaml `movement`)."""


def node_id(kind: str, key: str) -> str:
    return f"{PREFIX[kind]}:{key}"


def build_graph(e: dict[str, Any]) -> dict[str, Any]:
    """The contents of `graph.json`."""
    ent = e["entities"]
    nodes: list[dict[str, Any]] = []
    for kind in schema.KIND:
        for key, n in ent.get(kind, {}).items():
            nodes.append({"id": node_id(kind, key), "kind": kind, **n})

    edges: list[dict[str, Any]] = []

    def edge(rel: str, sk: str, s: str, tk: str, t: str, **attrs: Any) -> None:
        edges.append({"source": node_id(sk, s), "target": node_id(tk, t), "relation": rel, **attrs})

    muscles = e["muscles"]
    for m, a in muscles.items():
        edge("origin", "muscle", m, "bone", a["origin"])
    for m, a in muscles.items():
        edge("insertion", "muscle", m, "bone", a["insertion"])
    coords = e["coordinates"]
    roles = e["roles"]
    for c in roles["crosses"]:
        edge("crosses", "muscle", c["muscle"], "joint", coords[c["coordinate"]]["joint"], coordinate=c["coordinate"], momentArm=c["momentArm"])
    for m, a in muscles.items():
        for g in a["groups"]:
            edge("partOf", "muscle", m, "muscleGroup", g)
    for m, a in muscles.items():
        edge("innervatedBy", "muscle", m, "nerve", a["nerve"])
    for lig, a in e["ligaments"].items():
        for j in a["stabilises"]:
            edge("stabilises", "ligament", lig, "joint", j)
    for j, a in e["joints"].items():
        for b in a["articulates"]:
            edge("articulates", "joint", j, "bone", b)
    for ph in roles["phases"]:
        edge("hasPhase", "movement", MOVEMENT, "phase", ph["phase"], order=ph["order"], startPct=ph["startPct"], endPct=ph["endPct"])

    def action_of(coordinate: str, direction: int) -> str:
        c = coords[coordinate]
        return str(c["positive"] if direction > 0 else c["negative"])

    for ph in roles["phases"]:
        for act in ph["actions"]:
            edge("involves", "phase", ph["phase"], "jointAction", action_of(act["coordinate"], act["direction"]), rangeDeg=round(abs(act["changeDeg"]), 3))
    for c in coords.values():
        for k in ("positive", "negative"):
            edge("actionAt", "jointAction", c[k], "joint", c["joint"])
    for ph in roles["phases"]:
        for act in ph["actions"]:
            a_key = action_of(act["coordinate"], act["direction"])
            for m in act["muscles"]:
                edge(
                    "drivenBy",
                    "jointAction",
                    a_key,
                    "muscle",
                    m["muscle"],
                    phase=node_id("phase", ph["phase"]),
                    role=m["role"],
                    contraction=m["contraction"],
                    peakActivation=m["peakActivation"],
                    activation=m["activation"],
                    momentArm=m["momentArm"],
                )
    return {"schemaVersion": schema.SCHEMA_VERSION, "nodes": nodes, "edges": edges}


def main(argv: Sequence[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="python -m pipeline.export_graph", description=doc.split("\n")[0])
    ap.add_argument("--enriched", type=Path, default=REPO / paths.ENRICHED)
    ap.add_argument("--out", type=Path, default=REPO / paths.KNOWLEDGE_GRAPH)
    a = ap.parse_args(argv)
    graph = build_graph(json.loads(a.enriched.read_text()))
    errors = schema.validate_graph(graph)
    if errors:
        raise ValueError("graph.json fails validate_graph:\n" + "\n".join(errors[:20]))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(graph, separators=(",", ":")) + "\n")
    counts: dict[str, int] = {}
    for ed in graph["edges"]:
        counts[ed["relation"]] = counts.get(ed["relation"], 0) + 1
    print(f"export_graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges {counts}; wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
