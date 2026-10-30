"""Stage `loadModel`: summarise the scaled model and put the walking trial on one time base.

Inputs (defaults under `data/raw/rajagopal/walk_pipeline/`, read-only):
  --model   Scale/subject_scaled_walk.osim        scaled Rajagopal model, 80 muscles, 39 coordinates
  --ik      IK/results_walk/ik_output_walk.mot     inverse-kinematics coordinates, 100 Hz
  --grf     ExpData/grf_walk.mot                   ground reaction forces, 2000 Hz
Outputs (defaults under `data/work/`):
  --out-model       model.json       bodies, joints, coordinates, muscles, trial; see `model_summary`
  --out-kinematics  kinematics.csv   `time`, then `<coordinate>` for every model coordinate in model
                                     order, then `<coordinate>_speed` in the same order
  --out-grf         grf.csv          `time`, then per foot (`_r`, `_l`) the columns of `GRF_COLUMNS`

Kinematics. Units are SI: rotational coordinates in rad, translational in m, speeds in rad/s or
m/s. The IK file stores rotational coordinates in degrees (`inDegrees=yes`); only coordinates of
motion type `Rotational` are converted, as OpenSim does (the coupled `knee_angle_*_beta` is
stored in radians already). Every coordinate is low-pass filtered with a zero-lag Butterworth
filter (`zero_lag_lowpass`: second-order section run forward then backward, i.e. 4th-order
zero-lag, cutoff 6 Hz per pass), the usual choice for walking kinematics and the cutoff of the
upstream Rajagopal external-loads setup. Speeds are central differences of the filtered values
(`central_difference`). Later stages (static optimisation, moment arms) all read these filtered
values, so every quantity derives from one kinematic signal.

Ground reaction forces. Ground frame, y vertical (up), x forward, z to the right; forces in N,
centre of pressure in m, free torque in N·m. Each column is resampled onto the kinematics times
by linear interpolation (`interp_linear`). The centre of pressure carries meaning only while the
foot's vertical force exceeds the contact threshold (`CONTACT_THRESHOLD_N`); the raw file holds
arbitrary values while the foot is off the plate. Contact detection: `contact_intervals`.

Run with the OpenSim environment's Python: `python -m pipeline.load_model`. The pure helpers in
this module (file readers, filter, differences, contact detection) use only the standard library,
so they also serve `static_opt` and `moment_arms` and run in any Python.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "data" / "raw" / "rajagopal" / "walk_pipeline"
WORK = REPO / "data" / "work"

DEFAULT_MODEL = RAW / "Scale" / "subject_scaled_walk.osim"
DEFAULT_IK = RAW / "IK" / "results_walk" / "ik_output_walk.mot"
DEFAULT_GRF = RAW / "ExpData" / "grf_walk.mot"

KINEMATICS_CUTOFF_HZ = 6.0
"""Low-pass cutoff of the coordinates, per filter pass (Hz)."""

CONTACT_THRESHOLD_N = 20.0
"""A foot is in contact while its vertical ground reaction force exceeds this value (N).
20 N sits well above the force-plate noise (exactly 0 N off the plate in this trial) and well
below body weight (≈ 835 N), so contact onset and offset come within one 2 ms GRF sample."""

SPEED_SUFFIX = "_speed"

# grf.csv column (per side suffix `_r` / `_l`) -> grf_walk.mot column (with `{s}` = r / l).
GRF_COLUMNS: dict[str, str] = {
    "force_x": "ground_force_{s}_vx",
    "force_y": "ground_force_{s}_vy",
    "force_z": "ground_force_{s}_vz",
    "cop_x": "ground_force_{s}_px",
    "cop_y": "ground_force_{s}_py",
    "cop_z": "ground_force_{s}_pz",
    "torque_x": "ground_torque_{s}_x",
    "torque_y": "ground_torque_{s}_y",
    "torque_z": "ground_torque_{s}_z",
}
VERTICAL_FORCE = "force_y"
SIDES = ("r", "l")

# OpenSim Coordinate::MotionType enum values.
MOTION_TYPES = {1: "rotational", 2: "translational", 3: "coupled"}


def opensim_module() -> Any:
    """The `opensim` package, imported on first use.

    opensim ships no type stubs and exists only in the conda env; `Any` keeps mypy strict clean,
    and the lazy import keeps this module importable (and its pure helpers testable) anywhere.
    """
    osim = importlib.import_module("opensim")
    osim.Logger.setLevelString("Warn")
    return osim


# ---------------------------------------------------------------------------------------------
# Tables: OpenSim .mot/.sto and CSV, as column-major dicts of floats.


@dataclass
class Table:
    """A time series: `labels[0]` is the time column; `columns[label]` holds its values."""

    labels: list[str]
    columns: dict[str, list[float]]
    header: dict[str, str]
    """Key=value lines of an OpenSim file header (e.g. `inDegrees`); empty for CSV."""

    @property
    def time(self) -> list[float]:
        return self.columns[self.labels[0]]


def read_sto(path: Path) -> Table:
    """Read an OpenSim `.mot`/`.sto` file: header lines up to `endheader`, then a tab-separated
    label row and numeric rows."""
    header: dict[str, str] = {}
    with path.open() as f:
        for line in f:
            text = line.strip()
            if text == "endheader":
                break
            if "=" in text:
                key, _, value = text.partition("=")
                header[key.strip()] = value.strip()
        labels = f.readline().split()
        rows = [[float(v) for v in line.split()] for line in f if line.strip()]
    columns = {label: [row[i] for row in rows] for i, label in enumerate(labels)}
    return Table(labels, columns, header)


def write_sto(path: Path, table: Table, name: str, in_degrees: bool) -> None:
    """Write `table` as an OpenSim `.mot` (version 1 header)."""
    n = len(table.time)
    with path.open("w") as f:
        f.write(f"{name}\nversion=1\nnRows={n}\nnColumns={len(table.labels)}\n")
        f.write(f"inDegrees={'yes' if in_degrees else 'no'}\nendheader\n")
        f.write("\t".join(table.labels) + "\n")
        for i in range(n):
            f.write("\t".join(f"{table.columns[c][i]:.10g}" for c in table.labels) + "\n")


def read_csv(path: Path) -> Table:
    """Read a CSV with a header row and numeric columns."""
    with path.open(newline="") as f:
        reader = csv.reader(f)
        labels = next(reader)
        rows = [[float(v) for v in row] for row in reader if row]
    columns = {label: [row[i] for row in rows] for i, label in enumerate(labels)}
    return Table(labels, columns, {})


def write_csv(path: Path, labels: Sequence[str], columns: dict[str, list[float]]) -> None:
    """Write numeric columns as CSV, `labels` giving the order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(columns[labels[0]])
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(labels)
        for i in range(n):
            w.writerow([f"{columns[c][i]:.10g}" for c in labels])


# ---------------------------------------------------------------------------------------------
# Pure numerics.


def butterworth2(cutoff_hz: float, rate_hz: float) -> tuple[list[float], list[float]]:
    """Second-order Butterworth low-pass as one biquad `(b, a)`, `a[0] == 1`, by the bilinear
    transform with frequency pre-warping (identical to `scipy.signal.butter(2, cutoff, fs=rate)`)."""
    k = math.tan(math.pi * cutoff_hz / rate_hz)
    q = math.sqrt(2.0)
    norm = 1.0 / (1.0 + q * k + k * k)
    b0 = k * k * norm
    b = [b0, 2.0 * b0, b0]
    a = [1.0, 2.0 * (k * k - 1.0) * norm, (1.0 - q * k + k * k) * norm]
    return b, a


def _biquad(b: Sequence[float], a: Sequence[float], x: Sequence[float]) -> list[float]:
    """Run a biquad (direct form II transposed) over `x`, starting in the steady state of a
    constant input `x[0]` (as `scipy.signal.lfilter_zi` does)."""
    x0 = x[0]
    z2 = (b[2] - a[2] * (b[0] + b[1] + b[2]) / (1 + a[1] + a[2])) * x0
    z1 = (b[1] + b[2] - (a[1] + a[2]) * (b[0] + b[1] + b[2]) / (1 + a[1] + a[2])) * x0
    y: list[float] = []
    for xi in x:
        yi = b[0] * xi + z1
        z1 = b[1] * xi - a[1] * yi + z2
        z2 = b[2] * xi - a[2] * yi
        y.append(yi)
    return y


def zero_lag_lowpass(x: Sequence[float], cutoff_hz: float, rate_hz: float) -> list[float]:
    """Zero-lag low-pass: a 2nd-order Butterworth section run forward, then backward
    (4th-order zero-lag overall; amplitude 0.5 at the cutoff). The ends are padded by odd
    reflection over `pad = min(len(x) - 1, round(3 * rate / cutoff))` samples, so the filter
    settles before the data start. Equals `scipy.signal.filtfilt(b, a, x, padlen=pad)`."""
    n = len(x)
    if n < 2:
        return list(x)
    b, a = butterworth2(cutoff_hz, rate_hz)
    pad = min(n - 1, round(3.0 * rate_hz / cutoff_hz))
    front = [2.0 * x[0] - x[i] for i in range(pad, 0, -1)]
    back = [2.0 * x[-1] - x[n - 1 - i] for i in range(1, pad + 1)]
    ext = front + list(x) + back
    fwd = _biquad(b, a, ext)
    bwd = _biquad(b, a, fwd[::-1])[::-1]
    return bwd[pad : pad + n]


def central_difference(t: Sequence[float], x: Sequence[float]) -> list[float]:
    """dx/dt: second-order central differences inside (exact for quadratics, also on uneven
    spacing), first-order one-sided differences at the two ends (as `numpy.gradient`)."""
    n = len(x)
    if n < 2:
        return [0.0] * n
    d = [0.0] * n
    d[0] = (x[1] - x[0]) / (t[1] - t[0])
    d[-1] = (x[-1] - x[-2]) / (t[-1] - t[-2])
    for i in range(1, n - 1):
        h0 = t[i] - t[i - 1]
        h1 = t[i + 1] - t[i]
        d[i] = (h0 * h0 * x[i + 1] - h1 * h1 * x[i - 1] + (h1 * h1 - h0 * h0) * x[i]) / (h0 * h1 * (h0 + h1))
    return d


def interp_linear(t_src: Sequence[float], x_src: Sequence[float], t_dst: Sequence[float]) -> list[float]:
    """Linear interpolation of `x_src(t_src)` (increasing times) at `t_dst`; ends held constant."""
    out: list[float] = []
    j = 0
    last = len(t_src) - 1
    for t in t_dst:
        if t <= t_src[0]:
            out.append(x_src[0])
            continue
        if t >= t_src[last]:
            out.append(x_src[last])
            continue
        while t_src[j + 1] < t:
            j += 1
        w = (t - t_src[j]) / (t_src[j + 1] - t_src[j])
        out.append(x_src[j] + w * (x_src[j + 1] - x_src[j]))
    return out


def contact_intervals(
    t: Sequence[float], fy: Sequence[float], threshold: float = CONTACT_THRESHOLD_N
) -> list[tuple[float, float]]:
    """Intervals `(on, off)` of foot contact: the foot is in contact while its vertical ground
    reaction force `fy` exceeds `threshold` (N). `on` is the first sample above the threshold
    (initial contact); `off` is the last sample above it (toe-off). Contact already present at
    the first sample, or still present at the last, yields an interval clipped to the data."""
    out: list[tuple[float, float]] = []
    start: float | None = None
    for i, (ti, f) in enumerate(zip(t, fy)):
        if f > threshold:
            if start is None:
                start = ti
        elif start is not None:
            out.append((start, t[i - 1]))
            start = None
    if start is not None:
        out.append((start, t[-1]))
    return out


def sample_rate(t: Sequence[float]) -> float:
    """Mean sampling rate (Hz) of increasing times `t`."""
    return (len(t) - 1) / (t[-1] - t[0])


# ---------------------------------------------------------------------------------------------
# Trial: kinematics and GRF on one time base.


@dataclass
class CoordinateInfo:
    name: str
    motion_type: str
    default_value: float


def kinematics_table(ik: Table, coords: Sequence[CoordinateInfo], cutoff_hz: float) -> Table:
    """Filtered coordinates (SI units) and their speeds, for every coordinate in `coords`.
    A coordinate absent from the IK file keeps its default value throughout."""
    t = ik.time
    rate = sample_rate(t)
    to_rad = ik.header.get("inDegrees", "no").lower() == "yes"
    values: dict[str, list[float]] = {}
    for c in coords:
        raw = ik.columns.get(c.name)
        if raw is None:
            series = [c.default_value] * len(t)
        elif to_rad and c.motion_type == "rotational":
            series = [math.radians(v) for v in raw]
        else:
            series = list(raw)
        values[c.name] = zero_lag_lowpass(series, cutoff_hz, rate)
    columns: dict[str, list[float]] = {"time": list(t)}
    columns.update(values)
    for c in coords:
        columns[c.name + SPEED_SUFFIX] = central_difference(t, values[c.name])
    labels = ["time"] + [c.name for c in coords] + [c.name + SPEED_SUFFIX for c in coords]
    return Table(labels, columns, {})


def grf_table(grf: Table, t: Sequence[float]) -> Table:
    """GRF columns renamed per `GRF_COLUMNS` and resampled onto times `t`."""
    columns: dict[str, list[float]] = {"time": list(t)}
    labels = ["time"]
    for s in SIDES:
        for out, src in GRF_COLUMNS.items():
            label = f"{out}_{s}"
            columns[label] = interp_linear(grf.time, grf.columns[src.format(s=s)], t)
            labels.append(label)
    return Table(labels, columns, {})


# ---------------------------------------------------------------------------------------------
# Model summary (OpenSim).


def base_body(frame: Any) -> str:
    """Name of the body (or ground) a frame is fixed to."""
    return str(frame.findBaseFrame().getName())


def coordinate_infos(model: Any, state: Any) -> list[CoordinateInfo]:
    cs = model.getCoordinateSet()
    return [
        CoordinateInfo(
            cs.get(i).getName(),
            MOTION_TYPES.get(int(cs.get(i).getMotionType()), "unknown"),
            float(cs.get(i).getDefaultValue()),
        )
        for i in range(cs.getSize())
    ]


def model_summary(osim: Any, model: Any, state: Any) -> dict[str, Any]:
    """The compact model description written to `model.json`.

    - `totalMass`: the model's mass (kg), for moments per kilogram.
    - `bodies`: name, `mass` (kg), `geometry` (mesh files attached to the body, `.vtp`).
    - `joints`: name, `parent` and `child` body.
    - `coordinates`: name, `joint`, `motionType` (rotational | translational | coupled),
      `range` [min, max] (rad or m), `locked` and `constrained` (coupled to another coordinate)
      in the model's default state.
    - `muscles`: name, `type` (OpenSim class), `maxIsometricForce` (N), `optimalFiberLength` (m),
      `tendonSlackLength` (m), `originBody` and `insertionBody` (bodies of the first and last
      path point), `pathBodies` (bodies of all path points in order, repeats collapsed).
    """
    bodies: list[dict[str, Any]] = []
    bs = model.getBodySet()
    for i in range(bs.getSize()):
        b = bs.get(i)
        meshes = []
        for g in range(b.getPropertyByName("attached_geometry").size()):
            mesh = osim.Mesh.safeDownCast(b.get_attached_geometry(g))
            if mesh is not None:
                meshes.append(str(mesh.get_mesh_file()))
        bodies.append({"name": b.getName(), "mass": float(b.getMass()), "geometry": meshes})

    js = model.getJointSet()
    joints = [
        {"name": j.getName(), "parent": base_body(j.getParentFrame()), "child": base_body(j.getChildFrame())}
        for j in (js.get(i) for i in range(js.getSize()))
    ]

    cs = model.getCoordinateSet()
    coordinates = []
    for i in range(cs.getSize()):
        c = cs.get(i)
        coordinates.append(
            {
                "name": c.getName(),
                "joint": c.getJoint().getName(),
                "motionType": MOTION_TYPES.get(int(c.getMotionType()), "unknown"),
                "range": [float(c.getRangeMin()), float(c.getRangeMax())],
                "locked": bool(c.getLocked(state)),
                "constrained": bool(c.isConstrained(state)),
            }
        )

    muscles = []
    ms = model.getMuscles()
    for i in range(ms.getSize()):
        m = ms.get(i)
        pps = m.getGeometryPath().getPathPointSet()
        path_bodies: list[str] = []
        for k in range(pps.getSize()):
            body = base_body(pps.get(k).getParentFrame())
            if not path_bodies or path_bodies[-1] != body:
                path_bodies.append(body)
        muscles.append(
            {
                "name": m.getName(),
                "type": m.getConcreteClassName(),
                "maxIsometricForce": float(m.getMaxIsometricForce()),
                "optimalFiberLength": float(m.getOptimalFiberLength()),
                "tendonSlackLength": float(m.getTendonSlackLength()),
                "originBody": path_bodies[0],
                "insertionBody": path_bodies[-1],
                "pathBodies": path_bodies,
            }
        )
    total = sum(float(b["mass"]) for b in bodies)
    return {"name": model.getName(), "totalMass": total, "bodies": bodies, "joints": joints, "coordinates": coordinates, "muscles": muscles}


def rel(path: Path) -> str:
    """`path` relative to the repository when inside it (keeps outputs machine-independent)."""
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def run(model_path: Path, ik_path: Path, grf_path: Path, out_model: Path, out_kin: Path, out_grf: Path) -> None:
    osim = opensim_module()
    model = osim.Model(str(model_path))
    state = model.initSystem()
    coords = coordinate_infos(model, state)

    ik = read_sto(ik_path)
    kin = kinematics_table(ik, coords, KINEMATICS_CUTOFF_HZ)
    grf_raw = read_sto(grf_path)
    grf = grf_table(grf_raw, kin.time)

    summary = model_summary(osim, model, state)
    summary["trial"] = {
        "coordinatesFile": rel(ik_path),
        "grfFile": rel(grf_path),
        "timeStart": kin.time[0],
        "timeEnd": kin.time[-1],
        "frames": len(kin.time),
        "rateHz": round(sample_rate(kin.time), 6),
        "grfRateHz": round(sample_rate(grf_raw.time), 6),
        "kinematicsCutoffHz": KINEMATICS_CUTOFF_HZ,
        "contactThresholdN": CONTACT_THRESHOLD_N,
    }
    out_model.parent.mkdir(parents=True, exist_ok=True)
    out_model.write_text(json.dumps(summary, indent=1) + "\n")
    write_csv(out_kin, kin.labels, kin.columns)
    write_csv(out_grf, grf.labels, grf.columns)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.load_model", description=__doc__.split("\n")[0])
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="scaled OpenSim model (.osim)")
    p.add_argument("--ik", type=Path, default=DEFAULT_IK, help="inverse-kinematics coordinates (.mot)")
    p.add_argument("--grf", type=Path, default=DEFAULT_GRF, help="ground reaction forces (.mot)")
    p.add_argument("--out-model", type=Path, default=WORK / "model.json")
    p.add_argument("--out-kinematics", type=Path, default=WORK / "kinematics.csv")
    p.add_argument("--out-grf", type=Path, default=WORK / "grf.csv")
    a = p.parse_args(argv)
    run(a.model, a.ik, a.grf, a.out_model, a.out_kinematics, a.out_grf)
    print(f"load_model: wrote {a.out_model}, {a.out_kinematics}, {a.out_grf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
