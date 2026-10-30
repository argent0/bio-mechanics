"""Workstream M: the merged model and `ik_full.mot` that stage `buildModel` writes.

The fixture builds the model into a temporary directory (a few seconds) from the committed
recipe and skips when `opensim` is unimportable or a source model is absent
(`pipeline/env/fetch_data.sh` fetches them).

Pinned facts:
  - 462 muscles: Rajagopal's 80, FBLS's 216 trunk and latissimus muscles, Holzbaur's 47 per arm,
    Mortensen's 72 neck muscles; no torque actuators.
  - The merged bodies sit where Rajagopal's sit at the reference pose, and each lumbar
    coordinate turns the torso against the pelvis exactly as Rajagopal's `back` joint did.
  - Total mass stays the subject's; the head carries the skull and jaw meshes.
  - `ik_full.mot` repeats the inverse kinematics (radians) and holds the head's orientation in
    ground constant (D-010).
  - Moment-arm signs at the trial's mean arm posture (`ARM_POSE`), teaching facts of the merge:
    `SIGNS` (coordinate, sign) per muscle, on both sides.
"""
from __future__ import annotations

import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pipeline import build_model as bm
from pipeline.load_model import REPO, read_sto

import pipeline_paths as paths

SOURCES = [REPO / "data" / "raw" / d for d in ("fbls/FBLSmodel.osim", "holzbaur/Stanford_VA_Upper_Limb_original.osim", "mortensen/HYOID_1.2_ScaledStrenght_UpdatedInertia.osim")]
COUNTS = {"rajagopal": 80, "fbls": 216, "holzbaur": 94, "mortensen": 72}
ADDED_BODIES = {"lumbar1", "lumbar2", "lumbar3", "lumbar4", "lumbar5", "Abdomen", "LB_wrap", "cerv1", "cerv2", "cerv3", "cerv4", "cerv5", "cerv6", "cerv7", "head"}
ARM_POSE = {"elbow_flex": math.radians(38.3), "pro_sup": math.radians(54.0)}
"""The right arm's mean elbow flexion and forearm rotation over the trial (inverse kinematics)."""
SIGNS: dict[str, tuple[str, int]] = {
    "TRIlong": ("elbow_flex", -1),
    "TRIlat": ("elbow_flex", -1),
    "BRA": ("elbow_flex", +1),
    "BIClong": ("elbow_flex", +1),
    "BRD": ("elbow_flex", +1),
    "PT": ("pro_sup", +1),
    "PQ": ("pro_sup", +1),
    "SUP": ("pro_sup", -1),
    "DELT2": ("arm_add", -1),
    "PECM2": ("arm_add", +1),
    "DELT1": ("arm_flex", +1),
    "DELT3": ("arm_flex", -1),
    "INFSP": ("arm_rot", -1),
}
"""Positive: elbow flexion, pronation, shoulder adduction, flexion, internal rotation."""
TRUNK_SIGNS: dict[str, tuple[str, int]] = {
    "rect_abd_r": ("lumbar_extension", -1),
    "IL_L1_r": ("lumbar_extension", +1),
    "LTpL_L1_r": ("lumbar_extension", +1),
    "splen_cap_sklthx_r": ("neck_lower_extension", +1),
    "semi_cap_sklthx_r": ("neck_upper_extension", +1),
    "stern_mast_r": ("neck_lower_extension", -1),
}


class Built:
    def __init__(self, osim: Any, d: Path) -> None:
        self.osim = osim
        self.dir = d
        self.model = osim.Model(str(d / "model.osim"))
        self.posers = {"merged": bm.Poser(osim, self.model)}
        self.state = self.posers["merged"].state
        self.base = osim.Model(str(REPO / paths.SCALED_MODEL))
        self.posers["base"] = bm.Poser(osim, self.base)
        self.base_state = self.posers["base"].state
        self.ik = read_sto(d / "ik_full.mot")

    def pose(self, model: Any, state: Any, values: dict[str, float]) -> None:
        """Every independent coordinate at its value in `values` (else 0), each coupled one from
        its coupler."""
        poser = self.posers["merged" if model is self.model else "base"]
        dependent = {c.dependent for c in poser.couplers}
        poser.pose({n: values.get(n, 0.0) for n in poser.names if n in values or n not in dependent})

    def moment_arm(self, muscle: str, coordinate: str, values: dict[str, float]) -> float:
        self.pose(self.model, self.state, values)
        cs = self.model.getCoordinateSet()
        return float(self.model.getMuscles().get(muscle).computeMomentArm(self.state, cs.get(coordinate)))


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Built]:
    osim = pytest.importorskip("opensim")
    for s in SOURCES:
        if not s.exists():
            pytest.skip(f"{s} comes from pipeline/env/fetch_data.sh")
    d = tmp_path_factory.mktemp("m")
    assert bm.main(["--out-model", str(d / "model.osim"), "--out-ik", str(d / "ik_full.mot")]) == 0
    yield Built(osim, d)


def test_model_loads_with_every_merged_muscle(built: Built) -> None:
    ms = built.model.getMuscles()
    names = [ms.get(i).getName() for i in range(ms.getSize())]
    assert len(names) == sum(COUNTS.values())
    assert all(ms.get(i).getConcreteClassName() == "Millard2012EquilibriumMuscle" for i in range(ms.getSize()))
    fs = built.model.getForceSet()
    assert not any(fs.get(i).getConcreteClassName() == "CoordinateActuator" for i in range(fs.getSize()))
    bodies = {built.model.getBodySet().get(i).getName() for i in range(built.model.getBodySet().getSize())}
    assert ADDED_BODIES <= bodies
    assert not built.model.getJointSet().contains("back")
    assert sum(n.endswith("_r") for n in names) == sum(n.endswith("_l") for n in names)


def test_every_path_point_lies_on_a_body(built: Built) -> None:
    assert bm.check_paths(built.model) > 1500


def test_wrists_unlock(built: Built) -> None:
    for c in ("wrist_flex_r", "wrist_dev_r", "wrist_flex_l", "wrist_dev_l"):
        assert not built.model.getCoordinateSet().get(c).getLocked(built.state)


def test_mass_stays_and_the_head_carries_the_skull(built: Built) -> None:
    def total(model: Any) -> float:
        bs = model.getBodySet()
        return sum(float(bs.get(i).getMass()) for i in range(bs.getSize()))

    assert total(built.model) == pytest.approx(total(built.base), abs=1e-9)

    def meshes(body: str) -> set[str]:
        b = built.model.getBodySet().get(body)
        return {str(built.osim.Mesh.safeDownCast(b.get_attached_geometry(g)).get_mesh_file()) for g in range(b.getPropertyByName("attached_geometry").size())}

    assert {"hat_skull.vtp", "hat_jaw.vtp"} == meshes("head")
    assert "hat_skull.vtp" not in meshes("torso") and "hat_spine.vtp" in meshes("torso")
    head = built.model.getBodySet().get("head").getMass()
    assert 4.0 < head < 6.0


def test_reference_pose_matches_rajagopal(built: Built) -> None:
    built.pose(built.model, built.state, {})
    built.pose(built.base, built.base_state, {})
    bs = built.base.getBodySet()
    for i in range(bs.getSize()):
        name = bs.get(i).getName()
        p = bm.to_vec3(bs.get(i).getTransformInGround(built.base_state).p())
        q = bm.to_vec3(built.model.getBodySet().get(name).getTransformInGround(built.state).p())
        assert math.dist(p, q) < 1e-9, name


def test_added_frames_lie_on_their_rajagopal_body(built: Built) -> None:
    """At the reference pose each added body's frame lies on the Rajagopal body the recipe names
    (`newBodies`): so the head's skull and jaw meshes keep their torso vertices."""
    recipe = bm.load_recipe(REPO / paths.MERGE_RECIPE)
    built.pose(built.model, built.state, {})
    bs = built.model.getBodySet()
    for src in recipe["sources"]:
        for added, on in (src.get("newBodies") or {}).items():
            xa, xo = bs.get(added).getTransformInGround(built.state), bs.get(on).getTransformInGround(built.state)
            assert math.dist(bm.to_vec3(xa.p()), bm.to_vec3(xo.p())) < 1e-6, added
            d = bm.rotation_vector(bm.mmul(bm.mT(bm.to_mat3(xo.R())), bm.to_mat3(xa.R())))
            assert math.sqrt(bm.vdot(d, d)) < 1e-5, added


@pytest.mark.parametrize("coordinate", ["lumbar_extension", "lumbar_bending", "lumbar_rotation"])
def test_lumbar_coordinates_keep_their_meaning(built: Built, coordinate: str) -> None:
    """One lumbar coordinate alone turns the torso against the pelvis as Rajagopal's `back`."""
    for model, state in ((built.model, built.state), (built.base, built.base_state)):
        built.pose(model, state, {coordinate: 0.3})
    rm = bm.mmul(bm.mT(bm.to_mat3(built.model.getBodySet().get("pelvis").getTransformInGround(built.state).R())), bm.to_mat3(built.model.getBodySet().get("torso").getTransformInGround(built.state).R()))
    rb = bm.mmul(bm.mT(bm.to_mat3(built.base.getBodySet().get("pelvis").getTransformInGround(built.base_state).R())), bm.to_mat3(built.base.getBodySet().get("torso").getTransformInGround(built.base_state).R()))
    d = bm.rotation_vector(bm.mmul(bm.mT(rb), rm))
    assert math.sqrt(bm.vdot(d, d)) < 1e-6


def test_ik_full_repeats_the_inverse_kinematics(built: Built) -> None:
    raw = read_sto(REPO / paths.IK_MOTION)
    frames = bm.ik_radians(raw, built.base)
    names = [built.model.getCoordinateSet().get(i).getName() for i in range(built.model.getCoordinateSet().getSize())]
    assert built.ik.labels == ["time", *names]
    assert built.ik.header["inDegrees"] == "no" and built.ik.time == raw.time
    for i, f in enumerate(frames):
        for c, v in f.items():
            assert built.ik.columns[c][i] == v, (c, i)


def test_neck_angles_hold_the_head_level(built: Built) -> None:
    """D-010: the head's orientation in ground stays constant over every frame."""
    names = built.ik.labels[1:]
    first: bm.Mat3 | None = None
    worst = 0.0
    for i in range(0, len(built.ik.time), 7):
        built.pose(built.model, built.state, {n: built.ik.columns[n][i] for n in names})
        r = bm.to_mat3(built.model.getBodySet().get("head").getTransformInGround(built.state).R())
        if first is None:
            first = r
        d = bm.rotation_vector(bm.mmul(bm.mT(first), r))
        worst = max(worst, math.sqrt(bm.vdot(d, d)))
    assert worst < 1e-6
    for c in ("neck_lower_extension", "neck_upper_extension", "neck_lower_rotation"):
        assert max(abs(v) for v in built.ik.columns[c]) < 0.3


@pytest.mark.parametrize("side", ["r", "l"])
def test_arm_moment_arm_signs(built: Built, side: str) -> None:
    pose = {f"{k}_{side}": v for k, v in ARM_POSE.items()}
    for muscle, (coord, sign) in SIGNS.items():
        r = built.moment_arm(f"{muscle}_{side}", f"{coord}_{side}", pose)
        assert r * sign > 0.002, (muscle, side, r)


def test_trunk_and_neck_moment_arm_signs(built: Built) -> None:
    for muscle, (coord, sign) in TRUNK_SIGNS.items():
        for name in (muscle, muscle[:-2] + "_l"):
            r = built.moment_arm(name, coord, {})
            assert r * sign > 0.002, (name, coord, r)
