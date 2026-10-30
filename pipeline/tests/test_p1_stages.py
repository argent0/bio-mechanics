"""Integration and plausibility tests of pipeline stages 1–3.

The OpenSim tests run the three stages once into a temporary directory (≈ 30 s) and skip when
`opensim` is unimportable. The gait-window helpers below are pure and run anywhere.

Gait windows. Contact comes from the vertical GRF in `grf.csv` with the stage threshold
(`CONTACT_THRESHOLD_N` = 20 N). In this trial the left foot stands outside the force plates
before ≈0.4 s and after ≈1.98 s, so the left GRF shows one stance only. Left contacts outside
the plates are placed one stride before and after the measured one, the stride being the time
between the two right initial contacts (gait is periodic within a trial). Right single-leg
stance is right contact minus every left contact.

Plausibility floors (activation, 0–1):
  - `TIBANT_FLOOR` = 0.05: tibialis anterior mean over 0–10 % of each right stance; it lowers
    the foot to the ground after heel strike (eccentric dorsiflexor).
  - `GLMED_FLOOR` = 0.10: gluteus medius (mean of its 3 parts) over right single-leg stance; it
    holds the pelvis level over the stance leg (hip abductor).
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

import pytest

from pipeline.load_model import CONTACT_THRESHOLD_N, SPEED_SUFFIX, Table, contact_intervals, read_csv

Interval = tuple[float, float]

TIBANT_FLOOR = 0.05
GLMED_FLOOR = 0.10
EARLY_STANCE = (0.0, 0.1)
"""Fractions of stance: the 0–10 % window after heel strike."""
MID_STANCE = (0.2, 0.5)
"""Fractions of stance: mid-stance, from about opposite toe-off to before heel-off."""
GLMED = ("glmed1_r", "glmed2_r", "glmed3_r")
KNEE_EXTENSORS = ("vasint_r", "vaslat_r", "vasmed_r", "recfem_r")


# ---------------------------------------------------------------------------------------------
# Gait-window helpers (pure).


def complete(intervals: Sequence[Interval], t0: float, t1: float) -> list[Interval]:
    """Intervals that start after `t0` and end before `t1` (both events observed)."""
    return [(a, b) for a, b in intervals if a > t0 and b < t1]


def subtract(base: Sequence[Interval], cuts: Sequence[Interval]) -> list[Interval]:
    """Parts of `base` outside every interval of `cuts` (open cuts: their ends stay in)."""
    out = list(base)
    for c0, c1 in cuts:
        nxt: list[Interval] = []
        for a, b in out:
            if c1 <= a or c0 >= b:
                nxt.append((a, b))
                continue
            if a < c0:
                nxt.append((a, c0))
            if c1 < b:
                nxt.append((c1, b))
        out = nxt
    return out


def fraction(interval: Interval, lo: float, hi: float) -> Interval:
    a, b = interval
    return (a + lo * (b - a), a + hi * (b - a))


def gaps(intervals: Sequence[Interval]) -> list[Interval]:
    """The intervals between consecutive intervals (e.g. swing between stances)."""
    return [(intervals[i][1], intervals[i + 1][0]) for i in range(len(intervals) - 1)]


def periodic(intervals: Sequence[Interval], stride: float) -> list[Interval]:
    """`intervals` plus copies shifted one stride earlier and later."""
    return sorted({(a + k * stride, b + k * stride) for a, b in intervals for k in (-1, 0, 1)})


def mean_over(t: Sequence[float], x: Sequence[float], windows: Sequence[Interval]) -> float:
    vals = [xi for ti, xi in zip(t, x) if any(a <= ti <= b for a, b in windows)]
    assert vals, f"no frames in {windows}"
    return sum(vals) / len(vals)


def test_subtract_and_gaps() -> None:
    assert subtract([(0.0, 10.0)], [(2.0, 3.0), (9.0, 12.0)]) == [(0.0, 2.0), (3.0, 9.0)]
    assert gaps([(0.0, 1.0), (2.0, 3.0)]) == [(1.0, 2.0)]
    assert periodic([(1.0, 2.0)], 5.0) == [(-4.0, -3.0), (1.0, 2.0), (6.0, 7.0)]
    assert complete([(0.0, 1.0), (2.0, 3.0), (4.0, 5.0)], 0.0, 5.0) == [(2.0, 3.0)]
    assert fraction((2.0, 4.0), 0.0, 0.1) == pytest.approx((2.0, 2.2))


# ---------------------------------------------------------------------------------------------
# OpenSim integration.


class Outputs:
    def __init__(self, d: Path) -> None:
        self.dir = d
        self.model = json.loads((d / "model.json").read_text())
        self.kin = read_csv(d / "kinematics.csv")
        self.grf = read_csv(d / "grf.csv")
        self.act = read_csv(d / "activations.csv")
        self.forces = read_csv(d / "forces.csv")
        self.settings = json.loads((d / "static_opt.json").read_text())
        self.arms: dict[tuple[str, str], list[float]] = defaultdict(list)
        with (d / "moment_arms.csv").open() as f:
            for row in csv.DictReader(f):
                self.arms[(row["muscle"], row["coordinate"])].append(float(row["moment_arm"]))
        self.length: dict[str, list[float]] = defaultdict(list)
        self.velocity: dict[str, list[float]] = defaultdict(list)
        with (d / "mt_lengths.csv").open() as f:
            for row in csv.DictReader(f):
                self.length[row["muscle"]].append(float(row["length"]))
                self.velocity[row["muscle"]].append(float(row["velocity"]))

    def contacts(self, side: str) -> list[Interval]:
        return contact_intervals(self.grf.time, self.grf.columns[f"force_y_{side}"], CONTACT_THRESHOLD_N)


@pytest.fixture(scope="module")
def out(tmp_path_factory: pytest.TempPathFactory) -> Outputs:
    pytest.importorskip("opensim")
    from pipeline import load_model, moment_arms, static_opt

    d = tmp_path_factory.mktemp("p1")
    assert load_model.main(["--out-model", str(d / "model.json"), "--out-kinematics", str(d / "kinematics.csv"), "--out-grf", str(d / "grf.csv")]) == 0
    assert static_opt.main(
        [
            "--kinematics", str(d / "kinematics.csv"),
            "--out-activations", str(d / "activations.csv"),
            "--out-forces", str(d / "forces.csv"),
            "--out-settings", str(d / "static_opt.json"),
            "--scratch", str(d / "static_opt"),
        ]
    ) == 0
    assert moment_arms.main(
        ["--kinematics", str(d / "kinematics.csv"), "--out-moment-arms", str(d / "moment_arms.csv"), "--out-lengths", str(d / "mt_lengths.csv")]
    ) == 0
    return Outputs(d)


def muscles(o: Outputs) -> list[str]:
    return [m["name"] for m in o.model["muscles"]]


def test_model_summary(out: Outputs) -> None:
    m = out.model
    assert len(m["muscles"]) == 80 and len(m["coordinates"]) == 39
    glmed = next(x for x in m["muscles"] if x["name"] == "glmed1_r")
    assert (glmed["originBody"], glmed["insertionBody"]) == ("pelvis", "femur_r")
    assert glmed["maxIsometricForce"] > 0 and glmed["optimalFiberLength"] > 0
    knee = next(x for x in m["joints"] if x["name"] == "walker_knee_r")
    assert (knee["parent"], knee["child"]) == ("femur_r", "tibia_r")
    femur = next(x for x in m["bodies"] if x["name"] == "femur_r")
    assert femur["geometry"] == ["r_femur.vtp"]
    assert m["trial"]["frames"] == 238 and m["trial"]["timeStart"] == 0.0


def test_kinematics_and_grf_share_time_base(out: Outputs) -> None:
    assert out.kin.time == out.grf.time == out.act.time
    names = [c["name"] for c in out.model["coordinates"]]
    assert out.kin.labels == ["time", *names, *[n + SPEED_SUFFIX for n in names]]
    # Knee flexion in walking spans roughly 0–70 degrees.
    knee = out.kin.columns["knee_angle_r"]
    assert 0.9 < max(knee) < 1.4 and min(knee) < 0.2


def test_activations_cover_all_muscles_in_range(out: Outputs) -> None:
    assert out.act.labels == ["time", *muscles(out)]
    for m in muscles(out):
        assert all(-1e-6 <= a <= 1.0 + 1e-6 for a in out.act.columns[m]), m


def test_reserves_stay_small(out: Outputs) -> None:
    """Muscles supply the lower-limb joint moments; each reserve stays below 5 N·m."""
    reserves = [a for a in out.settings["actuators"] if a["kind"] == "reserve"]
    assert len(reserves) == 10
    for a in reserves:
        assert a["peakAbsForce"] < 5.0, a


def test_knee_extensors_have_negative_moment_arm_about_knee_flexion(out: Outputs) -> None:
    """`knee_angle_r` is flexion-positive; extensors pull it the negative way."""
    for m in KNEE_EXTENSORS:
        r = out.arms[(m, "knee_angle_r")]
        assert len(r) == 238 and max(r) < -0.01, m
    assert min(out.arms[("bfsh_r", "knee_angle_r")]) > 0.01  # a knee flexor


def test_velocity_matches_moment_arms_times_speeds(out: Outputs) -> None:
    """dL/dt = −Σ r·q̇ (r = −∂L/∂q): the length velocity agrees with the moment arms."""
    t = out.kin.time
    for m in ("vasint_r", "recfem_r", "soleus_r", "glmed1_r", "semimem_r"):
        coords = [c for (mm, c) in out.arms if mm == m]
        predicted = [-sum(out.arms[(m, c)][i] * out.kin.columns[c + SPEED_SUFFIX][i] for c in coords) for i in range(len(t))]
        v = out.velocity[m]
        inner = range(2, len(t) - 2)
        err = max(abs(v[i] - predicted[i]) for i in inner)
        scale = max(abs(v[i]) for i in inner)
        assert err < 0.05 * scale, (m, err, scale)


def test_tibialis_anterior_active_after_right_initial_contact(out: Outputs) -> None:
    t = out.act.time
    ta = out.act.columns["tibant_r"]
    stances = complete(out.contacts("r"), t[0], t[-1])
    assert len(stances) == 2
    for stance in stances:
        early = mean_over(t, ta, [fraction(stance, *EARLY_STANCE)])
        mid = mean_over(t, ta, [fraction(stance, *MID_STANCE)])
        print(f"tibant_r stance {stance}: early {early:.3f}, mid {mid:.3f}")
        assert early > TIBANT_FLOOR
        assert early > mid


def test_gluteus_medius_active_in_right_single_leg_stance(out: Outputs) -> None:
    t = out.act.time
    right = out.contacts("r")
    left = out.contacts("l")
    stride = right[1][0] - right[0][0]
    single = subtract(right, periodic(left, stride))
    swing = gaps(right)
    assert len(single) == 2 and len(swing) == 1
    parts = []
    for m in GLMED:
        stance_mean = mean_over(t, out.act.columns[m], single)
        swing_mean = mean_over(t, out.act.columns[m], swing)
        print(f"{m}: single-leg stance {single} {stance_mean:.3f}, swing {swing} {swing_mean:.3f}")
        assert stance_mean > swing_mean, m
        parts.append(stance_mean)
    assert sum(parts) / len(parts) > GLMED_FLOOR
