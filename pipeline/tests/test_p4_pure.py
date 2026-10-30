"""Workstream P4, pure parts: the whole-body role configuration, curated anatomy, scope, path
simplification and mesh bookkeeping. These tests read `pipeline/config/roles.yaml` and
`data/curated/anatomy.yaml` and build small synthetic inputs; they need neither OpenSim nor
pipeline outputs.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import pytest

from pipeline import enrich_anatomy as ea
from pipeline import export_meshes, export_muscle_paths, label_roles
from pipeline.load_model import REPO

import pipeline_paths as paths

ARM = ("arm_flex", "arm_add", "arm_rot", "elbow_flex", "pro_sup", "wrist_flex", "wrist_dev")
MIDLINE = ("lumbar_extension", "lumbar_bending", "lumbar_rotation") + tuple(
    f"neck_{g}_{a}" for g in ("lower", "upper") for a in ("extension", "bending", "rotation")
)


def config() -> label_roles.Config:
    return label_roles.load_config(REPO / paths.ROLE_THRESHOLDS)


def anatomy() -> dict[str, Any]:
    return ea.load_anatomy(REPO / paths.CURATED_ANATOMY)


def test_roles_label_the_lumbar_neck_and_arm_coordinates() -> None:
    c = config()
    assert c.coordinates[10:] == MIDLINE + tuple(f"{x}_r" for x in ARM) + tuple(f"{x}_l" for x in ARM)


def test_midline_coordinates_take_both_sides_and_arm_coordinates_their_own() -> None:
    c = config()
    names = ["IL_L3_r", "IL_L3_l", "DELT3_r", "DELT3_l"]
    for coord in MIDLINE:
        assert label_roles.muscles_of(coord, names, c) == names
    assert label_roles.muscles_of("arm_flex_r", names, c) == ["IL_L3_r", "DELT3_r"]
    assert label_roles.muscles_of("arm_flex_l", names, c) == ["IL_L3_l", "DELT3_l"]


def test_labelled_coordinates_hold_the_model_and_a_spanning_muscle() -> None:
    """The legs-only model has torque-driven lumbar and arm coordinates (no muscle spans them)
    and no neck; those coordinates stay out."""
    c = config()
    kinematics = ["knee_angle_r", "knee_angle_l", "lumbar_extension", "arm_flex_r"]
    arms = [("vaslat_r", "knee_angle_r"), ("vaslat_l", "knee_angle_l"), ("vaslat_l", "knee_angle_r")]
    assert label_roles.labelled_coordinates(kinematics, arms, c) == ["knee_angle_r", "knee_angle_l"]
    arms += [("IL_L3_l", "lumbar_extension"), ("DELT3_l", "arm_flex_r")]
    assert label_roles.labelled_coordinates(kinematics, arms, c) == ["knee_angle_r", "knee_angle_l", "lumbar_extension"]


def test_every_labelled_coordinate_has_its_joint_and_actions() -> None:
    a = ea.with_left(anatomy())
    for coord in config().coordinates:
        entry = a["coordinates"][coord]
        assert entry["joint"] in a["joints"], coord
        for d in ("positive", "negative"):
            assert entry[d] in a["actions"], (coord, d)
            assert ea.side_of(entry[d]) == ea.side_of(coord), (coord, d)  # midline actions stay midline
    assert a["coordinates"]["lumbar_bending"] == {"joint": "lumbarSpine", "positive": "lumbar_right_bending", "negative": "lumbar_left_bending"}
    assert a["coordinates"]["pro_sup_l"] == {"joint": "radioulnar_l", "positive": "forearm_pronation_l", "negative": "forearm_supination_l"}


def test_left_arm_and_neck_entries_mirror_the_right() -> None:
    m = ea.with_left(anatomy())
    assert m["muscles"]["DELT1_l"] == {
        "name": "deltoid (anterior part)", "commonName": "front shoulder muscle", "ontologyName": "deltoid",
        "groups": ["deltoidMuscle_l", "scapulohumeral_l"], "nerve": "axillary_l", "origin": "clavicle_l", "insertion": "humerus_l",
    }
    assert m["muscles"]["splen_cap_sklthx_l"]["groups"] == ["spleniusCapitis_l", "neckExtensors_l"]
    assert m["muscles"]["IL_R10_l"]["insertion"] == "ribCage"  # the midline rib cage stays single
    assert m["bones"]["clavicle_l"]["body"] == "torso" and m["bones"]["carpals_l"]["fmaName"] == "set of carpal bones of left hand"
    assert m["joints"]["shoulder_l"]["opensim"] == ["acromial_l"]
    assert "lumbarSpine_l" not in m["joints"] and "lumbar_extension_l" not in m["coordinates"]


def test_fbls_fascicles_have_one_entry_each_in_a_group_per_named_muscle() -> None:
    a = anatomy()
    named = {
        r"MF_": "multifidus_r", r"LTp": "longissimus_r", r"IL_": "iliocostalis_r", r"QL_": "quadratusLumborum_r",
        r"EO\d_": "externalOblique_r", r"IO\d_": "internalOblique_r", r"rect_abd_": "rectusAbdominis_r", r"LD_": "latissimusDorsi_r",
    }
    counts = {g: 0 for g in named.values()}
    for k, e in a["muscles"].items():
        for prefix, g in named.items():
            if re.match(prefix, k):
                assert g in e["groups"], k
                counts[g] += 1
    assert counts == {
        "multifidus_r": 25, "longissimus_r": 26, "iliocostalis_r": 12, "quadratusLumborum_r": 18,
        "externalOblique_r": 6, "internalOblique_r": 6, "rectusAbdominis_r": 1, "latissimusDorsi_r": 14,
    }
    erector = {k for k, e in a["muscles"].items() if "erectorSpinae_r" in e["groups"]}
    assert {k for k in erector if k.startswith(("IL_", "LTp"))} == {k for k in a["muscles"] if k.startswith(("IL_", "LTp"))}


def test_bone_bodies_carry_extra_bodies() -> None:
    a = anatomy()
    assert ea.bone_bodies(a["bones"]["hyoid"]) == ["cerv3", "cerv1"]
    assert ea.bone_bodies(a["bones"]["femur_r"]) == ["femur_r"]
    ea.check_attachment("Geniohyoid_r", "insertion", "hyoid", a["bones"], ["cerv1", "head"])
    with pytest.raises(ValueError, match="off the model path"):
        ea.check_attachment("Geniohyoid_r", "insertion", "c3", a["bones"], ["cerv1", "head"])


def test_scope_keeps_the_regions_the_labelled_muscles_reach() -> None:
    """On a legs-only model the arm, trunk and neck anatomy stays out of the graph."""
    a = ea.with_left(anatomy())
    model = {
        "joints": [{"name": "hip_r", "parent": "pelvis", "child": "femur_r"}, {"name": "acromial_r", "parent": "torso", "child": "humerus_r"}],
        "muscles": [{"name": "glmed1_r", "insertionBody": "femur_r"}],
    }
    regions = ea.regions_of(a, model)
    muscles = {"glmed1_r": {"origin": "pelvis", "insertion": "femur_r", "groups": ["gluteals_r"], "nerve": "supgluteal_r"}}
    kept = ea.scope(a, regions, muscles, ["hip_flexion_r"])
    assert kept["joint"] == {"hip_r"}  # the shoulder's region stays unreached
    assert kept["jointAction"] == {"hip_flexion_r", "hip_extension_r"}
    assert {"pelvis", "femur_r"} <= kept["bone"] and "humerus_r" not in kept["bone"] and "l3" not in kept["bone"]
    assert kept["muscleGroup"] == {"gluteals_r"} and kept["nerve"] == {"supgluteal_r"}
    assert "iliofemoral_r" in kept["ligament"] and "annular_r" not in kept["ligament"]


def test_simplify_keeps_corners_and_drops_points_near_the_line() -> None:
    arc = [(math.cos(t), math.sin(t), 0.0) for t in (k * math.pi / 200 for k in range(101))]  # quarter circle, r = 1 m
    out = export_muscle_paths.simplify(arc, 0.002)
    assert out[0] == arc[0] and out[-1] == arc[-1] and 10 < len(out) < 30
    for p in arc:
        assert min(export_muscle_paths.segment_distance(p, out[i], out[i + 1]) for i in range(len(out) - 1)) <= 0.002
    corner = [(0.0, 0.0, 0.0), (0.05, 0.0005, 0.0), (0.1, 0.0, 0.0), (0.1, 0.1, 0.0)]
    assert export_muscle_paths.simplify(corner, 0.002) == [corner[0], corner[2], corner[3]]
    assert export_muscle_paths.simplify(corner[:2], 0.002) == corner[:2]


def test_twenty_five_hertz_frames() -> None:
    assert export_muscle_paths.frame_step(100.0) == 4 and 100.0 / export_muscle_paths.frame_step(100.0) == 25.0


def test_bodies_without_meshes_are_named_with_their_reason() -> None:
    model = {"bodies": [{"name": "torso", "geometry": ["hat_spine.vtp"]}, {"name": "lumbar3", "geometry": []}, {"name": "cerv2", "geometry": []}]}
    assert export_meshes.meshed_bodies(model) == ["torso"]
    assert "FBLS" in export_meshes.UNMESHED["lumbar3"] and "Mortensen" in export_meshes.UNMESHED["cerv2"]
    with pytest.raises(ValueError, match="outside UNMESHED"):
        export_meshes.meshed_bodies({"bodies": [{"name": "spleen", "geometry": []}]})


def test_anatomy_header_names_the_left_side_from_code() -> None:
    head = Path(REPO / paths.CURATED_ANATOMY).read_text().split("\n\n", 1)[0]
    assert "the left side comes from code" in head and "with_left" in head
