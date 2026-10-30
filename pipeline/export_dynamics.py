"""Stage `exportDynamics`: each right-leg muscle's moment about each labelled joint coordinate,
and the coordinate's angle, per frame, for the web's dynamics panel.

Moments. A muscle's moment about a coordinate at a frame is a·F·r in N·m, the moment of
decision D-002 that stage `labelRoles` integrates: activation a (`activations.csv`), max isometric
force F (`model.json`), moment arm r (`moment_arms.csv`; r > 0 turns the coordinate in its
positive direction). A positive moment therefore pushes the coordinate toward its `positive`
action, a negative one toward its `negative` action.

Scope, from `roles.yaml` (`label_roles.Config`): the coordinates of `coordinates`, in that order,
and per coordinate the muscles ending in `muscleSuffix` whose |r| reaches `momentArmMinM` at some
frame of the stride (the muscles of `roles.json` `crosses`).

Frames: the frames of `muscle_paths.json` (`export_muscle_paths.frame_step`), so the two files
share one time base and the viewer's playhead indexes both.

Output `data/out/dynamics.json`:
  format       "bm-dynamics/1"
  rateHz       frames per second
  time         [s] per frame
  stride       {start, end} in s, as in `muscle_paths.json` (`export_muscle_paths.stride_bounds`)
  coordinates  [{coordinate, joint, positive, negative, angleDeg, moments}] in `roles.yaml` order:
               joint               graph id of the joint, e.g. `joint:knee_r`
               positive, negative  graph ids of the joint action each direction of the
                                   coordinate is (anatomy.yaml `coordinates`), e.g.
                                   `action:knee_flexion_r`, `action:knee_extension_r`
               angleDeg            per frame, the coordinate's angle (degrees, OpenSim sign)
               moments             {muscle graph id: per frame, a·F·r (N·m)}, muscles in model order
Rounding: angles to 2 decimals, moments to 3 (1 mN·m).

Run from the repository root: `python -m pipeline.export_dynamics` (pure Python; any interpreter
with PyYAML).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.enrich_anatomy import load_anatomy
from pipeline.export_graph import node_id
from pipeline.export_muscle_paths import frame_step, stride_bounds
from pipeline.label_roles import Config, Trial, load_config, read_trial
from pipeline.load_model import REPO, sample_rate
from pipeline.segment_phases import GENERATED, Phases, read_phases

import pipeline_paths as paths  # noqa: E402  (generated/py: see `GENERATED`)

FORMAT = "bm-dynamics/1"


def stride_frames(time: Sequence[float], stride: dict[str, float]) -> tuple[int, int]:
    """First and last frame of the stride, both included."""
    f0 = min(range(len(time)), key=lambda i: abs(time[i] - stride["start"]))
    f1 = min(range(len(time)), key=lambda i: abs(time[i] - stride["end"]))
    return f0, f1


def crossing(trial: Trial, coord: str, cfg: Config, f0: int, f1: int) -> list[str]:
    """Right-leg muscles whose |moment arm| about `coord` reaches the floor within the stride."""
    return [
        m
        for m in trial.activation
        if m.endswith(cfg.muscle_suffix)
        and (r := trial.moment_arm.get((m, coord))) is not None
        and max(abs(x) for x in r[f0 : f1 + 1]) >= cfg.moment_arm_min_m
    ]


def build(trial: Trial, p: Phases, cfg: Config, anatomy: dict[str, Any]) -> dict[str, Any]:
    """The contents of `dynamics.json`."""
    step = frame_step(sample_rate(trial.time))
    frames = list(range(0, len(trial.time), step))
    stride = stride_bounds(p)
    f0, f1 = stride_frames(trial.time, stride)
    coords = []
    for coord in cfg.coordinates:
        c = anatomy["coordinates"][coord]
        q = trial.coordinates[coord]
        moments = {}
        for m in crossing(trial, coord, cfg, f0, f1):
            a, r, force = trial.activation[m], trial.moment_arm[(m, coord)], trial.max_force[m]
            moments[node_id("muscle", m)] = [round(a[f] * force * r[f], 3) for f in frames]
        coords.append(
            {
                "coordinate": coord,
                "joint": node_id("joint", c["joint"]),
                "positive": node_id("jointAction", c["positive"]),
                "negative": node_id("jointAction", c["negative"]),
                "angleDeg": [round(math.degrees(q[f]), 2) for f in frames],
                "moments": moments,
            }
        )
    return {
        "format": FORMAT,
        "rateHz": round(sample_rate(trial.time) / step, 6),
        "time": [trial.time[f] for f in frames],
        "stride": stride,
        "coordinates": coords,
    }


def main(argv: Sequence[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="python -m pipeline.export_dynamics", description=doc.split("\n")[0])
    ap.add_argument("--activations", type=Path, default=REPO / paths.ACTIVATIONS)
    ap.add_argument("--moment-arms", type=Path, default=REPO / paths.MOMENT_ARMS)
    ap.add_argument("--mt-lengths", type=Path, default=REPO / paths.MT_LENGTHS)
    ap.add_argument("--phases", type=Path, default=REPO / paths.PHASES)
    ap.add_argument("--kinematics", type=Path, default=REPO / paths.KINEMATICS)
    ap.add_argument("--config", type=Path, default=REPO / paths.ROLE_THRESHOLDS)
    ap.add_argument("--anatomy", type=Path, default=REPO / paths.CURATED_ANATOMY)
    ap.add_argument("--model", type=Path, default=REPO / paths.MODEL, help="model.json (max isometric forces)")
    ap.add_argument("--out", type=Path, default=REPO / paths.DYNAMICS)
    a = ap.parse_args(argv)
    trial = read_trial(a.activations, a.moment_arms, a.mt_lengths, a.kinematics, a.model)
    out = build(trial, read_phases(a.phases), load_config(a.config), load_anatomy(a.anatomy))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    n = sum(len(c["moments"]) for c in out["coordinates"])
    print(f"export_dynamics: {len(out['time'])} frames, {len(out['coordinates'])} coordinates, {n} muscle moments; wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
