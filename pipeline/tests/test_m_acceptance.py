"""Workstream M acceptance: static optimisation on the merged model over the stride.

Static optimisation on the merged model (462 muscles) takes minutes, so these tests read the
outputs the pipeline wrote (`ninja -f generated/pipeline.ninja`: `data/work/static_opt.json`,
`forces.csv`, `activations.csv`, `grf.csv`) and skip when they come from another model. The leg
reference runs here: stages 1-2 on the scaled Rajagopal model (legs only) and its raw inverse
kinematics, today's leg-only pipeline (≈ 30 s).

Stride: from the first to the second right initial contact (vertical GRF above the contact
threshold, `contact_intervals`), the stride the knowledge graph describes.

Pinned numbers (reserve RMS over the stride, N·m; activation RMS change over the stride):
  - `ARM_RESERVE_RMS` on every shoulder, elbow, forearm and wrist coordinate, both arms;
  - `NECK_RESERVE_RMS` on the six neck coordinates;
  - `LUMBAR_RESERVE_RMS` on the three lumbar coordinates (FBLS trunk, D-011);
  - `LEG_ACTIVATION_RMS`: every one of the 80 leg muscles changes by less than this from the
    leg-only run.
"""
from __future__ import annotations

import json
import math
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from pipeline.load_model import REPO, Table, contact_intervals, read_csv

import pipeline_paths as paths

ARM_RESERVE_RMS = 2.0
NECK_RESERVE_RMS = 1.0
LUMBAR_RESERVE_RMS = 10.0
LEG_ACTIVATION_RMS = 0.02
ARM = ("arm_flex", "arm_add", "arm_rot", "elbow_flex", "pro_sup", "wrist_flex", "wrist_dev")
WORK = REPO / "data" / "work"


class Run:
    def __init__(self, d: Path) -> None:
        self.settings: dict[str, Any] = json.loads((d / "static_opt.json").read_text())
        self.forces = read_csv(d / "forces.csv")
        self.act = read_csv(d / "activations.csv")
        grf = read_csv(d / "grf.csv")
        on = [a for a, _ in contact_intervals(grf.time, grf.columns["force_y_r"]) if a > grf.time[0]]
        self.stride = (on[0], on[1])
        self.frames = [i for i, t in enumerate(self.act.time) if on[0] <= t <= on[1]]

    def rms(self, table: Table, column: str) -> float:
        v = table.columns[column]
        return math.sqrt(sum(v[i] ** 2 for i in self.frames) / len(self.frames))

    def reserves(self) -> dict[str, float]:
        return {a["coordinate"]: self.rms(self.forces, a["name"]) for a in self.settings["actuators"] if a["kind"] == "reserve"}


@pytest.fixture(scope="module")
def merged() -> Run:
    f = WORK / "static_opt.json"
    if not f.exists() or json.loads(f.read_text())["model"] != paths.MERGED_MODEL:
        pytest.skip("data/work/static_opt.json comes from the pipeline on the merged model (ninja)")
    return Run(WORK)


@pytest.fixture(scope="module")
def legs(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Run]:
    pytest.importorskip("opensim")
    from pipeline import load_model, static_opt

    d = tmp_path_factory.mktemp("legs")
    model = ["--model", str(REPO / paths.SCALED_MODEL)]
    assert load_model.main([*model, "--ik", str(REPO / paths.IK_MOTION), "--out-model", str(d / "model.json"), "--out-kinematics", str(d / "kinematics.csv"), "--out-grf", str(d / "grf.csv")]) == 0
    assert static_opt.main([*model, "--kinematics", str(d / "kinematics.csv"), "--out-activations", str(d / "activations.csv"), "--out-forces", str(d / "forces.csv"), "--out-settings", str(d / "static_opt.json"), "--scratch", str(d / "so")]) == 0
    yield Run(d)


def test_static_optimisation_covers_every_frame(merged: Run) -> None:
    assert merged.settings["frames"] == len(merged.act.time) == 238
    assert merged.frames and len(merged.act.labels) == 1 + 462


def test_arm_reserves_stay_small(merged: Run) -> None:
    r = merged.reserves()
    arm = {c: v for c, v in r.items() if c.rsplit("_", 1)[0] in ARM}
    assert len(arm) == 2 * len(ARM)
    print({c: round(v, 3) for c, v in sorted(arm.items())})
    assert max(arm.values()) < ARM_RESERVE_RMS


def test_neck_reserves_stay_small(merged: Run) -> None:
    neck = {c: v for c, v in merged.reserves().items() if c.startswith("neck_")}
    assert len(neck) == 6
    print({c: round(v, 3) for c, v in sorted(neck.items())})
    assert max(neck.values()) < NECK_RESERVE_RMS


def test_lumbar_reserves_stay_small(merged: Run) -> None:
    lumbar = {c: v for c, v in merged.reserves().items() if c.startswith("lumbar_")}
    assert len(lumbar) == 3
    print({c: round(v, 3) for c, v in sorted(lumbar.items())})
    assert max(lumbar.values()) < LUMBAR_RESERVE_RMS


def test_leg_activations_hold(merged: Run, legs: Run) -> None:
    """The merge leaves the leg muscles' activations within `LEG_ACTIVATION_RMS` of the leg-only
    pipeline, muscle by muscle over the stride."""
    assert merged.act.time == legs.act.time and merged.frames == legs.frames
    leg_muscles = legs.act.labels[1:]
    assert len(leg_muscles) == 80
    change = {}
    for m in leg_muscles:
        a, b = merged.act.columns[m], legs.act.columns[m]
        change[m] = math.sqrt(sum((a[i] - b[i]) ** 2 for i in merged.frames) / len(merged.frames))
    worst = sorted(change.items(), key=lambda kv: -kv[1])[:5]
    print("largest changes", [(m, round(v, 4)) for m, v in worst], "mean", round(sum(change.values()) / 80, 4))
    assert worst[0][1] < LEG_ACTIVATION_RMS
