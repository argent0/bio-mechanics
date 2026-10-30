"""Workstream M: the pure rules of stage `buildModel` (`pipeline/build_model.py`), and the merge
recipe `pipeline/config/model.yaml`. Every test here runs without OpenSim.

Pinned numbers:
  - Lumbar chain (FBLS, D-011): the raw shares of the five vertebral joints (and the torso joint)
    sum per axis to `FBLS_SUMS`; `normalised_shares` divides by them, so each axis sums to one
    and `lumbar_rotation` keeps Rajagopal's meaning (the torso turns by the coordinate's value).
  - Neck split (D-010): the lower group's share per axis is its range of motion over both
    groups' ranges in Mortensen's model, `NECK_SHARES` (extension, bending, rotation).
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from pipeline import build_model as bm
from pipeline.load_model import REPO, Table

RECIPE = REPO / "pipeline" / "config" / "model.yaml"
FBLS = REPO / "data" / "raw" / "fbls" / "FBLSmodel.osim"
FBLS_SUMS = {"lumbar_extension": 0.9343, "lumbar_bending": 1.0000, "lumbar_rotation": 0.3817}
NECK_SHARES = (0.6694, 0.8462, 0.4154)
MORTENSEN_RANGES = {
    "pitch2": (-0.575958653158, 0.837758040957),
    "roll2": (-0.575958653158, 0.575958653158),
    "yaw2": (-0.471238898038, 0.471238898038),
    "pitch1": (-0.279252680319, 0.418879020479),
    "roll1": (-0.104719755120, 0.104719755120),
    "yaw1": (-0.663225115758, 0.663225115758),
}


def close(a: bm.Vec3, b: bm.Vec3, tol: float = 1e-12) -> bool:
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_xyz_angles_round_trip() -> None:
    for angles in [(0.1, -0.2, 0.3), (-1.2, 0.4, 2.5), (0.0, 0.0, 0.0)]:
        assert close(bm.to_xyz(bm.from_xyz(angles)), angles, 1e-12)


def test_mirror_maps_z_and_rotations_across_the_sagittal_plane() -> None:
    assert bm.mirror_point((1.0, 2.0, 3.0)) == (1.0, 2.0, -3.0)
    r = bm.from_xyz((0.3, -0.2, 0.5))
    m = bm.mirror_rotation(r)
    # A point rotated then mirrored equals the mirrored point rotated by the mirrored rotation.
    p = (0.2, -0.4, 0.7)
    assert close(bm.mirror_point(bm.mvec(r, p)), bm.mvec(m, bm.mirror_point(p)))
    assert close(bm.to_xyz(m), (-0.3, 0.2, 0.5))


def test_rotation_vector_and_heading() -> None:
    assert close(bm.rotation_vector(bm.rot_y(0.4)), (0.0, 0.4, 0.0))
    assert math.isclose(bm.heading(bm.rot_y(0.7)), 0.7)
    assert math.isclose(bm.heading(bm.mmul(bm.rot_y(-1.2), bm.rot_z(0.3))), -1.2)


def test_turn_between_lays_one_direction_on_another() -> None:
    a, b = (0.1, -1.0, 0.2), (0.0, -1.0, 0.0)
    r = bm.turn_between(a, b)
    ra = bm.mvec(r, a)
    n = math.sqrt(bm.vdot(ra, ra))
    assert close(bm.vscale(1.0 / n, ra), b, 1e-12)


def test_register_matches_bounding_boxes() -> None:
    src = [(0.0, 0.0, 0.0), (1.0, 2.0, 4.0)]
    dst = [(1.0, 1.0, 1.0), (1.5, 2.0, 3.0)]
    p = bm.register(src, dst)
    assert p.scale == 0.5
    assert close(p.place(src[0]), dst[0]) and close(p.place(src[1]), dst[1])


def test_axis_scales_follow_the_frame() -> None:
    s = (1.2, 1.1, 1.3)
    assert close(bm.axis_scales(bm.IDENTITY, s), s)
    assert close(bm.axis_scales(bm.rot_z(math.pi / 2), s), (1.1, 1.2, 1.3), 1e-12)


def test_normalised_shares_sum_to_one() -> None:
    norm, sums = bm.normalised_shares({"a": {"j1": 0.1, "j2": 0.3}, "b": {"j1": 2.0}})
    assert sums == {"a": 0.4, "b": 2.0}
    assert math.isclose(sum(norm["a"].values()), 1.0) and norm["b"] == {"j1": 1.0}


def test_neck_split_follows_the_ranges_of_motion() -> None:
    lower = [MORTENSEN_RANGES[c] for c in ("pitch2", "roll2", "yaw2")]
    upper = [MORTENSEN_RANGES[c] for c in ("pitch1", "roll1", "yaw1")]
    shares = bm.group_shares(lower, upper)
    assert [round(s, 4) for s in shares] == list(NECK_SHARES)
    v = bm.neck_values((0.1, 0.2, 0.3), ["a", "b", "c"], ["d", "e", "f"], shares)
    assert math.isclose(v["a"] + v["d"], 0.1) and math.isclose(v["c"] + v["f"], 0.3)


def test_removing_parts_keeps_mass_and_centre_of_mass() -> None:
    whole = bm.MassProps(10.0, (0.0, 0.5, 0.0), [[2.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 2.0]])
    part = bm.MassProps(2.0, (0.0, 1.0, 0.0), [[0.1, 0.0, 0.0], [0.0, 0.1, 0.0], [0.0, 0.0, 0.1]])
    left = bm.remove_parts(whole, [part])
    assert left.mass == 8.0
    assert close(bm.vadd(bm.vscale(left.mass, left.com), bm.vscale(part.mass, part.com)), bm.vscale(whole.mass, whole.com))
    assert left.inertia[0][0] == pytest.approx(1.6) and bm.is_physical(left.inertia)
    both = bm.combine([left, part])
    assert both.mass == 10.0 and close(both.com, whole.com, 1e-12)


def test_function_slope() -> None:
    lin = ET.fromstring("<LinearFunction><coefficients>0.25 0</coefficients></LinearFunction>")
    spl = ET.fromstring("<SimmSpline><x>-1 0 1</x><y>-0.3 0 0.1</y></SimmSpline>")
    assert bm.function_slope(lin) == 0.25 and bm.function_slope(spl) == pytest.approx(0.2)


def test_mortensen_suffixes() -> None:
    recipe = yaml.safe_load(RECIPE.read_text())
    spec = next(s for s in recipe["sources"] if s["name"] == "mortensen")
    assert bm.renamed_muscle(spec, "stern_mast_L") == "stern_mast_l"
    assert bm.renamed_muscle(spec, "stern_mast") == "stern_mast_r"


def test_recipe_maps_every_placed_body() -> None:
    recipe = bm.load_recipe(RECIPE)
    assert {s["name"] for s in recipe["sources"]} == {"fbls", "holzbaur", "mortensen"}
    for s in recipe["sources"]:
        targets = set(s["bodies"].values())
        new = set(s.get("newBodies") or {})
        # Every target body is a Rajagopal body with a placement, or an added body on one.
        placed = set(s["placement"])
        assert {s["newBodies"][b] for b in new} <= placed
        assert targets - new <= placed, s["name"]
    assert len(recipe["neck"]["lower"]) == len(recipe["neck"]["upper"]) == 3


@pytest.mark.skipif(not FBLS.exists(), reason="data/raw/fbls/ comes from pipeline/env/fetch_data.sh")
def test_fbls_chain_shares() -> None:
    """The raw FBLS shares per lumbar axis, read from the file the way `normalise_chain` reads
    them: the axial ones sum to 0.38, the reason for the normalisation."""
    root = ET.parse(FBLS).getroot()
    couplers = {(c.findtext("dependent_coordinate_name") or "").strip(): c for c in root.iter("CoordinateCouplerConstraint")}
    rename = {"flex_extension": "lumbar_extension", "lat_bending": "lumbar_bending", "axial_rotation": "lumbar_rotation"}
    shares: dict[str, dict[str, float]] = {}
    chain = ("L5_S1_IVDjnt", "L4_L5_IVDjnt", "L3_L4_IVDjnt", "L2_L3_IVD_jnt", "L1_L2_IVD_jnt", "Torsojnt")
    for j in root.iter("CustomJoint"):
        if j.get("name") not in chain:
            continue
        for ta in j.iter("TransformAxis"):
            coord = (ta.findtext("coordinates") or "").strip()
            if not coord or not str(ta.get("name")).startswith("rotation"):
                continue
            a = bm.function_slope(bm.function_of(ta))
            key = f"{j.get('name')}/{ta.get('name')}"
            if coord in rename:
                shares.setdefault(rename[coord], {})[key] = a
            else:
                c = couplers[coord]
                ind = rename[(c.findtext("independent_coordinate_names") or "").strip()]
                f = c.find("coupled_coordinates_function")
                assert f is not None
                shares.setdefault(ind, {})[key] = a * bm.function_slope(bm.function_of(f))
    norm, sums = bm.normalised_shares(shares)
    assert {k: round(v, 4) for k, v in sums.items()} == FBLS_SUMS
    assert all(math.isclose(sum(v.values()), 1.0) for v in norm.values())
    assert len(norm["lumbar_rotation"]) == 6 and len(norm["lumbar_extension"]) == 5


def test_recipe_files_exist() -> None:
    recipe = bm.load_recipe(RECIPE)
    for key in ("scaleSet", "staticPose"):
        p = REPO / recipe[key]
        if not p.exists():
            pytest.skip(f"{p} comes from pipeline/env/make_trial.py")
    scale = bm.ScaleFactors(REPO / recipe["scaleSet"])
    assert scale.of("torso") == pytest.approx((1.21013, 1.17781, 1.21013))
    assert scale.of("hand_r") == (1.0, 1.0, 1.0) and scale.of("nowhere") == (1.0, 1.0, 1.0)


def test_static_pose_columns() -> None:
    t = Table(["time", "/jointset/back/lumbar_extension/value", "/jointset/back/lumbar_extension/speed", "/forceset/x/activation"], {"time": [0.0], "/jointset/back/lumbar_extension/value": [-0.2], "/jointset/back/lumbar_extension/speed": [0.0], "/forceset/x/activation": [0.1]}, {})
    assert bm.static_values(t) == {"lumbar_extension": -0.2}


def test_paths_module_names_the_stage_files() -> None:
    import pipeline_paths as paths

    assert Path(paths.MERGED_MODEL).name == "model.osim" and Path(paths.IK_FULL).name == "ik_full.mot"
    assert paths.MERGE_RECIPE in paths.BUILD_MODEL.inputs
    assert {paths.MERGED_MODEL, paths.IK_FULL} == set(paths.BUILD_MODEL.outputs)
