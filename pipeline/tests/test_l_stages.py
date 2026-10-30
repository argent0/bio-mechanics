"""The left leg on the real walking trial (workstream L): mirrored anatomy in the graph, the left
events and their sources, and the mirrored teaching examples on the reference timeline (D-007).

The fixture runs the pipeline into a temporary directory (≈ 30 s) and skips when `opensim` is
unimportable; without the ontology subsets it runs `enrichAnatomy` on empty Uberon and FMA
files, as `test_p2_stages.py` does.

Each teaching example names the reference phase it reads by the event that opens it, found in
`roles.json` `events` (`opened_by`): the left leg's own phases sit about half a stride after the
right leg's (`label_roles` module docstring, "One timeline for both legs").
  - Left loading response: from left initial contact (`oppositeInitialContact`) to right
    toe-off, the reference pre-swing.
  - Left single-leg stance: from right toe-off to right initial contact, the reference initial,
    mid- and terminal swing; the reference initial swing (opened by `toeOff`) holds the start of
    the left mid-stance.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import schema
from pipeline.load_model import REPO
from pipeline.segment_phases import read_phases
import pipeline_paths as paths

LEG_MODEL = ["--model", str(REPO / paths.SCALED_MODEL)]
"""These stages run on the scaled Rajagopal model (legs only, 80 muscles) and its raw inverse
kinematics: the fixtures pin the leg results the merged model must keep (workstream M)."""

EMPTY_OWL = '<?xml version="1.0"?>\n<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>\n'
VASTI_L = ("vaslat_l", "vasmed_l", "vasint_l")
ADDMAG_L = {"addmagDist_l", "addmagIsch_l", "addmagMid_l", "addmagProx_l"}
SINGLE_LEG_STANCE_L = ("initialSwing", "midSwing", "terminalSwing")
"""The reference phases from right toe-off to right initial contact: the left foot alone on the
ground."""


class Out:
    def __init__(self, d: Path) -> None:
        self.dir = d
        self.roles: dict[str, Any] = json.loads((d / "roles.json").read_text())
        self.graph: dict[str, Any] = json.loads((d / "graph.json").read_text())
        self.dynamics: dict[str, Any] = json.loads((d / "dynamics.json").read_text())

    def opened_by(self, event: str) -> str:
        """The reference phase of the stride whose start is the time of `event`."""
        t = next(e["time"] for e in self.roles["events"] if e["event"] == event)
        return str(next(p["phase"] for p in self.roles["phases"] if p["start"] == t))

    def action(self, phase: str, coordinate: str) -> dict[str, Any]:
        ph = next(p for p in self.roles["phases"] if p["phase"] == phase)
        return next(a for a in ph["actions"] if a["coordinate"] == coordinate)

    def roles_in(self, phase: str, coordinate: str) -> dict[str, tuple[str, str]]:
        return {m["muscle"]: (m["role"], m["contraction"]) for m in self.action(phase, coordinate)["muscles"]}


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Out]:
    pytest.importorskip("opensim")
    from pipeline import enrich_anatomy, export_dynamics, export_graph, label_roles, load_model, moment_arms, segment_phases, static_opt

    d = tmp_path_factory.mktemp("l")
    w = {k: str(d / k) for k in ("model.json", "kinematics.csv", "grf.csv", "activations.csv", "moment_arms.csv", "mt_lengths.csv", "phases.csv", "roles.json", "enriched.json", "graph.json", "dynamics.json")}
    assert load_model.main([*LEG_MODEL, "--ik", str(REPO / paths.IK_MOTION), "--out-model", w["model.json"], "--out-kinematics", w["kinematics.csv"], "--out-grf", w["grf.csv"]]) == 0
    assert static_opt.main([*LEG_MODEL, "--kinematics", w["kinematics.csv"], "--out-activations", w["activations.csv"], "--out-forces", str(d / "forces.csv"), "--out-settings", str(d / "static_opt.json"), "--scratch", str(d / "so")]) == 0
    assert moment_arms.main([*LEG_MODEL, "--kinematics", w["kinematics.csv"], "--out-moment-arms", w["moment_arms.csv"], "--out-lengths", w["mt_lengths.csv"]]) == 0
    assert segment_phases.main([*LEG_MODEL, "--kinematics", w["kinematics.csv"], "--grf", w["grf.csv"], "--out", w["phases.csv"]]) == 0
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
    assert export_dynamics.main([*common, "--moment-arms", w["moment_arms.csv"], "--phases", w["phases.csv"], "--kinematics", w["kinematics.csv"], "--model", w["model.json"], "--out", w["dynamics.json"]]) == 0
    yield Out(d)


# ---------------------------------------------------------------------------------------------
# Mirrored anatomy in the graph.


def test_graph_holds_forty_muscles_per_leg(out: Out) -> None:
    g = out.graph
    assert schema.validate_graph(g) == []
    muscles = [n for n in g["nodes"] if n["kind"] == "muscle"]
    left = sorted(n["id"] for n in muscles if n["side"] == "left")
    right = sorted(n["id"] for n in muscles if n["side"] == "right")
    assert len(left) == len(right) == 40
    assert left == sorted(i[:-2] + "_l" for i in right)


def test_left_nodes_mirror_their_right_twin(out: Out) -> None:
    nodes = {n["id"]: n for n in out.graph["nodes"]}
    left = [i for i in nodes if i.endswith("_l")]
    assert left and all(nodes[i]["side"] == "left" for i in left)
    for i in left:
        l, r = nodes[i], nodes[i[:-2] + "_r"]
        for k in ("kind", "name", "commonName", "region", "uberonId"):
            assert l[k] == r[k], (i, k)
        assert (l["opensimName"] is None) == (r["opensimName"] is None), i
        if r["opensimName"] is not None:
            assert l["opensimName"] == r["opensimName"][:-2] + "_l", i


def test_left_edges_mirror_the_right_structure(out: Out) -> None:
    """origin, insertion, partOf, innervatedBy, stabilises, articulates and actionAt of the left
    leg are the right leg's edges with each `_r` turned to `_l`."""
    rels = {"origin", "insertion", "partOf", "innervatedBy", "stabilises", "articulates", "actionAt"}

    def mirror(x: str) -> str:
        return x[:-2] + "_l" if x.endswith("_r") else x

    edges = [e for e in out.graph["edges"] if e["relation"] in rels]
    right = {(mirror(e["source"]), e["relation"], mirror(e["target"])) for e in edges if e["source"].endswith("_r")}
    left = {(e["source"], e["relation"], e["target"]) for e in edges if e["source"].endswith("_l")}
    assert left == right and len(left) == 200  # 40 + 40 + 44 + 40 + 13 + 13 + 10


def test_left_dynamics_follow_the_right(out: Out) -> None:
    coords = [c["coordinate"] for c in out.dynamics["coordinates"]]
    assert coords[5:] == [c[:-2] + "_l" for c in coords[:5]]
    knee = next(c for c in out.dynamics["coordinates"] if c["coordinate"] == "knee_angle_l")
    assert (knee["joint"], knee["positive"]) == ("joint:knee_l", "action:knee_flexion_l")
    assert knee["moments"] and all(m.endswith("_l") for m in knee["moments"])


# ---------------------------------------------------------------------------------------------
# Left events.


def test_left_events_come_from_the_plate_at_its_contact_and_from_markers_elsewhere(out: Out) -> None:
    """The left foot stands on a force plate from 0.84 s to 1.58 s: the left events at the
    plate contact come from the plate, the others from the markers (`label_roles` docstring)."""
    p = read_phases(out.dir / "phases.csv")
    left = [(e.event, round(p.time[e.frame], 2), e.source) for e in p.events if e.event in ("oppositeToeOff", "oppositeInitialContact")]
    assert left == [
        ("oppositeToeOff", 0.45, "kinematics"),
        ("oppositeInitialContact", 0.84, "grf"),
        ("oppositeToeOff", 1.59, "grf"),
        ("oppositeInitialContact", 1.97, "kinematics"),
    ]


# ---------------------------------------------------------------------------------------------
# Mirrored teaching examples.


def test_left_loading_response_sits_in_the_reference_pre_swing(out: Out) -> None:
    assert out.opened_by("oppositeInitialContact") == "preSwing"
    assert out.opened_by("toeOff") == "initialSwing"


def test_left_vasti_brake_knee_flexion_in_left_loading_response(out: Out) -> None:
    """The right leg's teaching example on the left: in the left loading response the left knee
    flexes under load while the left vasti lengthen and resist it (eccentric antagonists)."""
    phase = out.opened_by("oppositeInitialContact")
    act = out.action(phase, "knee_angle_l")
    assert act["direction"] == 1 and not act["stabilised"]
    roles = out.roles_in(phase, "knee_angle_l")
    for v in VASTI_L:
        assert roles.get(v) == ("antagonist", "eccentric"), (v, roles)
    assert roles["semimem_l"][0] == "mainMover"  # as semimembranosus in the right loading response


def test_left_gluteus_medius_holds_the_pelvis_in_left_single_leg_stance(out: Out) -> None:
    """The left foot alone on the ground: the left hip abductors hold the pelvis level, so the
    hip's adduction coordinate holds still, gluteus medius 1 stabilises it, and the muscles' net
    moment about it points toward abduction (negative) at every frame."""
    for phase in SINGLE_LEG_STANCE_L:
        act = out.action(phase, "hip_adduction_l")
        assert act["stabilised"] and act["direction"] == -1, phase
        assert out.roles_in(phase, "hip_adduction_l").get("glmed1_l", ("",))[0] == "stabiliser", phase
        hip = next(c for c in out.dynamics["coordinates"] if c["coordinate"] == "hip_adduction_l")
        ph = next(p for p in out.roles["phases"] if p["phase"] == phase)
        frames = [i for i, t in enumerate(out.dynamics["time"]) if ph["start"] <= t <= ph["end"]]
        assert frames and all(sum(m[i] for m in hip["moments"].values()) < 0 for i in frames), phase


GASMED_L_FLOOR_BAND = 0.01
"""The medial gastrocnemius's phase mean lies within this fraction of the D-006 floor (0.05)."""


def test_left_calf_brakes_ankle_dorsiflexion_early_in_left_mid_stance(out: Out) -> None:
    """The left tibia rolls forward over the planted left foot while soleus lengthens and resists
    it (eccentric antagonist). The medial gastrocnemius sits at the D-006 floor there (phase mean
    0.04997 with the exact static optimisation, 0.05021 with OpenSim's IPOPT): it brakes with
    soleus when its mean reaches 0.05 and takes no role below. The lateral gastrocnemius sits at
    mean activation ≈ 0.027, under the floor (0.05, or 25 % of its 0.37 stride peak), and takes
    no role: on the right leg all three calf muscles brake in mid-stance."""
    from pipeline.label_roles import trapezoid
    from pipeline.load_model import read_csv

    phase = out.opened_by("toeOff")
    act = out.action(phase, "ankle_angle_l")
    assert act["direction"] == 1 and not act["stabilised"]
    roles = out.roles_in(phase, "ankle_angle_l")
    assert roles.get("soleus_l") == ("antagonist", "eccentric"), roles
    ph = next(p for p in out.roles["phases"] if p["phase"] == phase)
    a = read_csv(out.dir / "activations.csv")
    frames = [i for i, t in enumerate(a.time) if ph["start"] <= t <= ph["end"]]
    t = [a.time[i] for i in frames]
    mean = trapezoid(t, [a.columns["gasmed_l"][i] for i in frames]) / (t[-1] - t[0])
    assert abs(mean - 0.05) < GASMED_L_FLOOR_BAND * 0.05, mean
    assert roles.get("gasmed_l") == (("antagonist", "eccentric") if mean >= 0.05 else None), (mean, roles)
    assert "gaslat_l" not in roles


def test_left_tibialis_anterior_and_adductor_magnus_rest_in_left_mid_stance(out: Out) -> None:
    phase = out.opened_by("toeOff")
    assert out.roles_in(phase, "ankle_angle_l").get("tibant_l", ("",))[0] not in ("mainMover", "helper")
    assert not set(out.roles_in(phase, "hip_adduction_l")) & ADDMAG_L
