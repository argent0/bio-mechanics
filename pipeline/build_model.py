"""Stage `buildModel`: one merged model and one motion for every later stage (D-008 to D-011).

Inputs: the scaled Rajagopal model (`pipeline_paths.SCALED_MODEL`), its inverse kinematics
(`pipeline_paths.IK_MOTION`), and the merge recipe (`pipeline_paths.MERGE_RECIPE`,
`pipeline/config/model.yaml`), which names the source models, their body maps, and the files
under `scaleSet`, `staticPose` and `geometry`.
Outputs: `pipeline_paths.MERGED_MODEL` (`data/work/model.osim`) and `pipeline_paths.IK_FULL`
(`data/work/ik_full.mot`).

The merged model is the scaled Rajagopal model plus
  - trunk: FBLS (Raabe & Chaudhari 2016): the lumbar vertebrae `lumbar5`..`lumbar1` and two
    wrapping bodies in place of Rajagopal's `back` joint, with the trunk and latissimus muscles
    (D-011);
  - arms: Holzbaur 2005, right side, mirrored for the left;
  - neck: Mortensen 2018: the cervical vertebrae `cerv7`..`cerv1` and the `head` (D-009).

Rules (each one is code below; `pipeline/tests/test_m_*.py` pins the outcomes):

Points. A source point is taken in the source's ground frame at its reference pose (free
coordinates at 0 unless `referencePose` sets them; `Source`), placed in the target body's generic
frame (`Placement.place`), and multiplied per axis by the target body's scale factors from the
subject's scale set (`ScaleFactors`). Every target body is axis-aligned with ground in the
reference pose (every Rajagopal coordinate 0; `Target` checks it), so a placement is a uniform
scale, a turn and a shift (`placements`: one anchor point, two anchor points, a joint axis laid
along a joint axis, or a mesh registration). An added body's frame lies on the frame of the
Rajagopal body it names in `newBodies` at the reference pose, so its points take that body's
placement and scale factors. Mirroring (left arm) maps z to -z.

Via bodies (Holzbaur's massless bodies on coupled translations, which emulate moving via points)
and conditional path points freeze at the via pose (`viaPose`, the right arm's mean posture over
the trial): a point on a via body takes its place on the nearest regular ancestor body there, and
a conditional point stays as a fixed point when active there and drops otherwise. Moving path
points freeze at the reference pose.

Muscles. Every merged muscle is a Millard2012EquilibriumMuscle with the settings of
`muscleTemplate`, carrying the source's maximum isometric force, pennation angle at optimal
fibre length, optimal fibre length and tendon slack length. The two lengths scale by the ratio
of the muscle-tendon length in the merged model to the length in the source, both at the
reference pose (Holzbaur's muscles at the via pose and its Rajagopal counterpart): the scale
tool's own rule, so each fibre keeps its source operating point.

Wrapping surfaces follow their body's placement; each semi-axis, radius or length scales by the
body's scale factors along that axis of the surface (`axis_scales`).

Bodies and mass. Added bodies take their source mass, centre of mass and inertia: the mass times
the subject's torso mass ratio (subject torso over FBLS torso plus vertebrae, which is the
generic Rajagopal torso), the inertia also times the squared mean length scale. Their mass
leaves the torso: its centre of mass follows by mass balance, its inertia keeps its radii of
gyration (`remove_parts`); the total mass stays the subject's. The skull and jaw meshes move to `head`
(D-009); its frame lies on the torso's at the reference pose, so the mesh vertices hold.

Joints. Source joints between added bodies copy over with their offsets placed by the same rule.
A joint into an existing Rajagopal body (FBLS `Torsojnt` into `torso`) puts that body where
Rajagopal's own joint put it at the reference pose (`attach_existing_child`). The FBLS chain
replaces `back`: its independent coordinates take Rajagopal's lumbar names and coordinate
settings, and each vertebral joint's share per axis is divided by the axis's sum
(`normalised_shares`), so `lumbar_rotation` (FBLS axial shares sum to 0.38) and
`lumbar_extension` (0.93) keep Rajagopal's meaning. FBLS's abdominal and lumbar wrapping bodies
keep their posture per unit of trunk motion. Mortensen's couplers sum to one per group already
and copy over.

Actuators. Rajagopal's torque actuators all go: muscles span every lumbar, shoulder, elbow,
forearm, wrist and neck coordinate, and static optimisation adds a reserve on every free
coordinate (`pipeline/static_opt.py`). Mortensen's bushings (passive vertebral stiffness) and
its two impact actuators stay out: the model carries passive joint forces nowhere else, and the
neck muscles alone balance the head. Rajagopal's locked wrist coordinates unlock (`unlock`): the
wrist muscles balance the hand at the trial's neutral wrist.

Neck angles (D-010, `neck` in the recipe): the head holds its static-pose orientation in ground
at every frame. `head_target` takes the head's pitch and roll from the static pose (neck at 0)
and its heading from the torso's mean heading over the trial; `solve_neck` finds per frame the
neck rotation that reaches it, each axis split between the lower and upper neck groups in
proportion to their ranges of motion (`group_shares`). `ik_full.mot` holds every coordinate of
the merged model in radians and metres (`inDegrees=no`): the inverse-kinematics coordinates
(rotations converted to radians), the neck angles, and each coupled coordinate from its coupler.

Every muscle path point lands on a body of the merged model: `check_paths` asserts it.

Run with the OpenSim environment's Python: `python -m pipeline.build_model`.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pipeline.load_model import REPO, Table, opensim_module, read_sto
from pipeline.segment_phases import GENERATED  # noqa: F401  (puts generated/py on sys.path)

import pipeline_paths as paths  # noqa: E402

Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]
"""A 3x3 matrix by rows."""

IDENTITY: Mat3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
ZERO: Vec3 = (0.0, 0.0, 0.0)

# ---------------------------------------------------------------------------------------------
# Small linear algebra (pure).


def vadd(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vsub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vscale(k: float, a: Vec3) -> Vec3:
    return (k * a[0], k * a[1], k * a[2])


def vmul(a: Vec3, b: Vec3) -> Vec3:
    """Element-wise product (per-axis scaling)."""
    return (a[0] * b[0], a[1] * b[1], a[2] * b[2])


def vdot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def mvec(m: Mat3, v: Vec3) -> Vec3:
    return (vdot(m[0], v), vdot(m[1], v), vdot(m[2], v))


def mT(m: Mat3) -> Mat3:
    return ((m[0][0], m[1][0], m[2][0]), (m[0][1], m[1][1], m[2][1]), (m[0][2], m[1][2], m[2][2]))


def mmul(a: Mat3, b: Mat3) -> Mat3:
    bt = mT(b)
    return (
        (vdot(a[0], bt[0]), vdot(a[0], bt[1]), vdot(a[0], bt[2])),
        (vdot(a[1], bt[0]), vdot(a[1], bt[1]), vdot(a[1], bt[2])),
        (vdot(a[2], bt[0]), vdot(a[2], bt[1]), vdot(a[2], bt[2])),
    )


def rot_x(a: float) -> Mat3:
    c, s = math.cos(a), math.sin(a)
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def rot_y(a: float) -> Mat3:
    c, s = math.cos(a), math.sin(a)
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def rot_z(a: float) -> Mat3:
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def from_xyz(angles: Vec3) -> Mat3:
    """Rotation from body-fixed x-y-z angles (OpenSim's `orientation`, `xyz_body_rotation`)."""
    return mmul(mmul(rot_x(angles[0]), rot_y(angles[1])), rot_z(angles[2]))


def to_xyz(r: Mat3) -> Vec3:
    """Body-fixed x-y-z angles of a rotation (inverse of `from_xyz`)."""
    b = math.asin(max(-1.0, min(1.0, r[0][2])))
    if abs(r[0][2]) < 1.0 - 1e-12:
        return (math.atan2(-r[1][2], r[2][2]), b, math.atan2(-r[0][1], r[0][0]))
    return (math.atan2(r[2][1], r[1][1]), b, 0.0)


MIRROR: Mat3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0))


def mirror_point(v: Vec3) -> Vec3:
    """The mirror image across the sagittal plane: z -> -z."""
    return (v[0], v[1], -v[2])


def mirror_rotation(r: Mat3) -> Mat3:
    """The mirror image of a frame orientation: M R M with M = diag(1, 1, -1)."""
    return mmul(mmul(MIRROR, r), MIRROR)


def rotation_vector(r: Mat3) -> Vec3:
    """Axis times angle (rad) of a rotation."""
    cos = max(-1.0, min(1.0, (r[0][0] + r[1][1] + r[2][2] - 1.0) / 2.0))
    angle = math.acos(cos)
    v = (r[2][1] - r[1][2], r[0][2] - r[2][0], r[1][0] - r[0][1])
    if angle < 1e-9:
        return vscale(0.5, v)
    return vscale(angle / (2.0 * math.sin(angle)), v)


def heading(r: Mat3) -> float:
    """Angle about ground y (up) of a frame's x axis projected on the floor."""
    return math.atan2(-r[2][0], r[0][0])


def mean(xs: Iterable[float]) -> float:
    v = list(xs)
    return sum(v) / len(v)


# ---------------------------------------------------------------------------------------------
# Rules (pure).


def axis_scales(r: Mat3, s: Vec3, uniform: float = 1.0) -> Vec3:
    """Stretch of each local axis of a frame with orientation `r` in a body scaled per axis by
    `s` (and uniformly by `uniform`)."""
    out = []
    for k in range(3):
        col = (r[0][k] * s[0], r[1][k] * s[1], r[2][k] * s[2])
        out.append(uniform * math.sqrt(vdot(col, col)))
    return (out[0], out[1], out[2])


def normalised_shares(shares: dict[str, dict[str, float]]) -> tuple[dict[str, dict[str, float]], dict[str, float]]:
    """`shares[independent coordinate][joint axis]` divided by their sum per coordinate, and the
    sums. The normalised shares of a coordinate sum to one, so the chain turns by the
    coordinate's value about each axis (exactly for one axis at a time)."""
    sums = {c: sum(v.values()) for c, v in shares.items()}
    return {c: {k: x / sums[c] for k, x in v.items()} for c, v in shares.items()}, sums


def group_shares(lower: Sequence[tuple[float, float]], upper: Sequence[tuple[float, float]]) -> list[float]:
    """Per axis, the lower neck group's share of a neck rotation: its range of motion over the
    sum of both groups' ranges. The upper group takes the rest."""
    return [(lo[1] - lo[0]) / ((lo[1] - lo[0]) + (up[1] - up[0])) for lo, up in zip(lower, upper)]


def parallel_axis(m: float, c: Vec3) -> list[list[float]]:
    """m (|c|^2 E - c c^T): the inertia of a point mass m at c about the origin."""
    cc = vdot(c, c)
    return [[m * ((cc if i == j else 0.0) - c[i] * c[j]) for j in range(3)] for i in range(3)]


def madd(a: list[list[float]], b: list[list[float]], k: float = 1.0) -> list[list[float]]:
    return [[a[i][j] + k * b[i][j] for j in range(3)] for i in range(3)]


@dataclass
class MassProps:
    mass: float
    com: Vec3
    inertia: list[list[float]]
    """About the centre of mass, in body axes."""

    def xml_inertia(self) -> str:
        i = self.inertia
        return " ".join(f"{v:.17g}" for v in (i[0][0], i[1][1], i[2][2], i[0][1], i[0][2], i[1][2]))


def inertia_matrix(moments: Vec3, products: Vec3) -> list[list[float]]:
    """OpenSim's `inertia` (Ixx Iyy Izz Ixy Ixz Iyz) as a symmetric matrix."""
    xx, yy, zz = moments
    xy, xz, yz = products
    return [[xx, xy, xz], [xy, yy, yz], [xz, yz, zz]]


def rotate_inertia(r: Mat3, i: list[list[float]]) -> list[list[float]]:
    """R I R^T."""
    tmp = [[sum(r[a][k] * i[k][b] for k in range(3)) for b in range(3)] for a in range(3)]
    return [[sum(tmp[a][k] * r[b][k] for k in range(3)) for b in range(3)] for a in range(3)]


def is_physical(i: list[list[float]]) -> bool:
    d = (i[0][0], i[1][1], i[2][2])
    return min(d) > 0 and d[0] + d[1] >= d[2] and d[1] + d[2] >= d[0] and d[0] + d[2] >= d[1]


def combine(parts: Sequence[MassProps]) -> MassProps:
    """One body made of `parts` (all in the same frame)."""
    m = sum(p.mass for p in parts)
    com = vscale(1.0 / m, (sum(p.mass * p.com[0] for p in parts), sum(p.mass * p.com[1] for p in parts), sum(p.mass * p.com[2] for p in parts)))
    io = [[0.0] * 3 for _ in range(3)]
    for p in parts:
        io = madd(madd(io, p.inertia), parallel_axis(p.mass, p.com))
    return MassProps(m, com, madd(io, parallel_axis(m, com), -1.0))


def remove_parts(whole: MassProps, parts: Sequence[MassProps]) -> MassProps:
    """`whole` minus `parts` (all in the same frame): the mass and centre of mass by balance, the
    inertia about the new centre of mass as `whole`'s times the mass ratio (radii of gyration
    kept). The sources' vertebra inertias exceed what the Rajagopal torso holds (FBLS's lumbar
    slabs alone carry 0.83 kg m^2 about x against the generic torso's 1.47), so a parallel-axis
    subtraction leaves no physical tensor."""
    m = whole.mass - sum(p.mass for p in parts)
    if m <= 0:
        raise ValueError("the parts outweigh the body they leave")
    mc = vsub(vscale(whole.mass, whole.com), (sum(p.mass * p.com[0] for p in parts), sum(p.mass * p.com[1] for p in parts), sum(p.mass * p.com[2] for p in parts)))
    return MassProps(m, vscale(1.0 / m, mc), [[v * m / whole.mass for v in row] for row in whole.inertia])


def function_slope(fn: ET.Element) -> float:
    """Mean slope of an OpenSim function element over its points (exact for linear ones)."""
    if fn.tag == "LinearFunction":
        return float((fn.findtext("coefficients") or "1 0").split()[0])
    if fn.tag in ("SimmSpline", "PiecewiseLinearFunction", "NaturalCubicSpline", "GCVSpline"):
        x = [float(v) for v in (fn.findtext("x") or "").split()]
        y = [float(v) for v in (fn.findtext("y") or "").split()]
        return (y[-1] - y[0]) / (x[-1] - x[0])
    if fn.tag == "Constant":
        return 0.0
    raise ValueError(f"function {fn.tag}: slope unknown")


def linear_function(slope: float) -> ET.Element:
    fn = ET.Element("LinearFunction", {"name": "function"})
    ET.SubElement(fn, "coefficients").text = f"{slope:.17g} 0"
    return fn


def text3(v: Vec3) -> str:
    return " ".join(f"{x:.17g}" for x in v)


def vec3(text: str | None) -> Vec3:
    v = [float(x) for x in (text or "0 0 0").split()]
    return (v[0], v[1], v[2])


def set_text(el: ET.Element, tag: str, text: str) -> None:
    sub = el.find(tag)
    if sub is None:
        sub = ET.SubElement(el, tag)
    sub.text = text


def function_of(axis: ET.Element) -> ET.Element:
    """The function element of a `TransformAxis` or a coupler's function wrapper."""
    return [e for e in axis if e.tag not in ("coordinates", "axis")][0]


# ---------------------------------------------------------------------------------------------
# Recipe and scale set.


def load_recipe(path: Path) -> dict[str, Any]:
    recipe = yaml.safe_load(path.read_text()) or {}
    if not isinstance(recipe, dict) or not recipe.get("sources"):
        raise ValueError(f"{path}: a merge recipe names its `sources`")
    return recipe


class ScaleFactors:
    """Per-body scale factors of the subject (an OpenSim ScaleSet `.xml`); 1 for absent bodies."""

    def __init__(self, path: Path) -> None:
        self.factors: dict[str, Vec3] = {}
        for s in ET.parse(path).getroot().iter("Scale"):
            if (s.findtext("apply") or "true").strip() == "true":
                self.factors[(s.findtext("segment") or "").strip()] = vec3(s.findtext("scales"))

    def of(self, body: str) -> Vec3:
        return self.factors.get(body, (1.0, 1.0, 1.0))


# ---------------------------------------------------------------------------------------------
# Models through the OpenSim API.


def to_vec3(v: Any) -> Vec3:
    return (float(v.get(0)), float(v.get(1)), float(v.get(2)))


def to_mat3(r: Any) -> Mat3:
    return (
        (float(r.get(0, 0)), float(r.get(0, 1)), float(r.get(0, 2))),
        (float(r.get(1, 0)), float(r.get(1, 1)), float(r.get(1, 2))),
        (float(r.get(2, 0)), float(r.get(2, 1)), float(r.get(2, 2))),
    )


def set_coordinates(model: Any, state: Any, values: dict[str, float]) -> None:
    """Set coordinate values, then assemble, so coupled coordinates follow their couplers."""
    cs = model.getCoordinateSet()
    for name, v in values.items():
        cs.get(name).setValue(state, v, False)
    model.assemble(state)
    model.realizePosition(state)


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def axis_angle(axis: Vec3, angle: float) -> Mat3:
    """Rotation by `angle` about the unit vector `axis` (Rodrigues)."""
    x, y, z = axis
    c, s, t = math.cos(angle), math.sin(angle), 1.0 - math.cos(angle)
    return (
        (t * x * x + c, t * x * y - s * z, t * x * z + s * y),
        (t * x * y + s * z, t * y * y + c, t * y * z - s * x),
        (t * x * z - s * y, t * y * z + s * x, t * z * z + c),
    )


def turn_between(a: Vec3, b: Vec3) -> Mat3:
    """The smallest rotation that turns the direction of `a` into that of `b`."""
    c = cross(a, b)
    nc = math.sqrt(vdot(c, c))
    if nc < 1e-15:
        return IDENTITY
    return axis_angle(vscale(1.0 / nc, c), math.atan2(nc, vdot(a, b)))


@dataclass
class Placement:
    """Source ground (reference pose) -> target body generic frame: p = scale * rot g + shift."""

    scale: float
    shift: Vec3
    rot: Mat3 = IDENTITY

    def place(self, g: Vec3) -> Vec3:
        return vadd(vscale(self.scale, mvec(self.rot, g)), self.shift)


class Source:
    """A source model at its reference pose and its via pose, with its XML in OpenSim 4 form."""

    def __init__(self, osim: Any, spec: dict[str, Any], via_values: dict[str, float], tmp: Path) -> None:
        self.spec = spec
        self.name: str = spec["name"]
        self.osim = osim
        self.model = osim.Model(str(REPO / spec["file"]))
        self.ref = self.model.initSystem()
        cs = self.model.getCoordinateSet()
        free = [str(cs.get(i).getName()) for i in range(cs.getSize()) if not cs.get(i).getLocked(self.ref) and not cs.get(i).isConstrained(self.ref)]
        reference = {**{c: 0.0 for c in free}, **{str(k): float(v) for k, v in (spec.get("referencePose") or {}).items()}}
        set_coordinates(self.model, self.ref, reference)
        self.via = osim.State(self.ref)
        set_coordinates(self.model, self.via, {**reference, **via_values})
        printed = tmp / f"{self.name}.osim"
        self.model.printToXML(str(printed))
        self.xml = ET.parse(printed).getroot()
        self.bodies: dict[str, str] = {str(k): str(v) for k, v in spec["bodies"].items()}
        self.new_bodies: dict[str, str] = {str(k): str(v) for k, v in (spec.get("newBodies") or {}).items()}
        self.via_carrier = self._via_bodies()

    def body(self, name: str) -> Any:
        return self.model.getBodySet().get(name)

    def ground(self, body: str, loc: Vec3) -> Vec3:
        return to_vec3(self.body(body).findStationLocationInGround(self.ref, self.osim.Vec3(*loc)))

    def rotation(self, body: str) -> Mat3:
        return to_mat3(self.body(body).getTransformInGround(self.ref).R())

    def _via_bodies(self) -> dict[str, str]:
        """Via body -> its nearest regular ancestor. A via body hangs on a joint whose coordinates
        are all coupled translations (Holzbaur's moving via points)."""
        parent: dict[str, str] = {}
        via: set[str] = set()
        js = self.model.getJointSet()
        for i in range(js.getSize()):
            j = js.get(i)
            child = str(j.getChildFrame().findBaseFrame().getName())
            parent[child] = str(j.getParentFrame().findBaseFrame().getName())
            n = j.numCoordinates()
            if n and all(int(j.get_coordinates(k).getMotionType()) == 2 and j.get_coordinates(k).isConstrained(self.ref) for k in range(n)):
                via.add(child)
        out: dict[str, str] = {}
        for b in via:
            a = parent[b]
            while a in via:
                a = parent[a]
            out[b] = a
        return out

    def carried(self, body: str, loc: Vec3) -> tuple[str, Vec3]:
        """A point on a via body, moved to the regular ancestor at the via pose."""
        carrier = self.via_carrier.get(body)
        if carrier is None:
            return body, loc
        p = self.body(body).findStationLocationInAnotherFrame(self.via, self.osim.Vec3(*loc), self.body(carrier))
        return carrier, to_vec3(p)


class Target:
    """The scaled Rajagopal model at its reference pose (every coordinate 0)."""

    def __init__(self, osim: Any, path: Path, scale: ScaleFactors, recipe: dict[str, Any]) -> None:
        self.model = osim.Model(str(path))
        self.state = self.model.initSystem()
        cs = self.model.getCoordinateSet()
        for i in range(cs.getSize()):
            cs.get(i).setValue(self.state, 0.0, False)
        self.model.realizePosition(self.state)
        self.scale = scale
        self.coincident: dict[str, str] = {}
        for src in recipe["sources"]:
            self.coincident.update({str(k): str(v) for k, v in (src.get("newBodies") or {}).items()})
        for src in recipe["sources"]:
            for body in {self.frame_of(str(b)) for b in src["bodies"].values()}:
                r = to_mat3(self.model.getBodySet().get(body).getTransformInGround(self.state).R())
                if max(abs(r[a][b] - IDENTITY[a][b]) for a in range(3) for b in range(3)) > 1e-9:
                    raise ValueError(f"{body}: axes off ground's at the reference pose")

    def frame_of(self, body: str) -> str:
        """The Rajagopal body whose frame a body's frame lies on at the reference pose."""
        return self.coincident.get(body, body)

    def scale_of(self, body: str) -> Vec3:
        return self.scale.of(self.frame_of(body))

    def origin(self, body: str) -> Vec3:
        """Body origin in ground at the reference pose."""
        b = self.model.getBodySet().get(self.frame_of(body))
        return to_vec3(b.getTransformInGround(self.state).p())

    def joint_centre(self, joint: str) -> tuple[str, Vec3]:
        """(parent body, centre in the parent's generic frame) of a Rajagopal joint."""
        pf = self.model.getJointSet().get(joint).getParentFrame()
        body = str(pf.findBaseFrame().getName())
        p = to_vec3(pf.findTransformInBaseFrame().p())
        s = self.scale.of(body)
        return body, (p[0] / s[0], p[1] / s[1], p[2] / s[2])

    def relocate(self, loc: Vec3, src_body: str, dst_body: str) -> Vec3:
        """A point given in `src_body`'s frame, in `dst_body`'s frame, at the reference pose."""
        return vsub(vadd(loc, self.origin(src_body)), self.origin(dst_body))


# ---------------------------------------------------------------------------------------------
# Placement of a source.


def bounding_box(points: Sequence[Vec3]) -> tuple[Vec3, Vec3]:
    lo = (min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points))
    hi = (max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points))
    return lo, hi


def register(src_points: Sequence[Vec3], dst_points: Sequence[Vec3]) -> Placement:
    """Uniform scale and shift that put the bounding box of `src_points` on that of `dst_points`:
    the scale is the mean ratio of the three box extents, the shift matches the box centres."""
    (slo, shi), (dlo, dhi) = bounding_box(src_points), bounding_box(dst_points)
    k = mean((dhi[i] - dlo[i]) / (shi[i] - slo[i]) for i in range(3))
    return Placement(k, vsub(vscale(0.5, vadd(dlo, dhi)), vscale(0.5 * k, vadd(slo, shi))))


def mesh_points(path: Path) -> list[Vec3]:
    from pipeline.export_meshes import read_vtp

    return [(float(p[0]), float(p[1]), float(p[2])) for p in read_vtp(path).positions]


def placements(src: Source, target: Target, recipe: dict[str, Any]) -> dict[str, Placement]:
    """Rajagopal body named in `placement` -> the source's placement in it."""
    out: dict[str, Placement] = {}
    for body, spec in (src.spec.get("placement") or {}).items():
        if "register" in spec:
            reg = spec["register"]
            pts = [src.ground(reg["body"], p) for p in mesh_points(REPO / reg["mesh"])]
            out[body] = register(pts, mesh_points(REPO / recipe["geometry"] / reg["target"]))
            continue
        g0, p0 = anchor(src, target, body, spec)
        k, rot = 1.0, IDENTITY
        if "distal" in spec:
            g1, p1 = anchor(src, target, body, spec["distal"])
            u, v = vsub(g1, g0), vsub(p1, p0)
            k, rot = math.sqrt(vdot(v, v) / vdot(u, u)), turn_between(u, v)
        elif "turn" in spec:
            rot = turn_between(joint_axis(src.model, src.ref, spec["turn"]["source"]), joint_axis(target.model, target.state, spec["turn"]["target"]))
        out[body] = Placement(k, vsub(p0, vscale(k, mvec(rot, g0))), rot)
    return out


def joint_axis(model: Any, state: Any, joint: str) -> Vec3:
    """Ground direction of a one-coordinate joint's rotation axis: a PinJoint's z axis, or a
    CustomJoint's first rotation axis that carries a coordinate."""
    osim = opensim_module()
    j = model.getJointSet().get(joint)
    r = to_mat3(j.getParentFrame().getTransformInGround(state).R())
    custom = osim.CustomJoint.safeDownCast(j)
    if custom is None:
        return mvec(r, (0.0, 0.0, 1.0))
    st = custom.getSpatialTransform()
    for k in range(3):
        ta = st.getTransformAxis(k)
        if ta.getCoordinateNames().size():
            return mvec(r, to_vec3(ta.getAxis()))
    raise ValueError(f"{joint}: no rotation axis with a coordinate")


def anchor(src: Source, target: Target, body: str, spec: dict[str, Any]) -> tuple[Vec3, Vec3]:
    """(source point in source ground, target point in the target body's generic frame) of one
    placement anchor: a source body's origin and a Rajagopal joint centre (or the body origin)."""
    g = src.ground(spec["origin"], ZERO)
    if "at" not in spec:
        return g, ZERO
    jb, p = target.joint_centre(spec["at"])
    if jb != body:
        raise ValueError(f"{src.name}: joint {spec['at']} hangs on {jb}, the placement names {body}")
    return g, p


@dataclass
class PointRec:
    body: str
    """Target body."""
    loc: Vec3
    """In the target body's frame, subject size."""


class Mapper:
    """Source point -> target body and location (subject size)."""

    def __init__(self, src: Source, target: Target, recipe: dict[str, Any]) -> None:
        self.src = src
        self.target = target
        self.places = placements(src, target, recipe)

    def target_body(self, src_body: str) -> str:
        carrier = self.src.via_carrier.get(src_body, src_body)
        try:
            return self.src.bodies[carrier]
        except KeyError:
            raise KeyError(f"{self.src.name}: body {carrier} is absent from the recipe's body map") from None

    def placement(self, tgt_body: str) -> Placement:
        return self.places[self.target.frame_of(tgt_body)]

    def point(self, src_body: str, loc: Vec3) -> PointRec:
        carrier, loc = self.src.carried(src_body, loc)
        tb = self.target_body(carrier)
        p = self.placement(tb).place(self.src.ground(carrier, loc))
        return PointRec(tb, vmul(self.target.scale_of(tb), p))

    def orientation(self, src_body: str, r_local: Mat3) -> Mat3:
        """Orientation in the target body of a frame oriented `r_local` in a source body."""
        rot = self.placement(self.target_body(src_body)).rot
        return mmul(rot, mmul(self.src.rotation(src_body), r_local))


# ---------------------------------------------------------------------------------------------
# Muscles and wrapping surfaces.


@dataclass
class WrapUse:
    wrap: str
    method: str
    range: tuple[int, int]


@dataclass
class MuscleRec:
    name: str
    source: str
    fmax: float
    lopt: float
    lts: float
    pennation: float
    length: float
    """Source muscle-tendon length at the reference pose (the via pose when `via`)."""
    points: list[PointRec]
    wraps: list[WrapUse]
    via: bool = False


@dataclass
class WrapRec:
    name: str
    body: str
    element: ET.Element


@dataclass
class Merge:
    """Everything the sources add, in target terms."""

    muscles: list[MuscleRec] = field(default_factory=list)
    wraps: list[WrapRec] = field(default_factory=list)
    bodies: dict[str, MassProps] = field(default_factory=dict)
    """Added bodies, in their own frames, subject size."""
    joints: list[ET.Element] = field(default_factory=list)
    constraints: list[ET.Element] = field(default_factory=list)
    coordinates: dict[str, str] = field(default_factory=dict)
    replaced_joint: str | None = None
    shares: dict[str, dict[str, float]] = field(default_factory=dict)
    """Normalised chain shares per lumbar coordinate."""


def side_name(name: str, side: str) -> str:
    return f"{name}_{side}"


def left_body(body: str) -> str:
    return body[:-2] + "_l" if body.endswith("_r") else body


def renamed_muscle(spec: dict[str, Any], name: str) -> str:
    """The source name with its side suffix rewritten per `suffixes` (longest match first)."""
    suffixes = {str(k): str(v) for k, v in (spec.get("suffixes") or {}).items()}
    for old, new in sorted(suffixes.items(), key=lambda kv: -len(kv[0])):
        if old and name.endswith(old):
            return name[: -len(old)] + new
    return name + suffixes.get("", "")


def wrap_element(src: Source, name: str) -> tuple[str, ET.Element]:
    for b in src.xml.iter("Body"):
        for w in b.iterfind("WrapObjectSet/objects/*"):
            if w.get("name") == name:
                return str(b.get("name")), w
    raise KeyError(f"{src.name}: wrap object {name} on no body")


def placed_wrap(m: Mapper, name: str, new_name: str) -> WrapRec:
    """A source wrapping surface placed, oriented and sized in its target body."""
    src_body, el0 = wrap_element(m.src, name)
    el = copy.deepcopy(el0)
    el.set("name", new_name)
    rec = m.point(src_body, vec3(el.findtext("translation")))
    r = m.orientation(src_body, from_xyz(vec3(el.findtext("xyz_body_rotation"))))
    s = axis_scales(r, m.target.scale_of(rec.body), m.placement(rec.body).scale)
    set_text(el, "translation", text3(rec.loc))
    set_text(el, "xyz_body_rotation", text3(to_xyz(r)))
    if el.tag == "WrapEllipsoid":
        set_text(el, "dimensions", text3(vmul(vec3(el.findtext("dimensions")), s)))
    elif el.tag == "WrapCylinder":
        set_text(el, "radius", f"{float(el.findtext('radius') or 0) * (s[0] + s[1]) / 2:.17g}")
        set_text(el, "length", f"{float(el.findtext('length') or 0) * s[2]:.17g}")
    elif el.tag == "WrapSphere":
        set_text(el, "radius", f"{float(el.findtext('radius') or 0) * mean(s):.17g}")
    elif el.tag == "WrapTorus":
        for tag in ("inner_radius", "outer_radius"):
            set_text(el, tag, f"{float(el.findtext(tag) or 0) * mean(s):.17g}")
    else:
        raise ValueError(f"{m.src.name}: wrap object type {el.tag}")
    return WrapRec(new_name, rec.body, el)


QUADRANT_MIRROR = {"+z": "-z", "-z": "+z", "z": "-z"}
"""A mirrored surface's local z axis points the other way (`mirrored_wrap`)."""


def mirrored_wrap(w: WrapRec, name: str, body: str) -> WrapRec:
    el = copy.deepcopy(w.element)
    el.set("name", name)
    set_text(el, "translation", text3(mirror_point(vec3(el.findtext("translation")))))
    set_text(el, "xyz_body_rotation", text3(to_xyz(mirror_rotation(from_xyz(vec3(el.findtext("xyz_body_rotation")))))))
    q = (el.findtext("quadrant") or "all").strip()
    set_text(el, "quadrant", QUADRANT_MIRROR.get(q, q))
    return WrapRec(name, body, el)


def collect_muscles(m: Mapper, merge: Merge) -> None:
    src = m.src
    spec = src.spec
    exclude = {str(x) for x in (spec.get("exclude") or [])}
    mirror = bool(spec.get("mirror"))
    on_mapped = spec.get("muscles") == "onMappedBodies"
    uses_via = bool(spec.get("viaPose"))
    state = src.via if uses_via else src.ref
    wraps: dict[str, WrapRec] = {}
    ms = src.model.getMuscles()
    for i in range(ms.getSize()):
        mu = ms.get(i)
        name = str(mu.getName())
        pps = mu.getGeometryPath().getPathPointSet()
        if name in exclude or pps.getSize() < 2:
            continue
        bodies = {str(pps.get(k).getParentFrame().findBaseFrame().getName()) for k in range(pps.getSize())}
        if on_mapped and not all(src.via_carrier.get(b, b) in src.bodies for b in bodies):
            continue
        points: list[PointRec] = []
        kept: list[int] = []
        for k in range(pps.getSize()):
            pp = pps.get(k)
            frame = pp.getParentFrame()
            if str(frame.getName()) != str(frame.findBaseFrame().getName()):
                raise ValueError(f"{name}: point {pp.getName()} on an offset frame")
            cond = src.osim.ConditionalPathPoint.safeDownCast(pp)
            if cond is not None and not cond.isActive(state):
                continue
            if src.osim.MovingPathPoint.safeDownCast(pp) is not None:
                loc = to_vec3(pp.getLocation(src.ref))
            else:
                loc = to_vec3(src.osim.PathPoint.safeDownCast(pp).get_location())
            points.append(m.point(str(frame.getName()), loc))
            kept.append(k)
        index = {old + 1: new + 1 for new, old in enumerate(kept)}
        uses: list[WrapUse] = []
        ws = mu.getGeometryPath().getWrapSet()
        for k in range(ws.getSize()):
            pw = ws.get(k)
            wname = str(pw.getWrapObjectName())
            lo, hi = int(pw.get_range(0)), int(pw.get_range(1))
            rng = (index.get(lo, lo) if lo > 0 else lo, index.get(hi, hi) if hi > 0 else hi)
            if wname not in wraps:
                wraps[wname] = placed_wrap(m, wname, side_name(wname, "r") if mirror else wname)
            uses.append(WrapUse(wraps[wname].name, str(pw.get_method()), rng))
        rec = MuscleRec(
            name=side_name(name, "r") if mirror else renamed_muscle(spec, name),
            source=src.name,
            fmax=float(mu.getMaxIsometricForce()),
            lopt=float(mu.getOptimalFiberLength()),
            lts=float(mu.getTendonSlackLength()),
            pennation=float(mu.getPennationAngleAtOptimalFiberLength()),
            length=float(mu.getGeometryPath().getLength(state)),
            points=points,
            wraps=uses,
            via=uses_via,
        )
        merge.muscles.append(rec)
        if mirror:
            merge.muscles.append(
                MuscleRec(
                    side_name(name, "l"), rec.source, rec.fmax, rec.lopt, rec.lts, rec.pennation, rec.length,
                    [PointRec(left_body(p.body), mirror_point(p.loc)) for p in points],
                    [WrapUse(u.wrap[:-2] + "_l", u.method, u.range) for u in uses],
                    uses_via,
                )
            )
    for w in wraps.values():
        merge.wraps.append(w)
        if mirror:
            merge.wraps.append(mirrored_wrap(w, w.name[:-2] + "_l", left_body(w.body)))


# ---------------------------------------------------------------------------------------------
# Added bodies, joints and couplers.


def source_mass(src: Source, body: str) -> MassProps:
    b = src.body(body)
    i = b.getInertia()
    return MassProps(float(b.getMass()), to_vec3(b.getMassCenter()), inertia_matrix(to_vec3(i.getMoments()), to_vec3(i.getProducts())))


def collect_bodies(m: Mapper, merge: Merge, mass_ratio: float) -> None:
    """Added bodies' mass properties, in their own (target) frames at subject size."""
    members: dict[str, list[str]] = {}
    for sb, tb in m.src.bodies.items():
        if tb in m.src.new_bodies:
            members.setdefault(tb, []).append(sb)
    for tb, sbs in members.items():
        length = m.placement(tb).scale * mean(m.target.scale_of(tb))
        parts = []
        for sb in sbs:
            mp = source_mass(m.src, sb)
            inertia = rotate_inertia(m.orientation(sb, IDENTITY), mp.inertia)
            parts.append(MassProps(mp.mass * mass_ratio, m.point(sb, mp.com).loc, [[v * mass_ratio * length * length for v in row] for row in inertia]))
        massive = [p for p in parts if p.mass > 0]
        merge.bodies[tb] = combine(massive) if massive else parts[0]


def joint_ends(j: ET.Element) -> tuple[ET.Element, ET.Element]:
    """(parent offset frame, child offset frame) of a joint element."""
    frames = {fr.get("name"): fr for fr in j.iterfind("frames/PhysicalOffsetFrame")}
    return frames[(j.findtext("socket_parent_frame") or "").strip()], frames[(j.findtext("socket_child_frame") or "").strip()]


def frame_body(fr: ET.Element) -> str:
    return (fr.findtext("socket_parent") or "").strip().split("/")[-1]


def collect_joints(m: Mapper, merge: Merge, base_xml: ET.Element) -> None:
    """Copy the source joints and couplers the recipe names, placed and renamed."""
    src = m.src
    names = [str(x) for x in (src.spec.get("joints") or [])]
    rename = {str(k): str(v) for k, v in (src.spec.get("coordinates") or {}).items()}
    merge.coordinates.update(rename)
    joints = [copy.deepcopy(j) for j in src.xml.iter() if j.get("name") in names and j.tag.endswith("Joint") and j.find("frames") is not None]
    if len(joints) != len(names):
        raise KeyError(f"{src.name}: joints {sorted(set(names) - {str(j.get('name')) for j in joints})} absent")
    for j in joints:
        for fr in j.iterfind("frames/PhysicalOffsetFrame"):
            sb = frame_body(fr)
            rec = m.point(sb, vec3(fr.findtext("translation")))
            r = m.orientation(sb, from_xyz(vec3(fr.findtext("orientation"))))
            set_text(fr, "socket_parent", f"/bodyset/{rec.body}")
            set_text(fr, "translation", text3(rec.loc))
            set_text(fr, "orientation", text3(to_xyz(r)))
        for c in j.iter("Coordinate"):
            c.set("name", rename.get(str(c.get("name")), str(c.get("name"))))
        for ta in j.iter("TransformAxis"):
            cn = ta.find("coordinates")
            if cn is not None and cn.text:
                cn.text = " ".join(rename.get(x, x) for x in cn.text.split())
    coords = {str(c.get("name")) for j in joints for c in j.iter("Coordinate")}
    constraints = []
    for c in src.xml.iter("CoordinateCouplerConstraint"):
        if (c.findtext("dependent_coordinate_name") or "").strip() in coords:
            cc = copy.deepcopy(c)
            ind = cc.find("independent_coordinate_names")
            if ind is not None and ind.text:
                ind.text = " ".join(rename.get(x, x) for x in ind.text.split())
            constraints.append(cc)
    attach_existing_child(m, joints)
    replaced = src.spec.get("replacesJoint")
    if replaced:
        normalise_chain(m, merge, joints, constraints, base_xml, str(replaced))
        merge.replaced_joint = str(replaced)
    merge.joints.extend(joints)
    merge.constraints.extend(constraints)


def attach_existing_child(m: Mapper, joints: list[ET.Element]) -> None:
    """A joint whose child is an existing Rajagopal body puts that body at its Rajagopal
    reference pose: the child offset is the parent-side centre in the child's frame there."""
    for j in joints:
        parent, child = joint_ends(j)
        cb = frame_body(child)
        if cb in m.src.new_bodies:
            continue
        loc = m.target.relocate(vec3(parent.findtext("translation")), frame_body(parent), cb)
        set_text(child, "translation", text3(loc))
        set_text(child, "orientation", parent.findtext("orientation") or "0 0 0")


def chain_joints(joints: list[ET.Element], m: Mapper) -> list[ET.Element]:
    """The joints from an existing body to an existing body (the vertebral chain), in order."""
    by_child = {frame_body(joint_ends(j)[1]): j for j in joints}
    body = next(c for c in by_child if c not in m.src.new_bodies)
    chain = []
    while body in by_child:
        j = by_child[body]
        chain.append(j)
        body = frame_body(joint_ends(j)[0])
    return list(reversed(chain))


def normalise_chain(m: Mapper, merge: Merge, joints: list[ET.Element], constraints: list[ET.Element], base_xml: ET.Element, replaced: str) -> None:
    """Make the chain from the replaced joint's parent to its child turn like the replaced joint:
    per axis, each chain joint's share (its axis function's slope times its coupler's slope) is
    divided by the axis's sum; dependent axes take slope 1 and their couplers the normalised
    share. Coupled bodies off the chain (wrapping bodies) keep their posture per unit of trunk
    motion: their couplers' inputs rescale by the same sums. The independent coordinates take the
    replaced joint's coordinate settings."""
    independents = set(merge.coordinates.values())
    couplers = {(c.findtext("dependent_coordinate_name") or "").strip(): c for c in constraints}

    def coupler_fn(c: ET.Element) -> ET.Element:
        f = c.find("coupled_coordinates_function")
        assert f is not None
        return f

    def independent_of(c: ET.Element) -> str:
        return (c.findtext("independent_coordinate_names") or "").strip()

    chain = chain_joints(joints, m)
    axes = [(j, ta) for j in chain for ta in j.iter("TransformAxis") if str(ta.get("name")).startswith("rotation") and (ta.findtext("coordinates") or "").strip()]
    shares: dict[str, dict[str, float]] = {}
    for j, ta in axes:
        coord = (ta.findtext("coordinates") or "").strip()
        key = f"{j.get('name')}/{ta.get('name')}"
        a = function_slope(function_of(ta))
        if coord in independents:
            shares.setdefault(coord, {})[key] = a
        else:
            c = couplers[coord]
            shares.setdefault(independent_of(c), {})[key] = a * function_slope(function_of(coupler_fn(c)))
    norm, sums = normalised_shares(shares)
    merge.shares = norm
    chain_deps = set()
    for j, ta in axes:
        coord = (ta.findtext("coordinates") or "").strip()
        key = f"{j.get('name')}/{ta.get('name')}"
        ta.remove(function_of(ta))
        if coord in independents:
            ta.append(linear_function(norm[coord][key]))
            continue
        chain_deps.add(coord)
        ta.append(linear_function(1.0))
        c = couplers[coord]
        f = coupler_fn(c)
        f.remove(function_of(f))
        f.append(linear_function(norm[independent_of(c)][key]))
    for dep, c in couplers.items():
        if dep in chain_deps:
            continue
        s = sums[independent_of(c)]
        fn = function_of(coupler_fn(c))
        if fn.tag == "LinearFunction":
            k, b = (float(v) for v in (fn.findtext("coefficients") or "1 0").split())
            set_text(fn, "coefficients", f"{k / s:.17g} {b:.17g}")
        else:
            x = fn.find("x")
            assert x is not None and x.text
            x.text = " ".join(f"{float(v) * s:.17g}" for v in x.text.split())
    base_coords = {str(c.get("name")): c for j in base_xml.iter() if j.get("name") == replaced and j.tag.endswith("Joint") for c in j.iter("Coordinate")}
    for j in chain:
        cs = j.find("coordinates")
        if cs is None:
            continue
        for k, c in enumerate(list(cs)):
            name = str(c.get("name"))
            if name in base_coords:
                cs.remove(c)
                cs.insert(k, copy.deepcopy(base_coords[name]))


# ---------------------------------------------------------------------------------------------
# Writing the merged model.


def muscle_element(template: ET.Element, rec: MuscleRec) -> ET.Element:
    el = copy.deepcopy(template)
    el.set("name", rec.name)
    pts = el.find("GeometryPath/PathPointSet/objects")
    wraps = el.find("GeometryPath/PathWrapSet/objects")
    assert pts is not None and wraps is not None
    for e in list(pts):
        pts.remove(e)
    for e in list(wraps):
        wraps.remove(e)
    for k, p in enumerate(rec.points):
        pe = ET.SubElement(pts, "PathPoint", {"name": f"{rec.name}-P{k + 1}"})
        ET.SubElement(pe, "socket_parent_frame").text = f"/bodyset/{p.body}"
        ET.SubElement(pe, "location").text = text3(p.loc)
    for k, w in enumerate(rec.wraps):
        we = ET.SubElement(wraps, "PathWrap", {"name": f"pathwrap{k + 1}"})
        ET.SubElement(we, "wrap_object").text = w.wrap
        ET.SubElement(we, "method").text = w.method
        ET.SubElement(we, "range").text = f"{w.range[0]} {w.range[1]}"
    set_text(el, "max_isometric_force", f"{rec.fmax:.17g}")
    set_text(el, "optimal_fiber_length", f"{rec.lopt:.17g}")
    set_text(el, "tendon_slack_length", f"{rec.lts:.17g}")
    set_text(el, "pennation_angle_at_optimal", f"{rec.pennation:.17g}")
    for curve in el:
        if curve.tag.endswith("Curve"):
            curve.set("name", f"{rec.name}_{curve.tag}")
    return el


def body_element(name: str, mp: MassProps) -> ET.Element:
    el = ET.Element("Body", {"name": name})
    ET.SubElement(el, "mass").text = f"{mp.mass:.17g}"
    ET.SubElement(el, "mass_center").text = text3(mp.com)
    ET.SubElement(el, "inertia").text = mp.xml_inertia()
    ET.SubElement(el, "attached_geometry")
    wos = ET.SubElement(el, "WrapObjectSet")
    ET.SubElement(wos, "objects")
    ET.SubElement(wos, "groups")
    return el


def find_named(root: ET.Element, tag: str, name: str) -> ET.Element:
    for e in root.iter(tag):
        if e.get("name") == name:
            return e
    raise KeyError(f"{tag} {name} absent")


def objects(model: ET.Element, path: str) -> ET.Element:
    el = model.find(path)
    assert el is not None, path
    return el


def write_merged_xml(base: Path, merge: Merge, target: Target, recipe: dict[str, Any], out: Path) -> dict[str, float]:
    """The merged model as XML (merged muscle lengths still at source values). Returns the torso's
    mass before and after the split."""
    tree = ET.parse(base)
    model = tree.getroot().find("Model")
    assert model is not None
    bodyset = objects(model, "BodySet/objects")
    jointset = objects(model, "JointSet/objects")
    forceset = objects(model, "ForceSet/objects")
    cset = objects(model, "ConstraintSet/objects")

    template = find_named(forceset, "Millard2012EquilibriumMuscle", str(recipe["muscleTemplate"]))
    for f in list(forceset):
        if f.tag == "CoordinateActuator":
            forceset.remove(f)
    names = {str(f.get("name")) for f in forceset}
    for rec in merge.muscles:
        if rec.name in names:
            raise ValueError(f"muscle {rec.name} exists already")
        names.add(rec.name)
        forceset.append(muscle_element(template, rec))

    if merge.replaced_joint:
        jointset.remove(find_named(jointset, "CustomJoint", merge.replaced_joint))
    jointset.extend(merge.joints)
    cset.extend(merge.constraints)

    torso = find_named(bodyset, "Body", "torso")
    whole = MassProps(float(torso.findtext("mass") or 0), vec3(torso.findtext("mass_center")), inertia_matrix(*inertia6(torso.findtext("inertia"))))
    parts = []
    for name, mp in merge.bodies.items():
        bodyset.append(body_element(name, mp))
        parts.append(MassProps(mp.mass, target.relocate(mp.com, name, "torso"), mp.inertia))
    left = remove_parts(whole, parts)
    set_text(torso, "mass", f"{left.mass:.17g}")
    set_text(torso, "mass_center", text3(left.com))
    set_text(torso, "inertia", left.xml_inertia())

    head = find_named(bodyset, "Body", str(recipe["head"]["body"]))
    tg, hg = torso.find("attached_geometry"), head.find("attached_geometry")
    assert tg is not None and hg is not None
    for mesh in list(tg):
        if (mesh.findtext("mesh_file") or "").strip() in recipe["head"]["meshes"]:
            tg.remove(mesh)
            hg.append(mesh)

    bodies = {str(b.get("name")): b for b in bodyset}
    wrap_names = {str(w.get("name")) for b in bodyset for w in b.iterfind("WrapObjectSet/objects/*")}
    for w in merge.wraps:
        if w.name in wrap_names:
            raise ValueError(f"wrap object {w.name} exists already")
        wrap_names.add(w.name)
        b = bodies[w.body]
        wos = b.find("WrapObjectSet")
        if wos is None:
            wos = ET.SubElement(b, "WrapObjectSet")
        objs = wos.find("objects")
        if objs is None:
            objs = ET.SubElement(wos, "objects")
        objs.append(w.element)

    unlock = {str(c) for c in (recipe.get("unlock") or [])}
    for c in model.iter("Coordinate"):
        if c.get("name") in unlock:
            set_text(c, "locked", "false")
    model.set("name", f"{model.get('name')}_merged")
    tree.write(out, encoding="UTF-8", xml_declaration=True)
    return {"torsoMassBefore": whole.mass, "torsoMassAfter": left.mass}


def inertia6(text: str | None) -> tuple[Vec3, Vec3]:
    v = [float(x) for x in (text or "0 0 0 0 0 0").split()]
    return (v[0], v[1], v[2]), (v[3], v[4], v[5])


# ---------------------------------------------------------------------------------------------
# Second pass: muscle lengths, checks.


def check_paths(model: Any) -> int:
    """Every path point of every muscle lies on a body of the model; returns the point count."""
    bs = model.getBodySet()
    bodies = {str(bs.get(i).getName()) for i in range(bs.getSize())}
    n = 0
    ms = model.getMuscles()
    for i in range(ms.getSize()):
        pps = ms.get(i).getGeometryPath().getPathPointSet()
        for k in range(pps.getSize()):
            b = str(pps.get(k).getParentFrame().findBaseFrame().getName())
            if b not in bodies:
                raise ValueError(f"{ms.get(i).getName()}: point {k + 1} on {b}, outside the model's bodies")
            n += 1
    return n


def zero_pose(model: Any, overrides: dict[str, float]) -> dict[str, float]:
    cs = model.getCoordinateSet()
    return {**{str(cs.get(i).getName()): 0.0 for i in range(cs.getSize())}, **overrides}


def finish(osim: Any, xml_path: Path, merge: Merge, target_via: dict[str, float], out: Path) -> dict[str, Any]:
    """Load the merged XML, scale each merged muscle's optimal fibre and tendon slack lengths by
    the ratio of its muscle-tendon length here to its source length, check, and write."""
    model = osim.Model(str(xml_path))
    state = model.initSystem()
    points = check_paths(model)
    ref = osim.State(state)
    set_coordinates(model, ref, zero_pose(model, {}))
    via = osim.State(state)
    set_coordinates(model, via, zero_pose(model, target_via))
    ratios: dict[str, float] = {}
    ms = model.getMuscles()
    for rec in merge.muscles:
        mu = ms.get(rec.name)
        k = float(mu.getGeometryPath().getLength(via if rec.via else ref)) / rec.length
        ratios[rec.name] = k
        mu.setOptimalFiberLength(rec.lopt * k)
        mu.setTendonSlackLength(rec.lts * k)
    model.finalizeConnections()
    model.printToXML(str(out))
    return {"muscles": int(ms.getSize()), "pathPoints": points, "lengthRatio": ratios}


# ---------------------------------------------------------------------------------------------
# Joint angles: ik_full.mot (D-010).


@dataclass
class Coupler:
    dependent: str
    independents: list[str]
    function: Any
    scale: float


class Poser:
    """Poses the merged model from independent coordinate values; couplers give the rest."""

    def __init__(self, osim: Any, model: Any) -> None:
        self.osim = osim
        self.model = model
        self.state = model.initSystem()
        cs = model.getCoordinateSet()
        self.names = [str(cs.get(i).getName()) for i in range(cs.getSize())]
        self.defaults = {n: float(cs.get(n).getDefaultValue()) for n in self.names}
        self.couplers: list[Coupler] = []
        cons = model.getConstraintSet()
        for i in range(cons.getSize()):
            c = osim.CoordinateCouplerConstraint.safeDownCast(cons.get(i))
            if c is not None:
                ind = c.getIndependentCoordinateNames()
                self.couplers.append(Coupler(str(c.getDependentCoordinateName()), [str(ind.get(k)) for k in range(ind.getSize())], c.getFunction(), float(c.getPropertyByName("scale_factor").toString())))

    def complete(self, values: dict[str, float]) -> dict[str, float]:
        """Every coordinate: the given values, coupled ones from their couplers, else defaults."""
        out = {n: values.get(n, self.defaults[n]) for n in self.names}
        for c in self.couplers:
            if c.dependent in values:
                continue
            x = self.osim.Vector(len(c.independents), 0.0)
            for k, n in enumerate(c.independents):
                x.set(k, out[n])
            out[c.dependent] = c.scale * float(c.function.calcValue(x))
        return out

    def pose(self, values: dict[str, float]) -> None:
        cs = self.model.getCoordinateSet()
        for n, v in self.complete(values).items():
            cs.get(n).setValue(self.state, v, False)
        self.model.realizePosition(self.state)

    def rotation(self, body: str) -> Mat3:
        return to_mat3(self.model.getBodySet().get(body).getTransformInGround(self.state).R())


def ik_radians(ik: Table, base: Any) -> list[dict[str, float]]:
    """Each IK frame's coordinates in SI units: the base model's rotational coordinates in
    radians (as `load_model.kinematics_table` converts them), the rest unchanged."""
    to_rad = ik.header.get("inDegrees", "no").lower() == "yes"
    cs = base.getCoordinateSet()
    rotational = {str(cs.get(i).getName()) for i in range(cs.getSize()) if int(cs.get(i).getMotionType()) == 1}
    return [{c: (math.radians(ik.columns[c][i]) if to_rad and c in rotational else ik.columns[c][i]) for c in ik.labels[1:]} for i in range(len(ik.time))]


def static_values(table: Table) -> dict[str, float]:
    """Coordinate values of the static pose (`/jointset/<joint>/<coordinate>/value` columns)."""
    out = {}
    for label in table.labels[1:]:
        parts = label.strip("/").split("/")
        if len(parts) == 4 and parts[0] == "jointset" and parts[3] == "value":
            out[parts[2]] = table.columns[label][0]
    return out


def head_target(poser: Poser, static: dict[str, float], frames: Sequence[dict[str, float]], neck: Sequence[str], head: str) -> Mat3:
    """The head's orientation in ground over the trial (D-010): pitch and roll of the static pose
    (every neck angle 0), heading of the torso's mean heading over the trial."""
    zero = {c: 0.0 for c in neck}
    poser.pose({**static, **zero})
    r_static = poser.rotation(head)
    tilt = mmul(rot_y(-heading(r_static)), r_static)
    s = c = 0.0
    for f in frames:
        poser.pose({**f, **zero})
        h = heading(poser.rotation("torso"))
        s += math.sin(h)
        c += math.cos(h)
    return mmul(rot_y(math.atan2(s, c)), tilt)


def neck_values(totals: Vec3, lower: Sequence[str], upper: Sequence[str], shares: Sequence[float]) -> dict[str, float]:
    """The six neck angles of a total rotation per axis, split by `shares`."""
    out = {}
    for k in range(3):
        out[lower[k]] = shares[k] * totals[k]
        out[upper[k]] = (1.0 - shares[k]) * totals[k]
    return out


def solve3(j: list[list[float]], e: Vec3) -> Vec3:
    """x with j x = e (3x3, Cramer's rule)."""
    def det(m: list[list[float]]) -> float:
        return m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])

    d = det(j)
    out = [det([[e[r] if col == k else j[r][col] for col in range(3)] for r in range(3)]) / d for k in range(3)]
    return (out[0], out[1], out[2])


def solve_neck(poser: Poser, frame: dict[str, float], target: Mat3, lower: Sequence[str], upper: Sequence[str], shares: Sequence[float], head: str, start: Vec3) -> tuple[Vec3, float]:
    """Total neck rotation per axis that turns the head to `target`: Newton steps on the rotation
    vector from target to head. Returns the totals and the remaining error (rad)."""

    def err(t: Vec3) -> Vec3:
        poser.pose({**frame, **neck_values(t, lower, upper, shares)})
        return rotation_vector(mmul(mT(target), poser.rotation(head)))

    x = start
    e = err(x)
    for _ in range(20):
        if math.sqrt(vdot(e, e)) < 1e-12:
            break
        h = 1e-6
        cols = []
        for k in range(3):
            xk = [x[0], x[1], x[2]]
            xk[k] += h
            cols.append(vscale(1.0 / h, vsub(err((xk[0], xk[1], xk[2])), e)))
        x = vsub(x, solve3([[cols[c][r] for c in range(3)] for r in range(3)], e))
        e = err(x)
    return x, math.sqrt(vdot(e, e))


def write_mot(path: Path, labels: Sequence[str], rows: Sequence[Sequence[float]], name: str) -> None:
    """An OpenSim `.mot` in radians and metres, at full double precision."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write(f"{name}\nversion=1\nnRows={len(rows)}\nnColumns={len(labels)}\ninDegrees=no\nendheader\n")
        f.write("\t".join(labels) + "\n")
        for r in rows:
            f.write("\t".join(repr(float(v)) for v in r) + "\n")


def build_ik_full(osim: Any, merged: Path, base: Target, ik_path: Path, recipe: dict[str, Any], out: Path) -> dict[str, Any]:
    poser = Poser(osim, osim.Model(str(merged)))
    ik = read_sto(ik_path)
    frames = ik_radians(ik, base.model)
    static = static_values(read_sto(REPO / recipe["staticPose"]))
    lower, upper = [str(c) for c in recipe["neck"]["lower"]], [str(c) for c in recipe["neck"]["upper"]]
    head = str(recipe["head"]["body"])
    cs = poser.model.getCoordinateSet()
    rng = {n: (float(cs.get(n).getRangeMin()), float(cs.get(n).getRangeMax())) for n in lower + upper}
    shares = group_shares([rng[n] for n in lower], [rng[n] for n in upper])
    target = head_target(poser, static, frames, lower + upper, head)
    rows = []
    worst = 0.0
    x = ZERO
    for i, f in enumerate(frames):
        x, e = solve_neck(poser, f, target, lower, upper, shares, head, x)
        worst = max(worst, e)
        full = poser.complete({**f, **neck_values(x, lower, upper, shares)})
        rows.append([ik.time[i], *[full[n] for n in poser.names]])
    write_mot(out, ["time", *poser.names], rows, "ik_full")
    return {"frames": len(rows), "neckShares": dict(zip(("extension", "bending", "rotation"), shares)), "headErrorMax": worst}


# ---------------------------------------------------------------------------------------------
# Main.


def via_pose(spec: dict[str, Any], ik: Table) -> tuple[dict[str, float], dict[str, float]]:
    """The via pose of a source and its Rajagopal counterpart (both arms): per source coordinate,
    the trial mean of a Rajagopal coordinate (degrees to radians) plus an offset."""
    deg = ik.header.get("inDegrees", "no").lower() == "yes"
    src: dict[str, float] = {}
    tgt: dict[str, float] = {}
    for c, v in (spec.get("viaPose") or {}).items():
        m = mean(ik.columns[v["from"]])
        r = math.radians(m) if deg else m
        src[str(c)] = r + float(v.get("offset", 0.0))
        tgt[str(v["from"])] = r
        tgt[re.sub(r"_r$", "_l", str(v["from"]))] = r
    return src, tgt


def build(model_path: Path, ik_path: Path, recipe_path: Path, out_model: Path, out_ik: Path) -> dict[str, Any]:
    osim = opensim_module()
    osim.ModelVisualizer.addDirToGeometrySearchPaths(str(model_path.resolve().parent / "Geometry"))
    recipe = load_recipe(recipe_path)
    target = Target(osim, model_path, ScaleFactors(REPO / recipe["scaleSet"]), recipe)
    ik = read_sto(ik_path)
    base_xml = ET.parse(model_path).getroot()
    merge = Merge()
    target_via: dict[str, float] = {}
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        sources = []
        for spec in recipe["sources"]:
            src_via, tgt_via = via_pose(spec, ik)
            target_via.update(tgt_via)
            sources.append(Source(osim, spec, src_via, tmp))
        trunk = next(s for s in sources if s.spec.get("replacesJoint"))
        generic_torso = float(trunk.body("torso").getMass()) + sum(float(trunk.body(b).getMass()) for b in trunk.new_bodies)
        mass_ratio = float(target.model.getBodySet().get("torso").getMass()) / generic_torso
        for src in sources:
            mapper = Mapper(src, target, recipe)
            collect_bodies(mapper, merge, mass_ratio)
            collect_joints(mapper, merge, base_xml)
            collect_muscles(mapper, merge)
        raw = tmp / "merged_raw.osim"
        torso = write_merged_xml(model_path, merge, target, recipe, raw)
        out_model.parent.mkdir(parents=True, exist_ok=True)
        info = finish(osim, raw, merge, target_via, out_model)
    ik_info = build_ik_full(osim, out_model, target, ik_path, recipe, out_ik)
    by_source: dict[str, int] = {}
    for rec in merge.muscles:
        by_source[rec.source] = by_source.get(rec.source, 0) + 1
    return {**info, **torso, **ik_info, "massRatio": mass_ratio, "musclesBySource": by_source, "lumbarShares": merge.shares}


def main(argv: Sequence[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="python -m pipeline.build_model", description=doc.split("\n")[0])
    ap.add_argument("--model", type=Path, default=REPO / paths.SCALED_MODEL, help="scaled Rajagopal model (.osim)")
    ap.add_argument("--ik", type=Path, default=REPO / paths.IK_MOTION, help="inverse kinematics (.mot)")
    ap.add_argument("--recipe", type=Path, default=REPO / paths.MERGE_RECIPE, help="merge recipe (.yaml)")
    ap.add_argument("--out-model", type=Path, default=REPO / paths.MERGED_MODEL)
    ap.add_argument("--out-ik", type=Path, default=REPO / paths.IK_FULL)
    ap.add_argument("--report", type=Path, help="write the build summary (JSON) here")
    a = ap.parse_args(argv)
    info = build(a.model, a.ik, a.recipe, a.out_model, a.out_ik)
    if a.report:
        a.report.write_text(json.dumps(info, indent=1) + "\n")
    print(
        f"build_model: {info['muscles']} muscles {info['musclesBySource']}, {info['pathPoints']} path points; "
        f"torso {info['torsoMassBefore']:.2f} -> {info['torsoMassAfter']:.2f} kg; head error {info['headErrorMax']:.1e} rad; "
        f"wrote {a.out_model}, {a.out_ik}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
