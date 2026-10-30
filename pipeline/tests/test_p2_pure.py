"""Pure tests of stages 4–7 (workstream P2): event detection on synthetic signals, the gait DFA
driven over frames, D-002 role classification on hand-made numbers, ontology lookup, graph
assembly, VTP and glTF conversion, quaternions. Standard library and PyYAML only."""
from __future__ import annotations

import base64
import json
import math
from pathlib import Path

import pytest

import gait_fsm
import schema
from pipeline import enrich_anatomy as ea
from pipeline import export_graph, export_meshes, export_muscle_paths, label_roles
from pipeline import segment_phases as sp
from pipeline.load_model import REPO

# ---------------------------------------------------------------------------------------------
# Event detection.


def test_local_extrema_finds_one_peak_per_cycle() -> None:
    x = [math.sin(2 * math.pi * i / 50) + 0.05 * math.sin(2 * math.pi * i / 5) for i in range(200)]
    peaks = sp.local_extrema(x, "max")
    dips = sp.local_extrema(x, "min")
    assert len(peaks) == 4 and len(dips) == 4
    assert all(abs(p - (12.5 + 50 * k)) <= 3 for k, p in enumerate(peaks))
    assert sp.local_extrema([0.0, 1.0, 1.0, 0.0], "max") == [1]
    assert sp.local_extrema([1.0, 0.5, 0.0, 0.5, 0.9, 0.2], "max") == [4]  # first excursion starts outside the data


def test_grf_contacts_skip_clipped_intervals() -> None:
    t = [0.01 * i for i in range(10)]
    fy = [30.0, 30.0, 0.0, 0.0, 50.0, 50.0, 50.0, 0.0, 0.0, 40.0]
    ics, tos = sp.grf_contacts(t, fy, 20.0)
    assert ics == [4, 9] and tos == [2, 7]


def test_merge_events_prefers_force_plates_within_tolerance() -> None:
    t = [0.01 * i for i in range(100)]
    merged = sp.merge_events([10, 50], [12, 80], t, 0.05)
    assert merged == [(12, "grf"), (50, "kinematics")]


def test_heel_off_and_crossings() -> None:
    h = [0.03] * 10 + [0.03 + 0.002 * k for k in range(1, 11)]
    assert sp.detect_heel_off(h, [3], 0.01) == [14]
    d = [-1.0, -0.5, 0.0, 0.5, -0.2, 0.3]
    assert sp.detect_crossing(d, [0]) == [2]
    assert sp.detect_crossing(d, [3]) == [5]


def test_walking_direction_and_along() -> None:
    d = sp.walking_direction([(0.0, 1.0, 0.0), (3.0, 1.0, 4.0)])
    assert d == pytest.approx((0.6, 0.0, 0.8))
    assert sp.along([(1.0, 0.0, 1.0)], [(0.0, 5.0, 0.0)], d) == pytest.approx([1.4])


# ---------------------------------------------------------------------------------------------
# The gait DFA over frames.


def stride_events(start: int = 5, gap: int = 10) -> list[sp.Event]:
    word: tuple[gait_fsm.GaitEvent, ...] = ("initialContact", *gait_fsm.STRIDE_WORD)
    return [sp.Event(e, start + gap * k, "kinematics") for k, e in enumerate(word)]


def test_label_frames_follows_the_stride_word() -> None:
    events = stride_events()
    labels = sp.label_frames(90, events)
    assert labels[:5] == [None] * 5
    assert [labels[5 + 10 * k] for k in range(8)] == [*gait_fsm.PHASES, "loadingResponse"]
    assert labels[14] == "loadingResponse" and labels[15] == "midStance"
    stride, pct = sp.stride_columns([0.01 * i for i in range(90)], labels, events)
    assert stride[4] is None and stride[5] == 0 and stride[85] == 1
    assert pct[5] == 0.0 and pct[40] == pytest.approx(50.0) and pct[85] is None


def test_label_frames_ignores_events_before_the_first_contact() -> None:
    events = [sp.Event("toeOff", 2, "grf"), *stride_events()]
    assert sp.label_frames(90, events)[5] == "loadingResponse"


def test_label_frames_rejects_events_out_of_order() -> None:
    events = stride_events()
    events[2] = sp.Event("toeOff", events[2].frame, "kinematics")
    with pytest.raises(sp.PhaseError, match="toeOff"):
        sp.label_frames(90, events)


def test_phases_csv_round_trip(tmp_path: Path) -> None:
    t = [0.01 * i for i in range(90)]
    events = stride_events()
    labels = sp.label_frames(90, events)
    stride, pct = sp.stride_columns(t, labels, events)
    p = sp.Phases(t, labels, stride, pct, events)
    sp.write_phases(tmp_path / "phases.csv", p)
    q = sp.read_phases(tmp_path / "phases.csv")
    assert q.phase == p.phase and q.stride == p.stride and q.events == p.events
    bounds = label_roles.phase_bounds(q, 0)
    assert [b[0] for b in bounds] == list(gait_fsm.PHASES)
    assert bounds[0][1:] == (5, 15) and bounds[-1][2] == 75


# ---------------------------------------------------------------------------------------------
# D-002 roles.


def config() -> label_roles.Config:
    return label_roles.load_config(REPO / "pipeline" / "config" / "roles.yaml")


def test_roles_yaml_holds_the_d002_thresholds() -> None:
    c = config()
    assert (c.moment_arm_min_m, c.main_mover_min_share, c.helper_min_share) == (0.005, 0.25, 0.05)
    assert (c.antagonist_min_share, c.stabiliser_min_activation, c.stabiliser_max_change_deg) == (0.05, 0.10, 5.0)
    assert c.as_json()["momentArmMinM"] == 0.005
    with pytest.raises(ValueError, match="unknown"):
        label_roles.Config.from_yaml({**c.as_json(), "extra": 1})


def muscle(a: float, r: float, v: float = 0.0, f: float = 1000.0, n: int = 3) -> label_roles.MuscleInPhase:
    return label_roles.MuscleInPhase([a] * n, [r] * n, [v] * n, f)


T = [0.0, 0.05, 0.1]


def test_choose_action() -> None:
    c = config()
    assert label_roles.choose_action(12.0, -5.0, c) == (1, False)
    assert label_roles.choose_action(-6.0, 5.0, c) == (-1, False)
    assert label_roles.choose_action(2.0, -5.0, c) == (-1, True)
    assert label_roles.choose_action(-2.0, 0.0, c) == (1, True)


def test_classify_by_moment_share() -> None:
    c = config()
    ms = {
        "big": muscle(0.5, 0.04),  # moment 20 N·m: 20/26 of the agonist moment
        "mid": muscle(0.1, 0.04),  # 4 N·m: 15 %
        "small": muscle(0.05, 0.04),  # 2 N·m: 7.7 %
        "tiny": muscle(0.01, 0.01),  # 0.1 N·m, under 5 % of 26.1
        "short": muscle(0.9, 0.004),  # moment arm under 5 mm: counts nowhere
        "anta": muscle(0.3, -0.02),  # opposing, 6 N·m: 100 % of the opposing moment
    }
    shares = {k: label_roles.moment_integrals(T, m, 1, c.moment_arm_min_m) for k, m in ms.items()}
    total = label_roles.Shares(sum(s.agonist for s in shares.values()), sum(s.opposing for s in shares.values()))
    roles = {k: label_roles.classify(T, m, shares[k], total, False, c) for k, m in ms.items()}
    assert roles["big"] is not None and roles["big"][0] == "mainMover"
    assert roles["mid"] is not None and roles["mid"][0] == "helper"
    assert roles["small"] is not None and roles["small"][0] == "helper"
    assert roles["tiny"] is None and roles["short"] is None
    assert roles["anta"] is not None and roles["anta"][0] == "antagonist" and roles["anta"][1] == pytest.approx(1.0)
    # The same muscles while the coordinate holds still: active ones (≥ 0.1) stabilise.
    stab = {k: label_roles.classify(T, m, shares[k], total, True, c) for k, m in ms.items()}
    assert stab["big"] is not None and stab["big"][0] == "stabiliser"
    assert stab["anta"] is not None and stab["anta"][0] == "stabiliser"
    assert stab["short"] is None  # moment arm under 5 mm throughout
    assert stab["small"] is not None and stab["small"][0] == "helper"  # activation 0.05


def test_moment_arm_sign_change_splits_the_integrals() -> None:
    c = config()
    m = label_roles.MuscleInPhase([1.0, 1.0, 1.0], [0.02, 0.0, -0.02], [0.0] * 3, 100.0)
    s = label_roles.moment_integrals(T, m, 1, c.moment_arm_min_m)
    assert s.agonist == pytest.approx(0.05) and s.opposing == pytest.approx(0.05)


def test_contraction_from_activation_weighted_velocity() -> None:
    c = config()
    m = label_roles.MuscleInPhase([0.0, 1.0, 0.0], [0.02] * 3, [-0.5, 0.05, -0.5], 100.0)
    v = label_roles.mean_velocity(T, m)
    assert v == pytest.approx(0.05)
    assert label_roles.contraction(v, c) == "eccentric"
    assert label_roles.contraction(-0.05, c) == "concentric"
    assert label_roles.contraction(0.005, c) == "isometric"


def test_sample_spans_the_phase() -> None:
    assert label_roles.sample([0.0, 1.0], [0.0, 2.0], 0.0, 1.0, 5) == pytest.approx([0.0, 0.5, 1.0, 1.5, 2.0])


# ---------------------------------------------------------------------------------------------
# Ontologies and graph.

OBO = """format-version: 1.2
data-version: releases/2026-10-01

[Term]
id: UBERON:0001371
name: gluteus medius
synonym: "gluteus medius muscle" RELATED []
xref: FMA:22315

[Term]
id: UBERON:0000001
name: old term
synonym: "gluteus medius" EXACT []
is_obsolete: true

[Typedef]
id: part_of
"""


def test_obo_lookup_and_subset(tmp_path: Path) -> None:
    header, terms = ea.parse_obo(OBO)
    onto = ea.Ontology(terms, "x")
    assert onto.lookup("Gluteus Medius") == "UBERON:0001371"
    assert onto.lookup("gluteus medius muscle") == "UBERON:0001371"
    assert onto.lookup("femur") is None
    out = tmp_path / "u.obo"
    assert ea.write_obo_subset(out, header, terms) == 1
    assert ea.read_uberon(out).version == "releases/2026-10-01"


def test_fma_subset_round_trip(tmp_path: Path) -> None:
    terms = [ea.Term("FMA:22330", "Right gluteus medius", [("Right gluteus medius muscle", "synonym")]), ea.Term("FMA:22315", "Gluteus medius")]
    out = tmp_path / "f.owl"
    ea.write_fma_subset(out, "5.1.0", terms)
    onto = ea.read_fma(out)
    assert onto.version == "5.1.0"
    _, fma_terms = ea.lookup_terms("muscle", "glmed1_r", {"name": "gluteus medius (anterior part)", "ontologyName": "gluteus medius"})
    assert fma_terms == ["right gluteus medius", "gluteus medius"]
    assert next(x for x in map(onto.lookup, fma_terms) if x) == "FMA:22330"
    assert onto.lookup("gluteus medius") == "FMA:22315"


def tiny_enriched() -> dict[str, object]:
    def ent(name: str, side: str = "right") -> dict[str, object]:
        return {"name": name, "commonName": None, "side": side, "uberonId": None, "fmaId": None, "opensimName": None}

    roles = {
        "config": {"coordinates": ["knee_angle_r"]},
        "crosses": [{"muscle": "vaslat_r", "coordinate": "knee_angle_r", "momentArm": [-0.04, -0.045]}],
        "phases": [
            {
                "phase": "loadingResponse", "order": 0, "startPct": 0.0, "endPct": 15.0,
                "actions": [
                    {
                        "coordinate": "knee_angle_r", "direction": 1, "changeDeg": 19.9, "stabilised": False,
                        "muscles": [{"muscle": "vaslat_r", "role": "antagonist", "contraction": "eccentric", "peakActivation": 0.2, "activation": [0.1, 0.2], "momentArm": [-0.04, -0.045]}],
                    }
                ],
            }
        ],
    }
    return {
        "roles": roles,
        "entities": {
            "bone": {"femur_r": ent("femur"), "patella_r": ent("patella"), "tibia_r": ent("tibia")},
            "joint": {"knee_r": ent("knee joint")},
            "muscle": {"vaslat_r": ent("vastus lateralis")},
            "muscleGroup": {"quadriceps_r": ent("quadriceps femoris")},
            "ligament": {"acl_r": ent("anterior cruciate ligament")},
            "nerve": {"femoral_r": ent("femoral nerve")},
            "jointAction": {"knee_flexion_r": ent("knee flexion"), "knee_extension_r": ent("knee extension")},
            "phase": {"loadingResponse": ent("loading response", "midline")},
            "movement": {"walking": ent("walking", "midline")},
        },
        "muscles": {"vaslat_r": {"origin": "femur_r", "insertion": "patella_r", "groups": ["quadriceps_r"], "nerve": "femoral_r"}},
        "joints": {"knee_r": {"articulates": ["femur_r", "tibia_r", "patella_r"]}},
        "ligaments": {"acl_r": {"stabilises": ["knee_r"]}},
        "coordinates": {"knee_angle_r": {"joint": "knee_r", "positive": "knee_flexion_r", "negative": "knee_extension_r"}},
    }


def test_build_graph_is_well_typed_and_uses_every_relation() -> None:
    g = export_graph.build_graph(tiny_enriched())
    assert schema.validate_graph(g) == []
    assert {e["relation"] for e in g["edges"]} == set(schema.RELATIONS)
    driven = next(e for e in g["edges"] if e["relation"] == "drivenBy")
    assert driven["source"] == "action:knee_flexion_r" and driven["phase"] == "phase:loadingResponse"
    involves = next(e for e in g["edges"] if e["relation"] == "involves")
    assert involves["rangeDeg"] == pytest.approx(19.9)


def test_check_attachment_keeps_curation_on_the_model_path() -> None:
    bones = {"patella_r": {"body": "patella_r"}, "fibula_r": {"body": "tibia_r"}}
    ea.check_attachment("vaslat_r", "insertion", "patella_r", bones, ["femur_r", "patella_r", "tibia_r"])
    with pytest.raises(ValueError, match="off the model path"):
        ea.check_attachment("glmed1_r", "origin", "fibula_r", bones, ["pelvis", "femur_r"])


def test_curated_anatomy_covers_the_right_leg() -> None:
    a = ea.load_anatomy(REPO / "data" / "curated" / "anatomy.yaml")
    assert len(a["muscles"]) == 40 and all(k.endswith("_r") for k in a["muscles"])
    assert {"acl_r", "pcl_r", "mcl_r", "lcl_r", "iliofemoral_r", "ischiofemoral_r", "pubofemoral_r", "atfl_r", "deltoid_r"} <= set(a["ligaments"])
    assert set(a["phases"]) == set(gait_fsm.PHASES)
    for m in a["muscles"].values():
        assert m["nerve"] in a["nerves"] and all(g in a["groups"] for g in m["groups"])
        for k in ("origin", "insertion"):
            assert m.get(k, "femur_r") in a["bones"]


# ---------------------------------------------------------------------------------------------
# Meshes and muscle paths.

VTP = """<?xml version="1.0"?>
<VTKFile type="PolyData" version="0.1" byte_order="LittleEndian">
 <PolyData><Piece NumberOfPoints="4" NumberOfPolys="1">
  <Points><DataArray type="Float32" NumberOfComponents="3" format="ascii">0 0 0 1 0 0 1 1 0 0 1 0</DataArray></Points>
  <Polys>
   <DataArray type="Int32" Name="connectivity" format="ascii">0 1 2 3</DataArray>
   <DataArray type="Int32" Name="offsets" format="ascii">4</DataArray>
  </Polys>
 </Piece></PolyData>
</VTKFile>
"""


def test_vtp_to_gltf(tmp_path: Path) -> None:
    (tmp_path / "quad.vtp").write_text(VTP)
    m = export_meshes.read_vtp(tmp_path / "quad.vtp", (2.0, 3.0, 1.0))
    assert m.positions[2] == (2.0, 3.0, 0.0)
    assert m.triangles == [(0, 1, 2), (0, 2, 3)]
    assert m.normals[0] == pytest.approx((0.0, 0.0, 1.0))
    doc = export_meshes.gltf_document("quad", [("quad.vtp", m)])
    blob = base64.b64decode(doc["buffers"][0]["uri"].split(",", 1)[1])
    assert len(blob) == doc["buffers"][0]["byteLength"]
    pos = doc["accessors"][0]
    assert pos["count"] == 4 and pos["max"] == [2.0, 3.0, 0.0]
    assert doc["accessors"][2]["count"] == 6
    json.dumps(doc)


def test_quaternion_and_merge() -> None:
    q = export_muscle_paths.quaternion
    assert q([[1, 0, 0], [0, 1, 0], [0, 0, 1]]) == pytest.approx((0.0, 0.0, 0.0, 1.0))
    s = math.sqrt(0.5)
    assert q([[0, -1, 0], [1, 0, 0], [0, 0, 1]]) == pytest.approx((0.0, 0.0, s, s))  # 90° about z
    assert q([[1, 0, 0], [0, -1, 0], [0, 0, -1]]) == pytest.approx((1.0, 0.0, 0.0, 0.0))  # 180° about x
    pts = [(0.0, 0.0, 0.0), (0.0005, 0.0, 0.0), (0.01, 0.0, 0.0), (0.0104, 0.0, 0.0)]
    assert export_muscle_paths.merge_close(pts, 0.001) == [(0.0, 0.0, 0.0), (0.0104, 0.0, 0.0)]
    assert export_muscle_paths.frame_step(100.0) == 2 and export_muscle_paths.frame_step(60.0) == 1
