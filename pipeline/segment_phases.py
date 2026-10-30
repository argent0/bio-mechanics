"""Stage `segmentPhases`: the gait events of the right leg, and a gait phase for every frame.

The right leg is the reference leg; "opposite" names the left leg. The seven events bound the
seven phases of the generated gait DFA (`generated/py/gait_fsm.py`, from
`spec/BioMech/GaitFsm.lean`). Every event is detected at a frame of `kinematics.csv` (100 Hz);
the frame of an event is the first frame of the phase it opens.

Signals. The scaled model (`pipeline_paths.SCALED_MODEL`) is posed at every frame of the filtered
coordinates (`kinematics.csv`), and OpenSim reports in ground the positions of the model's foot
and leg markers (`MARKERS`: heel, toe, ankle, knee) and of the pelvis origin. Positions are
projected on the walking direction: the horizontal unit vector of the pelvis displacement from
the first to the last frame. Ground reaction forces come from `grf.csv`.

Events, per leg (side `r` or `l`):
  - Initial contact (`detect_contacts`). Kinematic: each maximum of the heel marker's position
    ahead of the pelvis (`local_extrema`; Zeni, Richards & Higginson 2008, Gait & Posture
    27:710). Force: the first frame with vertical GRF above `CONTACT_THRESHOLD_N` (P1's
    `contact_intervals`).
  - Toe-off. Kinematic: each minimum of the toe marker's position ahead of the pelvis (Zeni et
    al. 2008). Force: the first frame after a contact interval.
  A force event within `GRF_MATCH_S` of a kinematic event of the same kind replaces it: the force
  plates give the contact instant directly. A kinematic event with no force event nearby stays;
  in this trial the left foot is off the force plates before about 0.40 s and after about 1.98 s,
  so its toe-off before the first plate contact comes from kinematics. A force event with no
  kinematic event nearby is dropped (e.g. a foot stepping onto a plate's edge mid-stance).
  Where both exist in this trial, the marker events precede the force events by 0–30 ms (the
  stage prints both); the force event is the measured contact.
Events of the right leg only:
  - Heel-off (`detect_heel_off`): the first frame after opposite toe-off at which the right heel
    marker stands `HEEL_RISE_M` above its height at opposite toe-off (the foot is flat then).
  - Feet adjacent (`detect_crossing`): the first frame after right toe-off at which the right
    ankle marker passes the left ankle marker along the walking direction.
  - Tibia vertical (`detect_crossing`): the first frame after feet adjacent at which the right
    ankle marker passes the right knee marker along the walking direction (the shank, seen from
    the side, turns from pointing back to pointing forward).
Opposite initial contact and opposite toe-off are the left leg's contact events.

Phases (`label_frames`). The gait DFA starts in `START` (loading response) at the first right
initial contact (decision D-001: initial contact is an instant) and reads the events that
follow in time order, one `step` each; a frame's phase is the state after every event up to and
including that frame. Frames before the first right initial contact lie outside every stride.
An event out of order drives the DFA to `invalid`, and the stage raises `PhaseError`.
Stride k runs from the k-th right initial contact to the next; a stride is complete when both
contacts lie inside the trial.

Output `phases.csv` (`PHASES_COLUMNS`), one row per frame of `kinematics.csv`:
  time          s
  phase         a `GaitPhase` constructor, e.g. `loadingResponse`; empty outside every stride
  stride        stride index from 0; empty outside every stride
  stride_pct    percent of a complete stride, 0 at its initial contact; empty elsewhere
  event         the `GaitEvent` opening the frame's phase, on the event's frame; empty elsewhere
  event_source  `grf` or `kinematics`: the signal the event came from; empty with no event

Module path. The stages of workstream P2 import generated modules (`pipeline_paths`,
`gait_fsm`, `schema`) from `generated/py`; this module puts that directory on `sys.path`
(`GENERATED`), and the other P2 stage modules import this one first.

Run with the OpenSim environment's Python from the repository root:
`python -m pipeline.segment_phases`. The detectors and `label_frames` are pure.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pipeline.load_model import CONTACT_THRESHOLD_N, REPO, Table, contact_intervals, opensim_module, read_csv

GENERATED = REPO / "generated" / "py"
"""Generated Python modules (`lake exe gen`), put on `sys.path` for `python -m` runs."""
if str(GENERATED) not in sys.path:
    sys.path.insert(0, str(GENERATED))

import gait_fsm  # noqa: E402
import pipeline_paths as paths  # noqa: E402
from gait_fsm import GaitEvent, GaitPhase  # noqa: E402

HEEL_RISE_M = 0.01
"""Heel-off: rise of the heel marker above its flat-foot height (m). One centimetre stands
clear of the slow drift of the heel marker during foot-flat (about 5 mm over mid-stance in this
trial) and marks the start of the fast rise of push-off."""

GRF_MATCH_S = 0.05
"""A force-plate contact event replaces a kinematic one of the same kind within this time (s)."""

MARKERS: dict[str, str] = {
    "heel_r": "R.Heel",
    "toe_r": "R.Toe",
    "ankle_r": "R.Ankle",
    "knee_r": "R.Knee",
    "heel_l": "L.Heel",
    "toe_l": "L.Toe",
    "ankle_l": "L.Ankle",
}
"""Signal name -> marker of the scaled model (lateral malleolus for the ankle, lateral femoral
epicondyle for the knee)."""

PHASES_COLUMNS = ("time", "phase", "stride", "stride_pct", "event", "event_source")

Source = Literal["grf", "kinematics"]
Vec3 = tuple[float, float, float]


class PhaseError(ValueError):
    """The detected events do not follow the gait DFA."""


@dataclass(frozen=True)
class Event:
    """A gait event at a frame."""

    event: GaitEvent
    frame: int
    source: Source


# ---------------------------------------------------------------------------------------------
# Pure detectors.


def local_extrema(x: Sequence[float], kind: Literal["max", "min"]) -> list[int]:
    """Frames where `x` peaks (`max`) or dips (`min`): one per excursion beyond the signal's
    midline (halfway between its extremes), at the excursion's extreme frame, so each gait
    cycle gives one event and ripples none. An excursion whose extreme lies on the first or
    last frame continues outside the data and gives no event."""
    n = len(x)
    if n < 3:
        return []
    sign = 1.0 if kind == "max" else -1.0
    y = [sign * v for v in x]
    mid = 0.5 * (max(y) + min(y))
    out: list[int] = []
    i = 0
    while i < n:
        if y[i] <= mid:
            i += 1
            continue
        j = i
        while j + 1 < n and y[j + 1] > mid:
            j += 1
        best = max(range(i, j + 1), key=lambda k: (y[k], -k))
        if 0 < best < n - 1:
            out.append(best)
        i = j + 1
    return out


def grf_contacts(t: Sequence[float], fy: Sequence[float], threshold: float = CONTACT_THRESHOLD_N) -> tuple[list[int], list[int]]:
    """Frames of initial contact (first frame above `threshold`) and toe-off (first frame after
    a contact) from the vertical GRF `fy`. A contact already under way at the first frame has no
    initial contact; one still under way at the last frame has no toe-off."""
    index = {ti: i for i, ti in enumerate(t)}
    ics: list[int] = []
    tos: list[int] = []
    for on, off in contact_intervals(t, fy, threshold):
        i_on, i_off = index[on], index[off]
        if i_on > 0:
            ics.append(i_on)
        if i_off < len(t) - 1:
            tos.append(i_off + 1)
    return ics, tos


def merge_events(kinematic: Sequence[int], force: Sequence[int], t: Sequence[float], match_s: float = GRF_MATCH_S) -> list[tuple[int, Source]]:
    """One frame per kinematic event: the nearest force event within `match_s`, else the
    kinematic frame itself."""
    out: list[tuple[int, Source]] = []
    for k in kinematic:
        near = [f for f in force if abs(t[f] - t[k]) <= match_s]
        if near:
            out.append((min(near, key=lambda f: abs(t[f] - t[k])), "grf"))
        else:
            out.append((k, "kinematics"))
    return out


def detect_contacts(
    t: Sequence[float], heel_ahead: Sequence[float], toe_ahead: Sequence[float], fy: Sequence[float]
) -> tuple[list[tuple[int, Source]], list[tuple[int, Source]]]:
    """Initial contacts and toe-offs of one leg: kinematic events (`heel_ahead`, `toe_ahead`:
    marker position ahead of the pelvis, m), replaced by force events where the plates saw them."""
    f_ic, f_to = grf_contacts(t, fy)
    return (
        merge_events(local_extrema(heel_ahead, "max"), f_ic, t),
        merge_events(local_extrema(toe_ahead, "min"), f_to, t),
    )


def detect_heel_off(heel_height: Sequence[float], flat_frames: Sequence[int], rise: float = HEEL_RISE_M) -> list[int]:
    """For each flat-foot frame (opposite toe-off), the first later frame at which the heel
    stands `rise` above its height at that frame."""
    out: list[int] = []
    for f0 in flat_frames:
        ref = heel_height[f0] + rise
        hit = next((f for f in range(f0 + 1, len(heel_height)) if heel_height[f] >= ref), None)
        if hit is not None:
            out.append(hit)
    return out


def detect_crossing(d: Sequence[float], after: Sequence[int]) -> list[int]:
    """For each frame in `after`, the first later frame at which `d` turns from negative to
    zero or positive."""
    out: list[int] = []
    for f0 in after:
        hit = next((f for f in range(f0 + 1, len(d)) if d[f - 1] < 0.0 <= d[f]), None)
        if hit is not None:
            out.append(hit)
    return out


def label_frames(n: int, events: Sequence[Event]) -> list[GaitPhase | None]:
    """The gait phase of each of `n` frames: the DFA starts at the first `initialContact` and
    reads the later events in frame order; frames before it get `None`. Raises `PhaseError`
    when the DFA reaches `invalid`."""
    ordered = sorted(events, key=lambda e: e.frame)
    first = next((i for i, e in enumerate(ordered) if e.event == "initialContact"), None)
    labels: list[GaitPhase | None] = [None] * n
    if first is None:
        return labels
    state: GaitPhase = gait_fsm.START
    k = first + 1
    for f in range(ordered[first].frame, n):
        while k < len(ordered) and ordered[k].frame <= f:
            nxt = gait_fsm.step(state, ordered[k].event)
            if nxt == "invalid":
                e = ordered[k]
                raise PhaseError(f"event {e.event} at frame {e.frame} ({e.source}) is out of order after {state}")
            state = nxt
            k += 1
        labels[f] = state
    return labels


def stride_columns(t: Sequence[float], labels: Sequence[GaitPhase | None], events: Sequence[Event]) -> tuple[list[int | None], list[float | None]]:
    """Stride index and percent of stride per frame (percent only inside complete strides)."""
    ics = sorted(e.frame for e in events if e.event == "initialContact")
    ics = [f for f in ics if labels[f] is not None]
    stride: list[int | None] = [None] * len(t)
    pct: list[float | None] = [None] * len(t)
    for k, f0 in enumerate(ics):
        f1 = ics[k + 1] if k + 1 < len(ics) else len(t)
        for f in range(f0, f1):
            stride[f] = k
            if k + 1 < len(ics):
                pct[f] = 100.0 * (t[f] - t[f0]) / (t[f1] - t[f0])
    return stride, pct


@dataclass
class Signals:
    """Marker and pelvis positions per frame in ground (m)."""

    pelvis: list[Vec3]
    markers: dict[str, list[Vec3]]


def walking_direction(pelvis: Sequence[Vec3]) -> Vec3:
    """Horizontal unit vector (y is up) of the pelvis displacement over the trial."""
    dx = pelvis[-1][0] - pelvis[0][0]
    dz = pelvis[-1][2] - pelvis[0][2]
    norm = math.hypot(dx, dz)
    return (dx / norm, 0.0, dz / norm)


def along(p: Sequence[Vec3], q: Sequence[Vec3], d: Vec3) -> list[float]:
    """(p − q) · d per frame."""
    return [(a[0] - b[0]) * d[0] + (a[1] - b[1]) * d[1] + (a[2] - b[2]) * d[2] for a, b in zip(p, q)]


def detect_events(t: Sequence[float], s: Signals, fy_r: Sequence[float], fy_l: Sequence[float]) -> list[Event]:
    """Every gait event of the trial, named from the right leg."""
    d = walking_direction(s.pelvis)
    m = s.markers
    ic_r, to_r = detect_contacts(t, along(m["heel_r"], s.pelvis, d), along(m["toe_r"], s.pelvis, d), fy_r)
    ic_l, to_l = detect_contacts(t, along(m["heel_l"], s.pelvis, d), along(m["toe_l"], s.pelvis, d), fy_l)
    events = [Event("initialContact", f, src) for f, src in ic_r]
    events += [Event("toeOff", f, src) for f, src in to_r]
    events += [Event("oppositeInitialContact", f, src) for f, src in ic_l]
    events += [Event("oppositeToeOff", f, src) for f, src in to_l]
    heel_height = [p[1] for p in m["heel_r"]]
    events += [Event("heelOff", f, "kinematics") for f in detect_heel_off(heel_height, [f for f, _ in to_l])]
    adjacent = detect_crossing(along(m["ankle_r"], m["ankle_l"], d), [f for f, _ in to_r])
    events += [Event("feetAdjacent", f, "kinematics") for f in adjacent]
    vertical = detect_crossing(along(m["ankle_r"], m["knee_r"], d), adjacent)
    events += [Event("tibiaVertical", f, "kinematics") for f in vertical]
    return sorted(events, key=lambda e: e.frame)


# ---------------------------------------------------------------------------------------------
# phases.csv.


@dataclass
class Phases:
    """The contents of `phases.csv`."""

    time: list[float]
    phase: list[GaitPhase | None]
    stride: list[int | None]
    stride_pct: list[float | None]
    events: list[Event]

    def event_time(self, e: Event) -> float:
        return self.time[e.frame]


def write_phases(path: Path, p: Phases) -> None:
    by_frame = {e.frame: e for e in p.events}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(PHASES_COLUMNS)
        for i, ti in enumerate(p.time):
            e = by_frame.get(i)
            pct = p.stride_pct[i]
            stride = p.stride[i]
            w.writerow(
                [
                    f"{ti:.10g}",
                    p.phase[i] or "",
                    "" if stride is None else str(stride),
                    "" if pct is None else f"{pct:.4f}",
                    e.event if e else "",
                    e.source if e else "",
                ]
            )


def read_phases(path: Path) -> Phases:
    """Read `phases.csv` (the format of this module's docstring)."""
    phases_by_name: dict[str, GaitPhase] = {p: p for p in gait_fsm.PHASES}
    events_by_name: dict[str, GaitEvent] = {e: e for e in gait_fsm.EVENTS}
    p = Phases([], [], [], [], [])
    with path.open(newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            p.time.append(float(row["time"]))
            p.phase.append(phases_by_name[row["phase"]] if row["phase"] else None)
            p.stride.append(int(row["stride"]) if row["stride"] else None)
            p.stride_pct.append(float(row["stride_pct"]) if row["stride_pct"] else None)
            if row["event"]:
                src: Source = "grf" if row["event_source"] == "grf" else "kinematics"
                p.events.append(Event(events_by_name[row["event"]], i, src))
    return p


def segment(t: Sequence[float], s: Signals, fy_r: Sequence[float], fy_l: Sequence[float]) -> Phases:
    """Events, phases and strides of a trial."""
    events = detect_events(t, s, fy_r, fy_l)
    labels = label_frames(len(t), events)
    first = next((i for i, lab in enumerate(labels) if lab is not None), len(t))
    used = [e for e in events if e.frame >= first]
    stride, pct = stride_columns(t, labels, used)
    return Phases(list(t), labels, stride, pct, used)


# ---------------------------------------------------------------------------------------------
# OpenSim signals.


def marker_signals(model_path: Path, kin: Table) -> Signals:
    """Pelvis origin and `MARKERS` in ground at every frame of `kin`."""
    from pipeline.moment_arms import pose

    osim = opensim_module()
    model = osim.Model(str(model_path))
    state = model.initSystem()
    ms = model.getMarkerSet()
    pelvis_body = model.getBodySet().get("pelvis")
    s = Signals([], {k: [] for k in MARKERS})

    def vec(v: Any) -> Vec3:
        return (float(v.get(0)), float(v.get(1)), float(v.get(2)))

    for f in range(len(kin.time)):
        pose(model, state, kin, f)
        s.pelvis.append(vec(pelvis_body.getPositionInGround(state)))
        for key, name in MARKERS.items():
            s.markers[key].append(vec(ms.get(name).getLocationInGround(state)))
    return s


def report(p: Phases, kinematic: Sequence[Event]) -> str:
    """Event times with their source, each force event's lead over its kinematic estimate, and
    the phase bounds of the first complete stride in percent."""
    lines: list[str] = []
    for e in p.events:
        line = f"  {e.event:<24} {p.event_time(e):6.2f} s  {e.source}"
        same = [k for k in kinematic if k.event == e.event]
        if e.source == "grf" and same:
            k = min(same, key=lambda k: abs(k.frame - e.frame))
            line += f"  (markers: {p.time[k.frame]:.2f} s)"
        lines.append(line)
    for ph in gait_fsm.PHASES:
        pcts = [pc for lab, st, pc in zip(p.phase, p.stride, p.stride_pct) if lab == ph and st == 0 and pc is not None]
        if pcts:
            lines.append(f"  {ph:<16} from {min(pcts):5.1f} % of stride 0")
    return "\n".join(lines)


def kinematic_only(t: Sequence[float], s: Signals) -> list[Event]:
    """Contact events from the markers alone, to compare with the force plates."""
    d = walking_direction(s.pelvis)
    m = s.markers
    out = [Event("initialContact", f, "kinematics") for f in local_extrema(along(m["heel_r"], s.pelvis, d), "max")]
    out += [Event("toeOff", f, "kinematics") for f in local_extrema(along(m["toe_r"], s.pelvis, d), "min")]
    out += [Event("oppositeInitialContact", f, "kinematics") for f in local_extrema(along(m["heel_l"], s.pelvis, d), "max")]
    out += [Event("oppositeToeOff", f, "kinematics") for f in local_extrema(along(m["toe_l"], s.pelvis, d), "min")]
    return out


def run(model_path: Path, kin_path: Path, grf_path: Path, out: Path) -> Phases:
    kin = read_csv(kin_path)
    grf = read_csv(grf_path)
    if kin.time != grf.time:
        raise ValueError("kinematics.csv and grf.csv must share one time base")
    s = marker_signals(model_path, kin)
    p = segment(kin.time, s, grf.columns["force_y_r"], grf.columns["force_y_l"])
    write_phases(out, p)
    print(report(p, kinematic_only(kin.time, s)))
    return p


def main(argv: Sequence[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="python -m pipeline.segment_phases", description=doc.split("\n")[0])
    ap.add_argument("--model", type=Path, default=REPO / paths.SCALED_MODEL, help="scaled OpenSim model (.osim)")
    ap.add_argument("--kinematics", type=Path, default=REPO / paths.KINEMATICS)
    ap.add_argument("--grf", type=Path, default=REPO / paths.GRF)
    ap.add_argument("--out", type=Path, default=REPO / paths.PHASES)
    a = ap.parse_args(argv)
    run(a.model, a.kinematics, a.grf, a.out)
    print(f"segment_phases: wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
