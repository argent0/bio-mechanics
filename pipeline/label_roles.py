"""Stage `labelRoles`: each muscle's role per gait phase and joint action (decisions D-002, D-006).

Scope. One complete stride of the right leg (stride 0 of `phases.csv`), its seven phases, the
joint coordinates of `Config.coordinates`, and the muscles of both sides
(`Config.muscle_suffixes`, `labelled_muscles`) that cross one of those coordinates. A
coordinate takes the muscles of its own leg (`muscles_of`): those whose name ends in the
coordinate's suffix, e.g. `vaslat_l` for `knee_angle_l`. A phase spans
the frames from the event that opens it to the event that closes it, both included, so the
phases tile the stride; integrals use the trapezoid rule over those frames.

One timeline for both legs (decision D-007). The right leg is the reference leg: its initial
contacts bound the stride and its seven events bound the phases, and every muscle of either leg
takes its roles per phase of this one timeline. The left leg's own phases read off it about half
a stride later, at the left leg's events, which `phases.csv` carries as the opposite events:
  - left initial contact = `oppositeInitialContact`, which opens the reference pre-swing; so the
    reference pre-swing holds the left loading response (left initial contact to right toe-off);
  - left toe-off = `oppositeToeOff`, which opens the reference mid-stance; the reference
    loading response holds the left pre-swing, and the reference mid-stance and terminal
    stance hold the left swing;
  - right toe-off to right initial contact (the reference initial, mid- and terminal swing)
    holds the left single-leg stance (left mid-stance and terminal stance).
Stage `segmentPhases` takes each left event from the force plates when the left foot meets or
leaves a plate, and from the markers otherwise (Zeni et al. 2008: heel and toe marker extrema
relative to the pelvis). In this trial the left foot stands on a force plate once, from 0.84 s
to 1.58 s (vertical force above `load_model.CONTACT_THRESHOLD_N`): the left initial contact at
0.84 s and the left toe-off at 1.59 s come from the plate, and the left toe-off at 0.45 s and
the left initial contact at 1.97 s, outside the plate contact, come from the markers. Each
event's `source` in `phases.csv` and `roles.json` `events` records which
(`pipeline/tests/test_l_stages.py` pins these four).

Joint action of a coordinate in a phase (`choose_action`). The coordinate's change over the
phase is Δq = q(end) − q(start).
  - |Δq| ≥ `stabiliser_max_change_deg`: the coordinate moves; the action is the direction it
    moves, `direction` = sign(Δq) (+1: the coordinate's positive direction, e.g. knee flexion).
  - |Δq| < `stabiliser_max_change_deg`: the coordinate is *stabilised*; the action is the
    direction of the muscles' net moment over the phase (the direction the muscles hold the
    joint against the load), `direction` = sign(∫ Σ moment dt), +1 when the net moment is zero.
Sign conventions of the coordinates are OpenSim's (P1, `moment_arms`): positive hip flexion,
hip adduction, hip internal rotation, knee flexion, ankle dorsiflexion.

Moments. A muscle's moment at a frame is a·F·r (D-002): activation a (`activations.csv`), max
isometric force F (`model.json`), moment arm r about the coordinate (`moment_arms.csv`; r > 0
turns the coordinate in its positive direction). With s = `direction`, a frame counts toward
the action when s·r ≥ `moment_arm_min_m` (the muscle is an agonist there) and against it when
−s·r ≥ `moment_arm_min_m` (opposing). Per muscle i over the phase:
  A_i = ∫ a·F·s·r dt over its agonist frames,  O_i = ∫ a·F·(−s·r) dt over its opposing frames;
A = Σ A_i and O = Σ O_i over the muscles.

Roles (`classify`), the first rule that holds:
  1. stabiliser: the coordinate is stabilised, the muscle's mean activation over the phase is
     ≥ `stabiliser_min_activation`, and |r| ≥ `moment_arm_min_m` at some frame of the phase;
  2. main mover: A_i ≥ O_i and A_i / A ≥ `main_mover_min_share`;
  3. helper: A_i ≥ O_i and A_i / A ≥ `helper_min_share`;
  4. antagonist: O_i > A_i and O_i / O ≥ `antagonist_min_share`;
rules 2–4 also need the muscle to be active in the phase (`active`, decision D-006, which
replaces D-004 and D-005): its mean activation over the phase ā satisfies
  ā ≥ `role_min_activation` and (ā ≥ `role_clear_activation` or ā ≥ `role_min_peak_fraction` × P),
P being the muscle's own peak activation over the stride: the largest activation between the
stride's two right initial contacts, both included (for the left leg's muscles too, D-007). The first clause drops near-silent muscles
whose small peak would let them pass the relative clause; the relative clause keeps muscles that
work hard for their own size (e.g. the vasti braking in loading response); the clear clause
keeps muscles with a large push-off peak active in earlier phases (e.g. the calf in mid-stance).
An inactive muscle has no role in the action during the phase. Otherwise the muscle has no
role in the action during the phase and roles.json omits it (and the graph has no `drivenBy`
edge for it). The totals A and O sum over every muscle crossing the coordinate, inactive ones
included: the floor decides who earns a role, and the shares stay the D-002 moment shares.
`share` in roles.json is A_i / A for movers and helpers, O_i / O for antagonists, and the
larger of the two for stabilisers.

Contraction (`contraction`): the activation-weighted mean muscle-tendon velocity over the phase,
v̄ = ∫ a·v dt / ∫ a dt (`mt_lengths.csv`; the plain mean when the muscle is silent).
|v̄| < `isometric_max_velocity`: isometric; v̄ < 0: concentric (shortening); v̄ > 0: eccentric
(lengthening under load, braking).

Curves. `activation` and `momentArm` are sampled at `samples_per_phase` evenly spaced times from
the phase start to its end (linear interpolation between frames); `peakActivation` is the
largest activation over the phase's frames. `crosses` lists, for every labelled muscle and
coordinate of its leg with |r| ≥ `moment_arm_min_m` somewhere in the stride, the moment arm sampled at
`samples_per_stride` evenly spaced times over the stride.

Output `roles.json`:
  config    the thresholds and settings of `roles.yaml`, as read
  stride    {index, start, end} in s
  events    [{event, time, source}] of the stride, closing initial contact included
  phases    [{phase, order, start, end, startPct, endPct, actions}], in stride order; each
            action {coordinate, direction, changeDeg, stabilised, agonistMoment,
            opposingMoment (N·m·s), muscles}; each muscle {muscle, role, contraction, share,
            meanActivation, peakActivation (over the phase), stridePeakActivation,
            meanVelocity (m/s), activation, momentArm (m)}
  crosses   [{muscle, coordinate, momentArm}]
  muscles   {name: {maxIsometricForce}} for the labelled muscles of both legs

Run from the repository root: `python -m pipeline.label_roles` (pure Python; any interpreter
with PyYAML).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from pipeline.load_model import REPO, Table, interp_linear, read_csv
from pipeline.segment_phases import GENERATED, Phases, read_phases

import pipeline_paths as paths  # noqa: E402  (generated/py: see `GENERATED`)

Role = Literal["mainMover", "helper", "stabiliser", "antagonist"]
Contraction = Literal["concentric", "eccentric", "isometric"]


@dataclass(frozen=True)
class Config:
    """The contents of `pipeline/config/roles.yaml` (keys in camelCase there)."""

    moment_arm_min_m: float
    main_mover_min_share: float
    helper_min_share: float
    antagonist_min_share: float
    role_min_activation: float
    role_clear_activation: float
    role_min_peak_fraction: float
    stabiliser_min_activation: float
    stabiliser_max_change_deg: float
    isometric_max_velocity: float
    samples_per_phase: int
    samples_per_stride: int
    muscle_suffixes: tuple[str, ...]
    coordinates: tuple[str, ...]

    @staticmethod
    def keys() -> dict[str, str]:
        """roles.yaml key -> field name."""
        out = {}
        for name in Config.__dataclass_fields__:
            head, *rest = name.split("_")
            key = head + "".join(w.upper() if w == "m" else w.capitalize() for w in rest)
            out[key] = name
        return out

    @staticmethod
    def from_yaml(data: dict[str, Any]) -> Config:
        keys = Config.keys()
        missing = sorted(set(keys) - set(data))
        unknown = sorted(set(data) - set(keys))
        if missing or unknown:
            raise ValueError(f"roles.yaml: missing {missing}, unknown {unknown}")
        v = {keys[k]: data[k] for k in keys}
        v["coordinates"] = tuple(v["coordinates"])
        v["muscle_suffixes"] = tuple(v["muscle_suffixes"])
        return Config(**v)

    def as_json(self) -> dict[str, Any]:
        names = {f: k for k, f in Config.keys().items()}
        return {names[f]: (list(x) if isinstance(x, tuple) else x) for f, x in asdict(self).items()}


def load_config(path: Path) -> Config:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping")
    return Config.from_yaml(data)


def labelled_muscles(names: Sequence[str], cfg: Config) -> list[str]:
    """The muscles of `names` whose name ends in one of `cfg.muscle_suffixes`, in their order."""
    return [m for m in names if m.endswith(cfg.muscle_suffixes)]


def muscles_of(coordinate: str, muscles: Sequence[str], cfg: Config) -> list[str]:
    """The muscles of `muscles` that count for `coordinate`: those of the coordinate's own leg
    (the muscle suffix the coordinate's name ends in), every one of them for a coordinate
    without a leg suffix."""
    side = next((s for s in cfg.muscle_suffixes if coordinate.endswith(s)), None)
    return [m for m in muscles if side is None or m.endswith(side)]


# ---------------------------------------------------------------------------------------------
# Pure numerics.


def trapezoid(t: Sequence[float], x: Sequence[float]) -> float:
    return sum(0.5 * (x[i] + x[i + 1]) * (t[i + 1] - t[i]) for i in range(len(t) - 1))


def sample(t: Sequence[float], x: Sequence[float], t0: float, t1: float, n: int) -> list[float]:
    """`x(t)` at `n` evenly spaced times from `t0` to `t1`, both included."""
    ts = [t0 + (t1 - t0) * k / (n - 1) for k in range(n)]
    return interp_linear(t, x, ts)


@dataclass
class MuscleInPhase:
    """One muscle's signals over one phase's frames."""

    activation: list[float]
    moment_arm: list[float]
    velocity: list[float]
    max_force: float
    stride_peak: float
    """The muscle's peak activation over the stride (D-005)."""


@dataclass
class Shares:
    agonist: float
    opposing: float


def moment_integrals(t: Sequence[float], m: MuscleInPhase, direction: int, r_min: float) -> Shares:
    """A_i and O_i of the module docstring."""
    ag = [a * m.max_force * direction * r if direction * r >= r_min else 0.0 for a, r in zip(m.activation, m.moment_arm)]
    op = [a * m.max_force * -direction * r if -direction * r >= r_min else 0.0 for a, r in zip(m.activation, m.moment_arm)]
    return Shares(trapezoid(t, ag), trapezoid(t, op))


def net_moment(t: Sequence[float], muscles: Sequence[MuscleInPhase]) -> float:
    return sum(trapezoid(t, [a * m.max_force * r for a, r in zip(m.activation, m.moment_arm)]) for m in muscles)


def choose_action(change_deg: float, net: float, cfg: Config) -> tuple[int, bool]:
    """(direction, stabilised) of a coordinate over a phase."""
    if abs(change_deg) >= cfg.stabiliser_max_change_deg:
        return (1 if change_deg > 0 else -1), False
    return (-1 if net < 0 else 1), True


def active(mean_act: float, stride_peak: float, cfg: Config) -> bool:
    """D-006: a muscle with phase-mean activation `mean_act` and stride peak `stride_peak` is
    active enough to move or oppose an action."""
    return mean_act >= cfg.role_min_activation and (
        mean_act >= cfg.role_clear_activation or mean_act >= cfg.role_min_peak_fraction * stride_peak
    )


def classify(t: Sequence[float], m: MuscleInPhase, s: Shares, total: Shares, stabilised: bool, cfg: Config) -> tuple[Role, float] | None:
    """The muscle's role and share, or `None` (rules of the module docstring)."""
    ag = s.agonist / total.agonist if total.agonist > 0 else 0.0
    op = s.opposing / total.opposing if total.opposing > 0 else 0.0
    mean_act = trapezoid(t, m.activation) / (t[-1] - t[0])
    if stabilised and mean_act >= cfg.stabiliser_min_activation and max(abs(r) for r in m.moment_arm) >= cfg.moment_arm_min_m:
        return "stabiliser", max(ag, op)
    if not active(mean_act, m.stride_peak, cfg):
        return None
    if s.agonist >= s.opposing and s.agonist > 0:
        if ag >= cfg.main_mover_min_share:
            return "mainMover", ag
        if ag >= cfg.helper_min_share:
            return "helper", ag
        return None
    if s.opposing > 0 and op >= cfg.antagonist_min_share:
        return "antagonist", op
    return None


def mean_velocity(t: Sequence[float], m: MuscleInPhase) -> float:
    w = trapezoid(t, m.activation)
    if w > 0:
        return trapezoid(t, [a * v for a, v in zip(m.activation, m.velocity)]) / w
    return trapezoid(t, m.velocity) / (t[-1] - t[0])


def contraction(v_mean: float, cfg: Config) -> Contraction:
    if abs(v_mean) < cfg.isometric_max_velocity:
        return "isometric"
    return "concentric" if v_mean < 0 else "eccentric"


# ---------------------------------------------------------------------------------------------
# Inputs.


@dataclass
class Trial:
    """The stage's inputs on the kinematics time base."""

    time: list[float]
    coordinates: dict[str, list[float]]
    activation: dict[str, list[float]]
    moment_arm: dict[tuple[str, str], list[float]]
    velocity: dict[str, list[float]]
    max_force: dict[str, float]


def read_long(path: Path, key_cols: Sequence[str], value_col: str, time: Sequence[float]) -> dict[tuple[str, ...], list[float]]:
    """A long-format CSV (`time`, keys..., values) as one series per key on the frames of `time`."""
    frame = {round(t, 6): i for i, t in enumerate(time)}
    out: dict[tuple[str, ...], list[float]] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            key = tuple(row[c] for c in key_cols)
            series = out.setdefault(key, [math.nan] * len(time))
            series[frame[round(float(row["time"]), 6)]] = float(row[value_col])
    for key, series in out.items():
        if any(math.isnan(v) for v in series):
            raise ValueError(f"{path}: frames missing for {key}")
    return out


def read_trial(act: Path, arms: Path, lengths: Path, kin_path: Path, model: Path) -> Trial:
    kin: Table = read_csv(kin_path)
    activ = read_csv(act)
    if activ.time != kin.time:
        raise ValueError("activations.csv and kinematics.csv must share one time base")
    arm = read_long(arms, ("muscle", "coordinate"), "moment_arm", kin.time)
    vel = read_long(lengths, ("muscle",), "velocity", kin.time)
    summary = json.loads(model.read_text())
    return Trial(
        time=kin.time,
        coordinates={c: kin.columns[c] for c in kin.labels[1:]},
        activation={m: activ.columns[m] for m in activ.labels[1:]},
        moment_arm={(k[0], k[1]): v for k, v in arm.items()},
        velocity={k[0]: v for k, v in vel.items()},
        max_force={m["name"]: float(m["maxIsometricForce"]) for m in summary["muscles"]},
    )


# ---------------------------------------------------------------------------------------------
# The stage.


def phase_bounds(p: Phases, stride: int) -> list[tuple[str, int, int]]:
    """(phase, first frame, last frame) of each phase of `stride`; the last frame is the first
    frame of the next phase, so neighbouring phases share their boundary frame."""
    frames = [i for i, s in enumerate(p.stride) if s == stride]
    if not frames or p.stride_pct[frames[0]] is None:
        raise ValueError(f"stride {stride} is incomplete")
    out: list[tuple[str, int, int]] = []
    start = frames[0]
    for i in frames[1:] + [frames[-1] + 1]:
        if i == frames[-1] + 1 or p.phase[i] != p.phase[start]:
            phase = p.phase[start]
            assert phase is not None
            out.append((phase, start, i))
            start = i
    return out


def r6(x: float, digits: int) -> float:
    return round(x, digits)


def label(trial: Trial, p: Phases, cfg: Config, stride: int = 0) -> dict[str, Any]:
    """The contents of `roles.json`."""
    t_all = trial.time
    muscles = [m for m in labelled_muscles(list(trial.activation), cfg) if any((m, c) in trial.moment_arm for c in cfg.coordinates)]
    bounds = phase_bounds(p, stride)
    s0, s1 = t_all[bounds[0][1]], t_all[bounds[-1][2]]
    stride_peak = {m: max(trial.activation[m][bounds[0][1] : bounds[-1][2] + 1]) for m in muscles}
    phases_out: list[dict[str, Any]] = []
    for order, (phase, f0, f1) in enumerate(bounds):
        t = t_all[f0 : f1 + 1]
        actions = []
        for coord in cfg.coordinates:
            q = trial.coordinates[coord]
            change = math.degrees(q[f1] - q[f0])
            crossing = {
                m: MuscleInPhase(
                    trial.activation[m][f0 : f1 + 1],
                    trial.moment_arm[(m, coord)][f0 : f1 + 1],
                    trial.velocity[m][f0 : f1 + 1],
                    trial.max_force[m],
                    stride_peak[m],
                )
                for m in muscles_of(coord, muscles, cfg)
                if (m, coord) in trial.moment_arm
            }
            direction, stabilised = choose_action(change, net_moment(t, list(crossing.values())), cfg)
            shares = {m: moment_integrals(t, x, direction, cfg.moment_arm_min_m) for m, x in crossing.items()}
            total = Shares(sum(s.agonist for s in shares.values()), sum(s.opposing for s in shares.values()))
            rows: list[dict[str, Any]] = []
            for m, x in crossing.items():
                got = classify(t, x, shares[m], total, stabilised, cfg)
                if got is None:
                    continue
                role, share = got
                v = mean_velocity(t, x)
                rows.append(
                    {
                        "muscle": m,
                        "role": role,
                        "contraction": contraction(v, cfg),
                        "share": r6(share, 4),
                        "meanActivation": r6(trapezoid(t, x.activation) / (t[-1] - t[0]), 4),
                        "peakActivation": r6(max(x.activation), 4),
                        "stridePeakActivation": r6(x.stride_peak, 4),
                        "meanVelocity": r6(v, 4),
                        "activation": [r6(a, 4) for a in sample(t, x.activation, t[0], t[-1], cfg.samples_per_phase)],
                        "momentArm": [r6(r, 5) for r in sample(t, x.moment_arm, t[0], t[-1], cfg.samples_per_phase)],
                    }
                )
            rows.sort(key=lambda r: (-r["share"], r["muscle"]))
            actions.append(
                {
                    "coordinate": coord,
                    "direction": direction,
                    "changeDeg": r6(change, 3),
                    "stabilised": stabilised,
                    "agonistMoment": r6(total.agonist, 3),
                    "opposingMoment": r6(total.opposing, 3),
                    "muscles": rows,
                }
            )
        phases_out.append(
            {
                "phase": phase,
                "order": order,
                "start": t_all[f0],
                "end": t_all[f1],
                "startPct": r6(100.0 * (t_all[f0] - s0) / (s1 - s0), 3),
                "endPct": r6(100.0 * (t_all[f1] - s0) / (s1 - s0), 3),
                "actions": actions,
            }
        )
    crosses = []
    fs0, fs1 = bounds[0][1], bounds[-1][2]
    for m in muscles:
        for coord in cfg.coordinates:
            if m not in muscles_of(coord, [m], cfg):
                continue
            r = trial.moment_arm.get((m, coord))
            if r is None or max(abs(x) for x in r[fs0 : fs1 + 1]) < cfg.moment_arm_min_m:
                continue
            curve = sample(t_all[fs0 : fs1 + 1], r[fs0 : fs1 + 1], s0, s1, cfg.samples_per_stride)
            crosses.append({"muscle": m, "coordinate": coord, "momentArm": [r6(x, 5) for x in curve]})
    events = [
        {"event": e.event, "time": p.event_time(e), "source": e.source}
        for e in p.events
        if fs0 <= e.frame <= fs1
    ]
    return {
        "config": cfg.as_json(),
        "stride": {"index": stride, "start": s0, "end": s1},
        "events": events,
        "phases": phases_out,
        "crosses": crosses,
        "muscles": {m: {"maxIsometricForce": trial.max_force[m]} for m in muscles},
    }


def main(argv: Sequence[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="python -m pipeline.label_roles", description=doc.split("\n")[0])
    ap.add_argument("--activations", type=Path, default=REPO / paths.ACTIVATIONS)
    ap.add_argument("--moment-arms", type=Path, default=REPO / paths.MOMENT_ARMS)
    ap.add_argument("--mt-lengths", type=Path, default=REPO / paths.MT_LENGTHS)
    ap.add_argument("--phases", type=Path, default=REPO / paths.PHASES)
    ap.add_argument("--kinematics", type=Path, default=REPO / paths.KINEMATICS)
    ap.add_argument("--config", type=Path, default=REPO / paths.ROLE_THRESHOLDS)
    ap.add_argument("--model", type=Path, default=REPO / paths.MODEL, help="model.json (max isometric forces)")
    ap.add_argument("--out", type=Path, default=REPO / paths.ROLES)
    a = ap.parse_args(argv)
    trial = read_trial(a.activations, a.moment_arms, a.mt_lengths, a.kinematics, a.model)
    roles = label(trial, read_phases(a.phases), load_config(a.config))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(roles, indent=1) + "\n")
    n = sum(len(x["muscles"]) for ph in roles["phases"] for x in ph["actions"])
    print(f"label_roles: {n} muscle roles over {len(roles['phases'])} phases; wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
