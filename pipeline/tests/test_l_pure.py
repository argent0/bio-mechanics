"""Pure tests of the left leg (workstream L): mirroring of the curated right side in code
(`enrich_anatomy.with_left`), the leg of each coordinate (`label_roles.muscles_of`), the left
coordinates of dynamics.json, and the size of the committed output. Standard library and
PyYAML only."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pytest

import gait_fsm
from pipeline import enrich_anatomy as ea
from pipeline import export_dynamics, export_muscle_paths, label_roles
from pipeline import segment_phases as sp
from pipeline.load_model import REPO

ANATOMY = REPO / "data" / "curated" / "anatomy.yaml"
OUT_LIMIT_BYTES = 8_000_000
"""`data/out/` stays under 8 MB in total (plan.md, W2)."""


def anatomy() -> dict[str, Any]:
    return ea.load_anatomy(ANATOMY)


def config() -> label_roles.Config:
    return label_roles.load_config(REPO / "pipeline" / "config" / "roles.yaml")


def stride_events(start: int = 5, gap: int = 10) -> list[sp.Event]:
    word: tuple[gait_fsm.GaitEvent, ...] = ("initialContact", *gait_fsm.STRIDE_WORD)
    return [sp.Event(e, start + gap * k, "kinematics") for k, e in enumerate(word)]


def test_side_and_mirror_of_names() -> None:
    assert [ea.side_of(k) for k in ("vaslat_r", "vaslat_l", "pelvis")] == ["right", "left", "midline"]
    assert [ea.mirror_name(k) for k in ("vaslat_r", "walker_knee_r", "pelvis")] == ["vaslat_l", "walker_knee_l", "pelvis"]
    assert ea.mirror_text("long head of right biceps femoris") == "long head of left biceps femoris"
    assert ea.mirror_text("Right knee joint") == "Left knee joint"
    assert ea.mirror_text("medial cuneiform bone") == "medial cuneiform bone"


def test_every_right_entry_gains_one_left_twin() -> None:
    a = anatomy()
    m = ea.with_left(a)
    for section in ea.MIRRORED_SECTIONS:
        right = [k for k in a[section] if ea.side_of(k) == "right"]
        left = [k for k in m[section] if ea.side_of(k) == "left"]
        assert left == [ea.mirror_name(k) for k in right], section
        assert list(m[section])[: len(a[section])] == list(a[section]), section  # right entries first, unchanged
    assert len([k for k in m["muscles"] if k.endswith("_l")]) == 231 == len([k for k in m["muscles"] if k.endswith("_r")])
    for section in ("regions", "phases", "movement"):
        assert m[section] == a[section]


def test_left_entries_mirror_their_right_entry() -> None:
    m = ea.with_left(anatomy())
    assert m["muscles"]["vaslat_l"] == {"name": "vastus lateralis", "commonName": "outer quad", "groups": ["quadriceps_l", "anteriorThigh_l"], "nerve": "femoral_l", "insertion": "patella_l"}
    assert m["muscles"]["bflh_l"]["fmaName"] == "long head of left biceps femoris"
    assert m["joints"]["knee_l"] == {"name": "knee joint", "commonName": "knee", "opensim": ["walker_knee_l", "patellofemoral_l"], "articulates": ["femur_l", "tibia_l", "patella_l"]}
    assert m["joints"]["hip_l"]["articulates"] == ["pelvis", "femur_l"]  # the midline pelvis stays single
    assert m["coordinates"]["knee_angle_l"] == {"joint": "knee_l", "positive": "knee_flexion_l", "negative": "knee_extension_l"}
    assert m["bones"]["fibula_l"]["body"] == "tibia_l" and m["bodies"]["calcn_l"] == "calcaneus_l"
    assert m["ligaments"]["calcaneofibular_l"]["stabilises"] == ["ankle_l", "subtalar_l"]
    # Every reference of a left entry names a left or midline entry.
    for key, e in m["muscles"].items():
        if key.endswith("_l"):
            refs = [*e["groups"], e["nerve"], e.get("origin", "pelvis"), e.get("insertion", "pelvis")]
            assert all(ea.side_of(r) in ("left", "midline") for r in refs), key


def test_left_keys_in_the_curated_file_raise() -> None:
    a = anatomy()
    bad = {**a, "nerves": {**a["nerves"], "femoral_l": {"name": "femoral nerve"}}}
    with pytest.raises(ValueError, match="mirroring"):
        ea.with_left(bad)


def test_left_lookups_ask_fma_for_the_left_class() -> None:
    m = ea.with_left(anatomy())
    _, fma = ea.lookup_terms("muscle", "glmed1_l", m["muscles"]["glmed1_l"])
    assert fma == ["left gluteus medius", "gluteus medius"]
    _, fma = ea.lookup_terms("muscle", "bflh_l", m["muscles"]["bflh_l"])
    assert fma[-1] == "long head of left biceps femoris"
    ub, fm = ea.wanted_terms(anatomy())
    assert {"left vastus lateralis", "right vastus lateralis", "left knee joint"} <= fm
    assert "vastus lateralis" in ub


def test_each_coordinate_takes_the_muscles_of_its_leg() -> None:
    c = config()
    assert c.muscle_suffixes == ("_r", "_l")
    assert c.coordinates[:10] == tuple(f"{x}_{s}" for s in "rl" for x in ("hip_flexion", "hip_adduction", "hip_rotation", "knee_angle", "ankle_angle"))
    names = ["vaslat_r", "vaslat_l", "ercspn_r", "lumbar_x"]
    assert label_roles.labelled_muscles(names, c) == ["vaslat_r", "vaslat_l", "ercspn_r"]
    assert label_roles.muscles_of("knee_angle_l", ["vaslat_r", "vaslat_l"], c) == ["vaslat_l"]
    assert label_roles.muscles_of("knee_angle_r", ["vaslat_r", "vaslat_l"], c) == ["vaslat_r"]
    assert label_roles.muscles_of("lumbar_extension", ["vaslat_r", "vaslat_l"], c) == ["vaslat_r", "vaslat_l"]


def test_dynamics_of_the_left_leg_name_left_joints_and_muscles() -> None:
    c = config()
    n = 90
    t = [0.01 * i for i in range(n)]
    trial = label_roles.Trial(
        time=t,
        coordinates={k: [math.radians(10.0)] * n for k in c.coordinates},
        activation={"a_r": [0.5] * n, "a_l": [0.5] * n},
        moment_arm={("a_r", "knee_angle_r"): [-0.04] * n, ("a_l", "knee_angle_l"): [-0.04] * n},
        velocity={},
        max_force={"a_r": 1000.0, "a_l": 1000.0},
    )
    d = export_dynamics.build(trial, sp.Phases(t, [], [], [], stride_events()), c, anatomy())
    knee = next(x for x in d["coordinates"] if x["coordinate"] == "knee_angle_l")
    assert (knee["joint"], knee["positive"], knee["negative"]) == ("joint:knee_l", "action:knee_flexion_l", "action:knee_extension_l")
    assert list(knee["moments"]) == ["muscle:a_l"] and knee["moments"]["muscle:a_l"] == [-20.0] * len(range(0, n, export_muscle_paths.frame_step(100.0)))


def test_committed_output_stays_under_8_mb() -> None:
    out = REPO / "data" / "out"
    total = sum(f.stat().st_size for f in Path(out).rglob("*") if f.is_file())
    assert total < OUT_LIMIT_BYTES, total
