"""Stages 4–7 on the real walking trial: plausibility of events, phases, roles, and outputs.

The fixture runs stages 1–3 (P1) and 4–7 into a temporary directory (≈ 30 s) and skips when
`opensim` is unimportable. Without the ontology subsets (`data/raw/ontology/fetch.sh`), the
fixture runs `enrichAnatomy` on empty Uberon and FMA files, so every ontology id is `null`.

Plausible ranges (percent of the stride), wider than textbook values (Perry: loading response
0–10 %, stance ≈ 60 %) because this subject's double support is long: the force plates measure
opposite toe-off at 14.8 % of the second stride, and stance at 65 %.
"""
from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import gait_fsm
import schema
from pipeline.load_model import REPO, read_csv

LOADING_RESPONSE_END = (8.0, 18.0)
STANCE_END = (55.0, 68.0)
QUADRICEPS = ("vasint_r", "vaslat_r", "vasmed_r", "recfem_r")
GLMED = ("glmed1_r", "glmed2_r", "glmed3_r")
EMPTY_OWL = '<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>\n'


class Out:
    def __init__(self, d: Path) -> None:
        self.dir = d
        self.roles: dict[str, Any] = json.loads((d / "roles.json").read_text())
        self.graph: dict[str, Any] = json.loads((d / "graph.json").read_text())
        self.meshes: dict[str, Any] = json.loads((d / "meshes" / "index.json").read_text())
        self.paths: dict[str, Any] = json.loads((d / "muscle_paths.json").read_text())

    def phase(self, name: str) -> dict[str, Any]:
        return next(p for p in self.roles["phases"] if p["phase"] == name)

    def action(self, phase: str, coordinate: str) -> dict[str, Any]:
        return next(a for a in self.phase(phase)["actions"] if a["coordinate"] == coordinate)


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Out]:
    pytest.importorskip("opensim")
    from pipeline import enrich_anatomy, export_graph, export_meshes, export_muscle_paths, label_roles, load_model, moment_arms, segment_phases, static_opt

    d = tmp_path_factory.mktemp("p2")
    w = {k: str(d / k) for k in ("model.json", "kinematics.csv", "grf.csv", "activations.csv", "moment_arms.csv", "mt_lengths.csv", "phases.csv", "roles.json", "enriched.json", "graph.json", "muscle_paths.json")}
    assert load_model.main(["--out-model", w["model.json"], "--out-kinematics", w["kinematics.csv"], "--out-grf", w["grf.csv"]]) == 0
    assert static_opt.main(["--kinematics", w["kinematics.csv"], "--out-activations", w["activations.csv"], "--out-forces", str(d / "forces.csv"), "--out-settings", str(d / "static_opt.json"), "--scratch", str(d / "so")]) == 0
    assert moment_arms.main(["--kinematics", w["kinematics.csv"], "--out-moment-arms", w["moment_arms.csv"], "--out-lengths", w["mt_lengths.csv"]]) == 0
    assert segment_phases.main(["--kinematics", w["kinematics.csv"], "--grf", w["grf.csv"], "--out", w["phases.csv"]]) == 0
    common = ["--activations", w["activations.csv"], "--mt-lengths", w["mt_lengths.csv"]]
    assert label_roles.main([*common, "--moment-arms", w["moment_arms.csv"], "--phases", w["phases.csv"], "--kinematics", w["kinematics.csv"], "--model", w["model.json"], "--out", w["roles.json"]]) == 0
    onto = REPO / "data" / "raw" / "ontology"
    uberon, fma = onto / "uberon.obo", onto / "fma.owl"
    if not (uberon.exists() and fma.exists()):
        uberon, fma = d / "uberon.obo", d / "fma.owl"
        uberon.write_text("format-version: 1.2\n")
        fma.write_text(EMPTY_OWL)
    assert enrich_anatomy.main(["--roles", w["roles.json"], "--model", w["model.json"], "--uberon", str(uberon), "--fma", str(fma), "--out", w["enriched.json"]]) == 0
    assert export_graph.main(["--enriched", w["enriched.json"], "--out", w["graph.json"]]) == 0
    assert export_meshes.main(["--model", w["model.json"], "--out", str(d / "meshes" / "index.json")]) == 0
    assert export_muscle_paths.main([*common, "--kinematics", w["kinematics.csv"], "--phases", w["phases.csv"], "--out", w["muscle_paths.json"]]) == 0
    yield Out(d)


def test_event_order_matches_the_stride_word(out: Out) -> None:
    events = [e["event"] for e in out.roles["events"]]
    assert events == ["initialContact", *gait_fsm.STRIDE_WORD]
    times = [e["time"] for e in out.roles["events"]]
    assert times == sorted(times)
    assert times[0] == pytest.approx(0.27, abs=0.015) and times[-1] == pytest.approx(1.42, abs=0.015)


def test_phase_percentages_are_plausible(out: Out) -> None:
    ph = {p["phase"]: p for p in out.roles["phases"]}
    assert [p["phase"] for p in out.roles["phases"]] == list(gait_fsm.PHASES)
    assert ph["loadingResponse"]["startPct"] == 0.0 and ph["terminalSwing"]["endPct"] == 100.0
    lo, hi = LOADING_RESPONSE_END
    assert lo <= ph["loadingResponse"]["endPct"] <= hi
    lo, hi = STANCE_END
    assert lo <= ph["preSwing"]["endPct"] <= hi
    for p in out.roles["phases"]:
        assert p["endPct"] > p["startPct"]


def test_gluteus_medius_works_in_single_leg_stance(out: Out) -> None:
    """Single-leg stance (mid-stance, terminal stance): gluteus medius holds the pelvis level
    over the stance leg, in hip abduction / adduction."""
    for phase in ("midStance", "terminalStance"):
        act = out.action(phase, "hip_adduction_r")
        roles = {m["muscle"]: m["role"] for m in act["muscles"]}
        assert set(GLMED) & set(roles), phase
        assert roles.get("glmed1_r") in ("mainMover", "helper", "stabiliser"), phase


def test_quadriceps_brake_knee_flexion_in_loading_response(out: Out) -> None:
    """The knee flexes in loading response while the quadriceps lengthen (eccentric braking).
    A quadriceps muscle with a role there is an eccentric antagonist. In this trial static
    optimisation keeps every quadriceps muscle under the D-004 activation floor (0.05) in
    loading response (vastus lateralis 0.046), so the roles may list none of them."""
    act = out.action("loadingResponse", "knee_angle_r")
    assert act["direction"] == 1 and not act["stabilised"]  # the knee flexes
    ph = out.phase("loadingResponse")
    velocity: dict[str, list[float]] = {}
    with (out.dir / "mt_lengths.csv").open() as f:
        for row in csv.DictReader(f):
            if row["muscle"] in QUADRICEPS and ph["start"] - 1e-9 <= float(row["time"]) <= ph["end"] + 1e-9:
                velocity.setdefault(row["muscle"], []).append(float(row["velocity"]))
    for m in ("vaslat_r", "vasmed_r", "vasint_r"):
        assert sum(velocity[m]) / len(velocity[m]) > 0.0, m  # lengthening
    for m in act["muscles"]:
        if m["muscle"] in QUADRICEPS:
            assert m["role"] == "antagonist" and m["contraction"] == "eccentric", m["muscle"]


def test_roles_record_the_thresholds(out: Out) -> None:
    c = out.roles["config"]
    assert (c["momentArmMinM"], c["mainMoverMinShare"], c["helperMinShare"], c["antagonistMinShare"], c["stabiliserMinActivation"], c["stabiliserMaxChangeDeg"]) == (0.005, 0.25, 0.05, 0.05, 0.1, 5.0)
    assert c["roleMinActivation"] == 0.05
    for p in out.roles["phases"]:
        for a in p["actions"]:
            for m in a["muscles"]:
                assert len(m["activation"]) == len(m["momentArm"]) == c["samplesPerPhase"]
                floor = c["stabiliserMinActivation"] if m["role"] == "stabiliser" else c["roleMinActivation"]
                assert m["meanActivation"] >= floor - 1e-4, (p["phase"], a["coordinate"], m["muscle"])


def test_graph_is_well_typed(out: Out) -> None:
    g = out.graph
    assert schema.validate_graph(g) == []
    relations = {e["relation"] for e in g["edges"]}
    assert relations == set(schema.RELATIONS)
    driven = [e for e in g["edges"] if e["relation"] == "drivenBy"]
    total = sum(len(a["muscles"]) for p in out.roles["phases"] for a in p["actions"])
    assert len(driven) == total
    ids = {n["id"] for n in g["nodes"]}
    assert {"muscle:glmed1_r", "bone:femur_r", "joint:knee_r", "movement:walking", "phase:midStance"} <= ids


def test_meshes_are_scaled_gltf(out: Out) -> None:
    idx = out.meshes
    assert idx["format"] == "bm-meshes/1" and len(idx["bodies"]) == 13
    pelvis = idx["bodies"][0]
    assert pelvis["body"] == "pelvis" and pelvis["meshes"][0]["scaleFactors"] != [1.0, 1.0, 1.0]
    for b in idx["bodies"]:
        doc = json.loads((out.dir / "meshes" / b["file"]).read_text())
        assert doc["asset"]["version"] == "2.0"
        assert sum(a["count"] for a in doc["accessors"][2::3]) == 3 * b["triangles"]


def test_muscle_paths_match_opensim_lengths(out: Out) -> None:
    """The exported polyline (wrap arcs included) has the muscle-tendon length OpenSim reports."""
    p = out.paths
    assert p["rateHz"] <= 60 and len(p["time"]) == len(p["bodies"]["femur_r"])
    assert p["stride"] == {"start": out.roles["stride"]["start"], "end": out.roles["stride"]["end"]}
    assert (out.dir / "muscle_paths.json").stat().st_size < 20e6
    lengths: dict[str, dict[float, float]] = {}
    with (out.dir / "mt_lengths.csv").open() as f:
        for row in csv.DictReader(f):
            lengths.setdefault(row["muscle"], {})[round(float(row["time"]), 6)] = float(row["length"])
    for m in ("glmed1_r", "gasmed_r", "vaslat_r", "iliacus_r", "addmagIsch_r"):
        for k in (0, len(p["time"]) // 2):
            xs = p["muscles"][m]["points"][k]
            pts = [xs[i : i + 3] for i in range(0, len(xs), 3)]
            poly = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
            assert poly == pytest.approx(lengths[m][round(p["time"][k], 6)], rel=0.02), m
    kin = read_csv(out.dir / "kinematics.csv")
    assert len(p["time"]) == math.ceil(len(kin.time) / 2)
