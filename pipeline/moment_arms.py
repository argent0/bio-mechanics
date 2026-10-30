"""Stage `computeMomentArms`: moment arms, muscle-tendon lengths and velocities per frame.

For every frame of `kinematics.csv` (filtered coordinates from `loadModel`) the model is posed
at the frame's coordinate values and, for every muscle, OpenSim reports
  - the muscle-tendon length L (m): the length of the muscle's geometry path, origin to
    insertion through its via points and wrapping surfaces;
  - the moment arm r (m) about each coordinate the muscle spans
    (`Muscle.computeMomentArm`, which accounts for the knee's coupled patella coordinate).

Sign convention (OpenSim): r = −∂L/∂q. A positive moment arm means the muscle's tension rotates
the coordinate in its positive direction; a muscle with a positive moment arm shortens as the
coordinate increases. Example: `knee_angle_r` is knee flexion (positive = flexed), so the knee
extensors (vasti, rectus femoris) have negative moment arms about it.

Spanning. A muscle spans a coordinate when |r| exceeds `SPAN_THRESHOLD_M` at some frame. The
search covers every unlocked, unconstrained coordinate, screened on every `SCREEN_STRIDE`-th
frame (plus the last); a muscle has exactly zero moment arm about a coordinate whose joint lies
outside its path, so the screen separates spanned from unspanned pairs cleanly.

Velocity v = dL/dt (m/s): central differences of L over time (`central_difference`). The
coordinates are low-pass filtered at 6 Hz in `loadModel`, so L is smooth and needs no further
smoothing. v < 0: the muscle-tendon unit shortens (concentric work when the muscle is active);
v > 0: it lengthens (eccentric work, braking); v ≈ 0: isometric.

Outputs (defaults under `data/work/`):
  --out-moment-arms  moment_arms.csv   long format: `time`, `muscle`, `coordinate`, `moment_arm` (m),
                                       one row per frame and spanned (muscle, coordinate) pair
  --out-lengths      mt_lengths.csv    long format: `time`, `muscle`, `length` (m), `velocity` (m/s)
Run with the OpenSim environment's Python: `python -m pipeline.moment_arms`.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.load_model import DEFAULT_MODEL, WORK, Table, central_difference, opensim_module, read_csv

SPAN_THRESHOLD_M = 1e-3
"""A muscle spans a coordinate when its moment arm magnitude exceeds 1 mm at some frame."""

SCREEN_STRIDE = 10


def pose(model: Any, state: Any, kin: Table, frame: int) -> None:
    """Set every coordinate to its value at `frame` and realise positions."""
    cs = model.getCoordinateSet()
    for i in range(cs.getSize()):
        c = cs.get(i)
        c.setValue(state, kin.columns[c.getName()][frame], False)
    model.realizePosition(state)


def spanned_pairs(model: Any, state: Any, kin: Table) -> list[tuple[int, str]]:
    """(muscle index, coordinate name) pairs whose |moment arm| exceeds the threshold."""
    cs = model.getCoordinateSet()
    candidates = [cs.get(i) for i in range(cs.getSize()) if not cs.get(i).getLocked(state) and not cs.get(i).isConstrained(state)]
    ms = model.getMuscles()
    n = len(kin.time)
    frames = sorted(set(range(0, n, SCREEN_STRIDE)) | {n - 1})
    peak: dict[tuple[int, str], float] = {}
    for f in frames:
        pose(model, state, kin, f)
        for k in range(ms.getSize()):
            m = ms.get(k)
            for c in candidates:
                key = (k, c.getName())
                peak[key] = max(peak.get(key, 0.0), abs(m.computeMomentArm(state, c)))
    return [key for key, r in peak.items() if r > SPAN_THRESHOLD_M]


def compute(model: Any, state: Any, kin: Table) -> tuple[list[str], dict[tuple[str, str], list[float]], dict[str, list[float]]]:
    """Muscle names, moment arms per spanned (muscle, coordinate), and lengths per muscle."""
    ms = model.getMuscles()
    cs = model.getCoordinateSet()
    names = [ms.get(k).getName() for k in range(ms.getSize())]
    pairs = spanned_pairs(model, state, kin)
    arms: dict[tuple[str, str], list[float]] = {(names[k], c): [] for k, c in pairs}
    lengths: dict[str, list[float]] = {n: [] for n in names}
    for f in range(len(kin.time)):
        pose(model, state, kin, f)
        for k, c in pairs:
            arms[(names[k], c)].append(float(ms.get(k).computeMomentArm(state, cs.get(c))))
        for k, n in enumerate(names):
            lengths[n].append(float(ms.get(k).getLength(state)))
    return names, arms, lengths


def run(model_path: Path, kin_path: Path, out_arms: Path, out_lengths: Path) -> tuple[int, int]:
    """Write both outputs; return (number of spanned pairs, number of frames)."""
    osim = opensim_module()
    model = osim.Model(str(model_path))
    state = model.initSystem()
    kin = read_csv(kin_path)
    names, arms, lengths = compute(model, state, kin)
    t = kin.time
    out_arms.parent.mkdir(parents=True, exist_ok=True)
    with out_arms.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "muscle", "coordinate", "moment_arm"])
        for i, ti in enumerate(t):
            for (m, c), r in arms.items():
                w.writerow([f"{ti:.10g}", m, c, f"{r[i]:.8g}"])
    velocities = {n: central_difference(t, lengths[n]) for n in names}
    with out_lengths.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time", "muscle", "length", "velocity"])
        for i, ti in enumerate(t):
            for n in names:
                w.writerow([f"{ti:.10g}", n, f"{lengths[n][i]:.8g}", f"{velocities[n][i]:.8g}"])
    return len(arms), len(t)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.moment_arms", description=__doc__.split("\n")[0])
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="merged OpenSim model (.osim), `pipeline_paths.MERGED_MODEL`")
    p.add_argument("--kinematics", type=Path, default=WORK / "kinematics.csv", help="output of loadModel")
    p.add_argument("--out-moment-arms", type=Path, default=WORK / "moment_arms.csv")
    p.add_argument("--out-lengths", type=Path, default=WORK / "mt_lengths.csv")
    a = p.parse_args(argv)
    pairs, frames = run(a.model, a.kinematics, a.out_moment_arms, a.out_lengths)
    print(f"moment_arms: {pairs} muscle-coordinate pairs x {frames} frames; wrote {a.out_moment_arms}, {a.out_lengths}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
