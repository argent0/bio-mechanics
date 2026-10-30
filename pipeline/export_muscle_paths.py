"""Stage `exportMusclePaths`: muscle path points, activation, lengthening velocity and body poses
per frame, for the web viewer's tube muscles and animated bones.

Frames: every `step`-th frame of `kinematics.csv`, `step` = ceil(rate / `MAX_RATE_HZ`), so the
output runs at 25 Hz for the 100 Hz trial. Stage `loadModel` low-pass filters the coordinates at
6 Hz, so 25 Hz frames hold the motion, and the viewer interpolates between them. Frame rate,
`PATH_TOLERANCE_M` and `POSITION_DIGITS` together keep `data/out/` under 8 MB with all 462
muscles drawn. At each frame the merged model
(`pipeline_paths.MERGED_MODEL`: legs, trunk, arms and neck, 462 muscles) is posed at the filtered
coordinates (P1's `moment_arms.pose`) and OpenSim reports, in ground:
  - each muscle's current path (`GeometryPath.getCurrentPath`): its path points in order,
    conditional points included only while active; where the path wraps over a surface the arc
    OpenSim computes over the surface (`PathWrapPoint.getWrapPath`, expressed in the wrap
    point's frame) is inserted ahead of the arc's end point; consecutive points closer than
    `MIN_SPACING_M` merge into one (`merge_close`), and the polyline then keeps the fewest
    points that hold every dropped point within `PATH_TOLERANCE_M` of it (`simplify`,
    Ramer-Douglas-Peucker): a wrap arc of many short chords becomes a few, origin, insertion and
    every corner of the path stay;
  - each body's pose, for every body of the model (those `export_meshes` draws and those it
    lists as `unmeshed`): frame origin and orientation.
The stride bounds come from the gait events of `phases.csv` (`stride_bounds`).
Activation (`activations.csv`) and lengthening velocity (`mt_lengths.csv`, v > 0 lengthening:
eccentric when active; v < 0 shortening: concentric) are read at the same frames.

Output `data/out/muscle_paths.json` (the format the viewer reads):
  format     "bm-muscle-paths/1"
  frame      "ground": metres, y up, the trial's walking direction along +x
  rateHz     frames per second of the output
  time       [s] per frame
  stride     {start, end} in s: the opening and closing right initial contact of stride 0
             (`phases.csv`, stage `segmentPhases`), the stride whose phase percentages
             `graph.json` gives; the frames cover more of the trial than this stride
  bodies     {body: [[px, py, pz, qx, qy, qz, qw] per frame]}: the body frame's origin (m) and
             orientation (unit quaternion, glTF order) in ground; the meshes of
             `meshes/index.json` sit in these frames
  muscles    {muscle: {points, activation, velocity}} for every muscle of the model:
             points      per frame, the path as a flat list [x0, y0, z0, x1, y1, z1, ...] (m)
                         from origin to insertion; the count may change between frames
             activation  per frame, 0–1
             velocity    per frame, muscle-tendon lengthening velocity (m/s)
Rounding: positions to `POSITION_DIGITS` decimals (1 mm, a tenth of the viewer's tube radius),
quaternions to 5, activation to 3, velocity to 4.

Run with the OpenSim environment's Python from the repository root:
`python -m pipeline.export_muscle_paths`.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.label_roles import read_long
from pipeline.load_model import REPO, opensim_module, read_csv, sample_rate
from pipeline.segment_phases import GENERATED, Phases, read_phases

import pipeline_paths as paths  # noqa: E402  (generated/py: see `GENERATED`)

FORMAT = "bm-muscle-paths/1"
MAX_RATE_HZ = 30.0
"""Upper bound of the output frame rate (Hz)."""
MIN_SPACING_M = 0.001
"""Consecutive path points closer than this (m) merge into one."""
PATH_TOLERANCE_M = 0.002
"""Every path point `simplify` drops lies within this distance (m) of the polyline it keeps."""
POSITION_DIGITS = 3

Vec3 = tuple[float, float, float]


def frame_step(rate_hz: float, max_rate_hz: float = MAX_RATE_HZ) -> int:
    """Every how many input frames one output frame falls."""
    return max(1, math.ceil(rate_hz / max_rate_hz - 1e-9))


def merge_close(points: Sequence[Vec3], spacing: float = MIN_SPACING_M) -> list[Vec3]:
    """`points` without each point closer than `spacing` to the point kept before it; the last
    point (the insertion) always stays."""
    out: list[Vec3] = []
    for i, p in enumerate(points):
        if out and math.dist(out[-1], p) < spacing:
            if i == len(points) - 1:
                out[-1] = p
            continue
        out.append(p)
    return out


def segment_distance(p: Vec3, a: Vec3, b: Vec3) -> float:
    """Distance from `p` to the segment from `a` to `b`."""
    ab = [b[i] - a[i] for i in range(3)]
    ap = [p[i] - a[i] for i in range(3)]
    n = sum(x * x for x in ab)
    t = 0.0 if n == 0 else max(0.0, min(1.0, sum(ab[i] * ap[i] for i in range(3)) / n))
    return math.dist(p, tuple(a[i] + t * ab[i] for i in range(3)))


def simplify(points: Sequence[Vec3], tolerance: float = PATH_TOLERANCE_M) -> list[Vec3]:
    """Ramer-Douglas-Peucker: the subsequence of `points`, first and last kept, such that every
    dropped point lies within `tolerance` of the kept polyline between its kept neighbours."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        far, at = 0.0, -1
        for k in range(i + 1, j):
            d = segment_distance(points[k], points[i], points[j])
            if d > far:
                far, at = d, k
        if at >= 0 and far > tolerance:
            keep[at] = True
            stack += [(i, at), (at, j)]
    return [p for p, k in zip(points, keep) if k]


def quaternion(r: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    """Unit quaternion (x, y, z, w) of a rotation matrix (rows), w ≥ 0."""
    t = r[0][0] + r[1][1] + r[2][2]
    if t > 0:
        s = 2.0 * math.sqrt(1.0 + t)
        q = ((r[2][1] - r[1][2]) / s, (r[0][2] - r[2][0]) / s, (r[1][0] - r[0][1]) / s, 0.25 * s)
    elif r[0][0] > r[1][1] and r[0][0] > r[2][2]:
        s = 2.0 * math.sqrt(1.0 + r[0][0] - r[1][1] - r[2][2])
        q = (0.25 * s, (r[0][1] + r[1][0]) / s, (r[0][2] + r[2][0]) / s, (r[2][1] - r[1][2]) / s)
    elif r[1][1] > r[2][2]:
        s = 2.0 * math.sqrt(1.0 + r[1][1] - r[0][0] - r[2][2])
        q = ((r[0][1] + r[1][0]) / s, 0.25 * s, (r[1][2] + r[2][1]) / s, (r[0][2] - r[2][0]) / s)
    else:
        s = 2.0 * math.sqrt(1.0 + r[2][2] - r[0][0] - r[1][1])
        q = ((r[0][2] + r[2][0]) / s, (r[1][2] + r[2][1]) / s, 0.25 * s, (r[1][0] - r[0][1]) / s)
    n = math.sqrt(sum(c * c for c in q))
    x, y, z, w = (c / n for c in q)
    return (-x, -y, -z, -w) if w < 0 else (x, y, z, w)


def stride_bounds(p: Phases, stride: int = 0) -> dict[str, float]:
    """Times of the right initial contacts that open and close `stride`."""
    ics = [p.event_time(e) for e in sorted(p.events, key=lambda e: e.frame) if e.event == "initialContact"]
    if len(ics) < stride + 2:
        raise ValueError(f"stride {stride} is incomplete: {len(ics)} initial contacts")
    return {"start": ics[stride], "end": ics[stride + 1]}


def _vec(v: Any) -> Vec3:
    return (float(v.get(0)), float(v.get(1)), float(v.get(2)))


def current_path(osim: Any, muscle: Any, state: Any) -> list[Vec3]:
    """The muscle's path in ground, with wrap arcs (module docstring)."""
    cp = muscle.getGeometryPath().getCurrentPath(state)
    pts: list[Vec3] = []
    for i in range(cp.getSize()):
        pp = cp.get(i)
        if pp.getConcreteClassName() == "PathWrapPoint":
            arc = osim.PathWrapPoint.safeDownCast(pp).getWrapPath(state)
            frame = pp.getParentFrame()
            pts += [_vec(frame.findStationLocationInGround(state, arc.get(k))) for k in range(arc.getSize())]
        pts.append(_vec(pp.getLocationInGround(state)))
    return simplify(merge_close(pts))


def run(model_path: Path, kin_path: Path, act_path: Path, len_path: Path, phases_path: Path, out: Path) -> dict[str, Any]:
    from pipeline.moment_arms import pose

    osim = opensim_module()
    model = osim.Model(str(model_path))
    state = model.initSystem()
    kin = read_csv(kin_path)
    act = read_csv(act_path)
    vel = read_long(len_path, ("muscle",), "velocity", kin.time)
    step = frame_step(sample_rate(kin.time))
    frames = list(range(0, len(kin.time), step))
    ms = model.getMuscles()
    names = [ms.get(k).getName() for k in range(ms.getSize())]
    bodyset = model.getBodySet()
    body_names = [bodyset.get(k).getName() for k in range(bodyset.getSize())]
    bodies: dict[str, list[list[float]]] = {b: [] for b in body_names}
    points: dict[str, list[list[float]]] = {m: [] for m in names}
    d = POSITION_DIGITS
    for f in frames:
        pose(model, state, kin, f)
        for b in body_names:
            tr = bodyset.get(b).getTransformInGround(state)
            p = _vec(tr.p())
            rot = tr.R()
            q = quaternion([[float(rot.get(i, j)) for j in range(3)] for i in range(3)])
            bodies[b].append([round(c, d) for c in p] + [round(c, 5) for c in q])
        for k, m in enumerate(names):
            pts = current_path(osim, ms.get(k), state)
            points[m].append([round(c, d) for p in pts for c in p])
    doc = {
        "format": FORMAT,
        "frame": "ground",
        "rateHz": round(sample_rate(kin.time) / step, 6),
        "time": [kin.time[f] for f in frames],
        "stride": stride_bounds(read_phases(phases_path)),
        "bodies": bodies,
        "muscles": {
            m: {
                "points": points[m],
                "activation": [round(act.columns[m][f], 3) for f in frames],
                "velocity": [round(vel[(m,)][f], 4) for f in frames],
            }
            for m in names
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, separators=(",", ":")) + "\n")
    return doc


def main(argv: Sequence[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="python -m pipeline.export_muscle_paths", description=doc.split("\n")[0])
    ap.add_argument("--model", type=Path, default=REPO / paths.MERGED_MODEL, help="merged OpenSim model (.osim)")
    ap.add_argument("--kinematics", type=Path, default=REPO / paths.KINEMATICS)
    ap.add_argument("--activations", type=Path, default=REPO / paths.ACTIVATIONS)
    ap.add_argument("--mt-lengths", type=Path, default=REPO / paths.MT_LENGTHS)
    ap.add_argument("--phases", type=Path, default=REPO / paths.PHASES, help="phases.csv (stride bounds)")
    ap.add_argument("--out", type=Path, default=REPO / paths.MUSCLE_PATHS)
    a = ap.parse_args(argv)
    out = run(a.model, a.kinematics, a.activations, a.mt_lengths, a.phases, a.out)
    size = a.out.stat().st_size / 1e6
    print(f"export_muscle_paths: {len(out['time'])} frames at {out['rateHz']:g} Hz, {len(out['muscles'])} muscles, {size:.1f} MB; wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
