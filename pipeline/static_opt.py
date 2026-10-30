"""Stage `runStaticOpt`: muscle activations per frame by static optimisation.

Problem (OpenSim's `StaticOptimization`, `use_muscle_physiology` on). At every frame of the
filtered kinematics (`kinematics.csv` from `loadModel`), with the measured ground reaction forces
applied to the feet through the trial's external loads (`grf_walk.xml`: right GRF on `calcn_r`,
left on `calcn_l`, force and point expressed in ground), find the actuator controls x that
reproduce the measured accelerations of every free coordinate and minimise the sum over
actuators of control squared (`ACTIVATION_EXPONENT` = 2). A muscle's force is its activation times
its active fibre force at full activation with a rigid tendon at the frame's length and speed
(`calcInextensibleTendonActiveFiberForce`), activation bounded by the muscle's control range; an
extra actuator's generalised force is its control times its optimal force, control unbounded.

Method `qp` (the default, `solve_frames`). The accelerations are linear in the actuator forces, so
the constraint "free-coordinate accelerations equal the measured ones" is the generalised-force
balance projected on the free coordinates: Σ_j r_ij F_j x_j + D_i c_i = b_i, with r_ij muscle j's
moment arm about free coordinate i (OpenSim's, which follows the couplers), F_j its force at full
activation, D_i the optimal force of coordinate i's extra actuator, c_i its control, and b_i the
inverse-dynamics generalised force of the frame (`InverseDynamicsSolver`, muscles and extra
actuators switched off, external loads on) projected through the couplers onto coordinate i.
The minimum of Σ x² + Σ c² over that affine set and the activation bounds is unique (strictly
convex); `solve_qp` finds it exactly by Newton steps on the Lagrange multipliers. The states and
the target accelerations come from the coordinates the way OpenSim's AnalyzeTool builds them
(`states_and_accelerations`): speeds from quintic GCV splines of the coordinates, every frame
assembled to the model's constraints, target accelerations from quintic GCV splines of those
speeds; each coupled coordinate's acceleration follows its coupler. Each muscle's moment arms are
evaluated about the free coordinates its path can move (`path_coordinates`: the joints between
its path bodies and wrapping surfaces, a coupled coordinate standing for its independent one);
every other moment arm is zero. Frames run in parallel worker processes (`--workers`).

Method `analyze`: OpenSim's own `AnalyzeTool` with one `StaticOptimization` analysis (IPOPT,
convergence criterion `CONVERGENCE_CRITERION`). Both methods solve the same problem; `qp` exactly,
`analyze` to IPOPT's tolerance. On the merged model (462 muscles, 238 frames) `analyze` took
18 minutes of wall time on 8 cores; `qp` takes 57 s on 4 worker processes (3.4 CPU-minutes, 0.86
CPU-seconds per frame, most of it in OpenSim's moment arms).

Actuators besides the muscles (`extra_actuators`), each a `CoordinateActuator` with controls
unbounded; its generalised force equals control times optimal force, so its cost per unit of
force or torque falls as its optimal force rises:
  - residuals on the 6 pelvis coordinates, optimal force `RESIDUAL_OPTIMAL_FORCE` (N, N·m).
    Muscles act between body segments and therefore exert zero generalised force on the pelvis
    coordinates; the residuals alone balance the pelvis, so their strength leaves the muscle
    solution unchanged. A large value keeps their controls near 1 and their cost small.
  - reserves on every free coordinate a muscle crosses, optimal force `RESERVE_OPTIMAL_FORCE` =
    1 N·m: one N·m of reserve torque costs as much as one fully active muscle, so the reserves
    fill in only what the muscles cannot supply. In the merged model (stage `buildModel`) the
    muscles cross every free coordinate: legs, lumbar, shoulders, elbows, forearms, wrists, neck.
  - joint actuators of optimal force `NONMUSCLE_OPTIMAL_FORCE` on any free coordinate crossed by
    no muscle (the Rajagopal model's arm and lumbar coordinates before the merge); the model's
    own torque actuators are removed.
  Locked and coupled coordinates (subtalar, mtp, knee beta, the vertebral and wrapping-body
  couplers) get no actuator.

Trial note. The left foot stands outside the force plates before ≈0.40 s and after ≈1.98 s (its
heel and toes sit at ground height while its measured force is 0 N). Over those frames the pelvis
residuals carry the missing load; the right-leg muscles see the measured right GRF throughout.
`static_opt.json` reports the peak and RMS residual and reserve per coordinate over the run.

Inputs: --model (.osim), --external-loads (.xml), --grf (.mot, the data file the external loads
read), --kinematics (kinematics.csv). Both methods read the coordinates as the AnalyzeTool reads a
`.mot` that this stage writes from `kinematics.csv` (radians, `inDegrees=no`) into --scratch, with
the tool's own coordinate filter off (the values are filtered already).
Outputs (defaults under `data/work/`):
  --out-activations  activations.csv     `time`, then one column per muscle (model order), 0–1
  --out-forces       forces.csv          `time`, then one column per actuator: muscle tendon
                                         force (N), then the extra actuators' generalised force
                                         (N or N·m), named `reserve_<coordinate>`
  --out-settings     static_opt.json     solver settings, actuators, peak and RMS residuals and
                                         reserves
  --scratch          static_opt/         OpenSim setup, model, loads, coordinates (and, for
                                         `analyze`, the raw .sto)
Run with the OpenSim environment's Python: `python -m pipeline.static_opt`. It prints the wall
time of the stage.
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
import multiprocessing
import os
import re
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pipeline.load_model import (
    DEFAULT_GRF,
    DEFAULT_MODEL,
    RAW,
    SPEED_SUFFIX,
    WORK,
    Table,
    opensim_module,
    read_csv,
    read_sto,
    rel,
    write_csv,
    write_sto,
)

DEFAULT_EXTERNAL_LOADS = RAW / "ID" / "grf_walk.xml"

ACTIVATION_EXPONENT = 2.0
CONVERGENCE_CRITERION = 1e-4
MAX_ITERATIONS = 100
USE_MUSCLE_PHYSIOLOGY = True

RESIDUAL_OPTIMAL_FORCE = 1000.0
NONMUSCLE_OPTIMAL_FORCE = 1000.0
RESERVE_OPTIMAL_FORCE = 1.0

RESIDUAL_COORDINATES = ("pelvis_tilt", "pelvis_list", "pelvis_rotation", "pelvis_tx", "pelvis_ty", "pelvis_tz")
RESERVE_PREFIX = "reserve_"
TOOL_NAME = "walk"
DEFAULT_WORKERS = min(8, os.cpu_count() or 1)


def coordinates_mot(kin: Table) -> Table:
    """The coordinate columns of `kinematics.csv` (speeds dropped) as a `.mot` table."""
    labels = [c for c in kin.labels if not c.endswith(SPEED_SUFFIX)]
    return Table(labels, {c: kin.columns[c] for c in labels}, {})


def extra_actuators(model: Any, state: Any) -> list[tuple[str, float, str]]:
    """`(coordinate, optimal force, kind)` for every non-muscle actuator this stage adds; kind is
    `residual`, `nonmuscle` (coordinate crossed by no muscle) or `reserve`. One per free
    coordinate, in coordinate-set order."""
    osim = opensim_module()
    cs = model.getCoordinateSet()
    ms = model.getMuscles()
    crossed: set[str] = set()
    for m, coords in path_coordinates(osim, model, state).items():
        mu = ms.get(m)
        for c in coords:
            if c not in RESIDUAL_COORDINATES and c not in crossed and abs(mu.computeMomentArm(state, cs.get(c))) > 1e-6:
                crossed.add(c)
    out: list[tuple[str, float, str]] = []
    for i in range(cs.getSize()):
        c = cs.get(i)
        name = c.getName()
        if name in RESIDUAL_COORDINATES:
            out.append((name, RESIDUAL_OPTIMAL_FORCE, "residual"))
        elif c.getLocked(state) or c.isConstrained(state):
            continue
        elif name in crossed:
            out.append((name, RESERVE_OPTIMAL_FORCE, "reserve"))
        else:
            out.append((name, NONMUSCLE_OPTIMAL_FORCE, "nonmuscle"))
    return out


def free_coordinates(model: Any, state: Any) -> list[str]:
    """Coordinates that are neither locked nor coupled, in coordinate-set order: the ones whose
    accelerations static optimisation matches."""
    cs = model.getCoordinateSet()
    return [str(cs.get(i).getName()) for i in range(cs.getSize()) if not cs.get(i).isConstrained(state)]


def path_coordinates(osim: Any, model: Any, state: Any) -> dict[str, list[str]]:
    """Muscle -> the free coordinates its path can move: the coordinates of every joint between
    the bodies its path points and wrapping surfaces hang on (the joints on some but not all of
    their chains to ground), a coupled coordinate standing for its independent coordinate."""
    from pipeline.build_model import model_couplers

    parent: dict[str, tuple[str, Any]] = {}
    js = model.getJointSet()
    for i in range(js.getSize()):
        j = js.get(i)
        parent[str(j.getChildFrame().findBaseFrame().getName())] = (str(j.getParentFrame().findBaseFrame().getName()), j)

    def chain(body: str) -> set[str]:
        out = set()
        while body in parent:
            body, j = parent[body]
            out.add(str(j.getName()))
        return out

    independent = {c.dependent: c.independents[0] for c in model_couplers(osim, model) if len(c.independents) == 1}
    free = set(free_coordinates(model, state))
    coords_of = {str(js.get(i).getName()): [str(js.get(i).get_coordinates(k).getName()) for k in range(js.get(i).numCoordinates())] for i in range(js.getSize())}
    out: dict[str, list[str]] = {}
    ms = model.getMuscles()
    for i in range(ms.getSize()):
        mu = ms.get(i)
        gp = mu.getGeometryPath()
        pps = gp.getPathPointSet()
        bodies = {str(pps.get(k).getParentFrame().findBaseFrame().getName()) for k in range(pps.getSize())}
        ws = gp.getWrapSet()
        bodies |= {str(ws.get(k).getWrapObject().getFrame().findBaseFrame().getName()) for k in range(ws.getSize())}
        chains = [chain(b) for b in bodies]
        joints = set().union(*chains) - chains[0].intersection(*chains[1:])
        found: list[str] = []
        for jn in sorted(joints):
            for c in coords_of[jn]:
                c = independent.get(c, c)
                if c in free and c not in found:
                    found.append(c)
        cs = model.getCoordinateSet()
        out[str(mu.getName())] = sorted(found, key=lambda c: cs.getIndex(c))
    return out


def prepare_model(osim: Any, model_path: Path, out: Path) -> tuple[list[str], list[tuple[str, float, str]]]:
    """Write the model with its non-muscle actuators replaced by `extra_actuators`; return the
    muscle names and the added actuators."""
    model = osim.Model(str(model_path))
    state = model.initSystem()
    extras = extra_actuators(model, state)
    fs = model.getForceSet()
    for i in reversed(range(fs.getSize())):
        if osim.Muscle.safeDownCast(fs.get(i)) is None and osim.Actuator.safeDownCast(fs.get(i)) is not None:
            fs.remove(i)
    for coord, optimal, _ in extras:
        act = osim.CoordinateActuator(coord)
        act.setName(RESERVE_PREFIX + coord)
        act.setOptimalForce(optimal)
        act.setMinControl(-float("inf"))
        act.setMaxControl(float("inf"))
        model.addForce(act)
    model.finalizeConnections()
    model.printToXML(str(out))
    ms = model.getMuscles()
    return [ms.get(i).getName() for i in range(ms.getSize())], extras


def write_loads(osim: Any, scratch: Path, loads_src: Path, grf: Path) -> Path:
    """Write the external loads with their data file `grf` (absolute); return the path. Both
    forces and their points are expressed in ground, so the loads need no model kinematics
    (OpenSim 4 reads none)."""
    loads = osim.ExternalLoads(str(loads_src), True)
    loads.setDataFileName(str(grf.resolve()))
    loads_file = scratch / "external_loads.xml"
    loads.printToXML(str(loads_file))
    # The upstream file carries `external_loads_model_kinematics_file`, which OpenSim 4 ignores
    # with a warning; drop it from the copy.
    text = re.sub(r"\s*<external_loads_model_kinematics_file>.*?</external_loads_model_kinematics_file>", "", loads_file.read_text(), flags=re.S)
    loads_file.write_text(text)
    return loads_file


def write_setup(osim: Any, scratch: Path, model_file: Path, coords_file: Path, loads_file: Path, t0: float, t1: float) -> Path:
    """Write the AnalyzeTool setup (method `analyze`); return its path."""
    so = osim.StaticOptimization()
    so.setName("StaticOptimization")
    so.setStartTime(t0)
    so.setEndTime(t1)
    so.setStepInterval(1)
    so.setUseModelForceSet(True)
    so.setActivationExponent(ACTIVATION_EXPONENT)
    so.setUseMusclePhysiology(USE_MUSCLE_PHYSIOLOGY)
    so.setConvergenceCriterion(CONVERGENCE_CRITERION)
    so.setMaxIterations(MAX_ITERATIONS)
    so.setInDegrees(False)

    tool = osim.AnalyzeTool()
    tool.setName(TOOL_NAME)
    tool.setModelFilename(str(model_file.resolve()))
    tool.setCoordinatesFileName(str(coords_file.resolve()))
    tool.setLowpassCutoffFrequency(-1.0)
    tool.setExternalLoadsFileName(str(loads_file.resolve()))
    tool.setReplaceForceSet(False)
    tool.setInitialTime(t0)
    tool.setFinalTime(t1)
    tool.setResultsDir(str(scratch.resolve()))
    tool.getAnalysisSet().cloneAndAppend(so)
    setup = scratch / "analyze_setup.xml"
    tool.printToXML(str(setup))
    return setup


# ---------------------------------------------------------------------------------------------
# Method `qp`.


def numpy_module() -> Any:
    """numpy, imported on first use (it lives in the OpenSim environment)."""
    return importlib.import_module("numpy")


def solve_qp(np: Any, a: Any, d: Any, b: Any, lo: Any, hi: Any, lam: Any | None = None, tol: float = 1e-10, max_iter: int = 100) -> tuple[Any, Any, Any, int]:
    """The minimiser of |x|^2 + |c|^2 subject to a x + d c = b (d element-wise, every d_i > 0) and
    lo <= x <= hi. Its Lagrange multipliers λ give x = clip(aᵀλ / 2, lo, hi) and c = d λ / 2; the
    residual a x + d c - b is piecewise linear and monotone in λ, and Newton steps on it (with
    backtracking on the concave dual function) reach its root exactly. Returns x, c, λ and the
    number of Newton steps; `lam` warm-starts the multipliers."""
    m = len(b)
    lam = np.zeros(m) if lam is None else lam.copy()

    def primal(l: Any) -> tuple[Any, Any, Any]:
        y = a.T @ l / 2.0
        return np.clip(y, lo, hi), d * l / 2.0, y

    def dual(l: Any) -> float:
        x, c, _ = primal(l)
        return float(x @ x + c @ c - l @ (a @ x + d * c - b))

    scale = 1.0 + float(np.abs(b).max())
    for it in range(max_iter):
        x, c, y = primal(lam)
        r = a @ x + d * c - b
        if float(np.abs(r).max()) <= tol * scale:
            return x, c, lam, it
        inside = (y > lo) & (y < hi)
        ai = a[:, inside]
        jac = ai @ ai.T / 2.0 + np.diag(d * d / 2.0)
        step = np.linalg.solve(jac, r)
        g0, t = dual(lam), 1.0
        while dual(lam - t * step) < g0 - 1e-14 * abs(g0) and t > 1e-8:
            t /= 2.0
        lam = lam - t * step
    raise RuntimeError("static_opt: the QP's Newton steps did not converge")


def states_and_accelerations(osim: Any, model: Any, state: Any, times: Sequence[float], q: dict[str, list[float]]) -> tuple[list[list[float]], list[list[float]], list[list[float]]]:
    """Per frame, every coordinate's value and speed and the target acceleration, as OpenSim's
    AnalyzeTool and StaticOptimization build them from a coordinates file: speeds are the first
    derivatives of quintic GCV splines through the coordinates (`GCVSplineSet(5, ...)`), each
    frame is assembled to the model's constraints, and the target accelerations are the first
    derivatives of quintic GCV splines through the assembled speeds. Lists follow the model's
    coordinate-set order."""
    cs = model.getCoordinateSet()
    names = [str(cs.get(i).getName()) for i in range(cs.getSize())]

    def splines(rows: list[list[float]]) -> Any:
        store = osim.Storage()
        labels = osim.ArrayStr()
        for n in ["time", *names]:
            labels.append(n)
        store.setColumnLabels(labels)
        for t, row in zip(times, rows):
            v = osim.Vector(len(row), 0.0)
            for k, x in enumerate(row):
                v.set(k, x)
            store.append(t, v)
        return osim.GCVSplineSet(5, store)

    q_rows = [[q[n][i] for n in names] for i in range(len(times))]
    qs = splines(q_rows)
    u_rows = [[qs.evaluate(k, 1, t) for k in range(len(names))] for t in times]
    qa, ua = [], []
    for row_q, row_u in zip(q_rows, u_rows):
        for k, n in enumerate(names):
            c = cs.get(k)
            c.setValue(state, row_q[k], False)
            c.setSpeedValue(state, row_u[k])
        model.assemble(state)
        qa.append([float(cs.get(k).getValue(state)) for k in range(len(names))])
        ua.append([float(cs.get(k).getSpeedValue(state)) for k in range(len(names))])
    us = splines(ua)
    acc = [[us.evaluate(k, 1, t) for k in range(len(names))] for t in times]
    return qa, ua, acc


class FrameSolver:
    """The model with its extra actuators and the external loads, ready to solve frames."""

    def __init__(self, osim: Any, model_file: Path, loads_file: Path) -> None:
        from pipeline.build_model import model_couplers

        self.osim = osim
        self.np = numpy_module()
        model = osim.Model(str(model_file))
        fs = model.getForceSet()
        for i in range(fs.getSize()):
            if osim.Actuator.safeDownCast(fs.get(i)) is not None:
                fs.get(i).set_appliesForce(False)
        model.addModelComponent(osim.ExternalLoads(str(loads_file), True))
        self.model = model
        self.state = model.initSystem()
        cs = model.getCoordinateSet()
        self.names = [str(cs.get(i).getName()) for i in range(cs.getSize())]
        for i in range(cs.getSize()):
            cs.get(i).setSpeedValue(self.state, float(i + 1))
        u = self.state.getU()
        self.uindex = {self.names[int(round(u.get(k))) - 1]: k for k in range(u.size())}
        self.free = free_coordinates(model, self.state)
        self.locked = {n for n in self.names if cs.get(n).getLocked(self.state)}
        self.couplers = [c for c in model_couplers(osim, model) if c.dependent not in self.locked]
        ms = model.getMuscles()
        self.muscles = [str(ms.get(i).getName()) for i in range(ms.getSize())]
        self.paths = path_coordinates(osim, model, self.state)
        extras = {}
        for i in range(fs.getSize()):
            act = osim.CoordinateActuator.safeDownCast(fs.get(i))
            if act is not None:
                extras[str(act.get_coordinate())] = (str(act.getName()), float(act.getOptimalForce()))
        if sorted(extras) != sorted(self.free):
            raise ValueError("static_opt: every free coordinate needs exactly one extra actuator")
        self.extras = [extras[c] for c in self.free]
        self.lo = self.np.array([float(ms.get(m).getMinControl()) for m in self.muscles])
        self.hi = self.np.array([float(ms.get(m).getMaxControl()) for m in self.muscles])
        self.d = self.np.array([f for _, f in self.extras])
        self.id = osim.InverseDynamicsSolver(model)
        self.lam: Any | None = None

    def derivative(self, fn: Any, x: float, order: int) -> float:
        v = self.osim.StdVectorInt()
        for _ in range(order):
            v.push_back(0)
        return float(fn.calcDerivative(v, self.osim.Vector(1, x)))

    def solve(self, time: float, q: Sequence[float], u: Sequence[float], acc: Sequence[float]) -> tuple[list[float], list[float], list[float]]:
        """(activations, muscle forces, extra-actuator generalised forces) at one frame."""
        np, osim, s, model = self.np, self.osim, self.state, self.model
        cs = model.getCoordinateSet()
        s.setTime(time)
        for k, n in enumerate(self.names):
            cs.get(k).setValue(s, q[k], False)
            cs.get(k).setSpeedValue(s, u[k])
        model.assemble(s)
        model.realizeVelocity(s)
        value = {n: float(cs.get(n).getValue(s)) for n in self.names}
        speed = {n: float(cs.get(n).getSpeedValue(s)) for n in self.names}
        target = {n: acc[k] for k, n in enumerate(self.names)}
        udot = osim.Vector(s.getNU(), 0.0)
        for n in self.free:
            udot.set(self.uindex[n], target[n])
        slope: dict[str, list[tuple[str, float]]] = {}
        for c in self.couplers:
            i = c.independents[0]
            d1 = c.scale * self.derivative(c.function, value[i], 1)
            d2 = c.scale * self.derivative(c.function, value[i], 2)
            udot.set(self.uindex[c.dependent], d1 * target[i] + d2 * speed[i] ** 2)
            slope.setdefault(i, []).append((c.dependent, d1))
        tau = self.id.solve(s, udot)
        b = np.array([float(tau.get(self.uindex[n])) + sum(k * float(tau.get(self.uindex[dep])) for dep, k in slope.get(n, [])) for n in self.free])
        row = {n: k for k, n in enumerate(self.free)}
        ms = model.getMuscles()
        a = np.zeros((len(self.free), len(self.muscles)))
        fopt = np.zeros(len(self.muscles))
        for j, m in enumerate(self.muscles):
            mu = ms.get(j)
            fopt[j] = float(mu.calcInextensibleTendonActiveFiberForce(s, 1.0))
            for n in self.paths[m]:
                a[row[n], j] = float(mu.computeMomentArm(s, cs.get(n))) * fopt[j]
        x, c, self.lam, _ = solve_qp(np, a, self.d, b, self.lo, self.hi, self.lam)
        return [float(v) for v in x], [float(v) for v in x * fopt], [float(v) for v in c * self.d]


_SOLVER: FrameSolver | None = None


def _solve_chunk(chunk: Sequence[tuple[float, Sequence[float], Sequence[float], Sequence[float]]]) -> list[tuple[list[float], list[float], list[float]]]:
    assert _SOLVER is not None
    _SOLVER.lam = None
    return [_SOLVER.solve(*frame) for frame in chunk]


def solve_frames(solver: FrameSolver, frames: Sequence[tuple[float, Sequence[float], Sequence[float], Sequence[float]]], workers: int) -> list[tuple[list[float], list[float], list[float]]]:
    """Every frame, in order: contiguous chunks of frames on `workers` forked processes, each
    warm-starting its multipliers from the frame before."""
    global _SOLVER
    _SOLVER = solver
    if workers <= 1:
        return _solve_chunk(frames)
    n = len(frames)
    size = -(-n // workers)
    chunks = [frames[i : i + size] for i in range(0, n, size)]
    with multiprocessing.get_context("fork").Pool(len(chunks)) as pool:
        parts = pool.map(_solve_chunk, chunks)
    return [r for part in parts for r in part]


def peak_abs(table: Table, label: str) -> float:
    return max(abs(v) for v in table.columns[label])


def rms(table: Table, label: str) -> float:
    v = table.columns[label]
    return math.sqrt(sum(x * x for x in v) / len(v))


def run(model_path: Path, loads_path: Path, grf_path: Path, kin_path: Path, out_act: Path, out_forces: Path, out_settings: Path, scratch: Path, method: str = "qp", workers: int = 1) -> dict[str, Any]:
    started = time.monotonic()
    osim = opensim_module()
    # The model written to --scratch names its meshes relative to the source model's folder.
    osim.ModelVisualizer.addDirToGeometrySearchPaths(str(model_path.resolve().parent / "Geometry"))
    scratch.mkdir(parents=True, exist_ok=True)
    kin = read_csv(kin_path)
    coords_file = scratch / "coordinates.mot"
    coords = coordinates_mot(kin)
    write_sto(coords_file, coords, "coordinates", in_degrees=False)
    model_file = scratch / "model_static_opt.osim"
    muscles, extras = prepare_model(osim, model_path, model_file)
    loads_file = write_loads(osim, scratch, loads_path, grf_path)
    t0, t1 = kin.time[0], kin.time[-1]
    extra_names = [RESERVE_PREFIX + c for c, _, _ in extras]

    if method == "analyze":
        setup = write_setup(osim, scratch, model_file, coords_file, loads_file, t0, t1)
        tool = osim.AnalyzeTool(str(setup))
        if not tool.run():
            raise RuntimeError("static_opt: AnalyzeTool failed")
        act = read_sto(scratch / f"{TOOL_NAME}_StaticOptimization_activation.sto")
        frc = read_sto(scratch / f"{TOOL_NAME}_StaticOptimization_force.sto")
        times = act.time
        activation = {m: act.columns[m] for m in muscles}
        force = {c: frc.columns[c] for c in [*muscles, *extra_names]}
    elif method == "qp":
        solver = FrameSolver(osim, model_file, loads_file)
        if solver.muscles != muscles or [n for n, _ in solver.extras] != extra_names:
            raise ValueError("static_opt: actuator order differs between the written and loaded model")
        times = kin.time
        q, u, acc = states_and_accelerations(osim, solver.model, solver.state, times, {c: coords.columns[c] for c in coords.labels[1:]})
        results = solve_frames(solver, list(zip(times, q, u, acc)), workers)
        activation = {m: [r[0][j] for r in results] for j, m in enumerate(muscles)}
        force = {m: [r[1][j] for r in results] for j, m in enumerate(muscles)}
        force.update({e: [r[2][k] for r in results] for k, e in enumerate(extra_names)})
    else:
        raise ValueError(f"static_opt: method {method} unknown")
    seconds = time.monotonic() - started

    write_csv(out_act, ["time", *muscles], {"time": list(times), **activation})
    write_csv(out_forces, ["time", *muscles, *extra_names], {"time": list(times), **force})
    frc_table = Table(["time", *extra_names], {"time": list(times), **{e: force[e] for e in extra_names}}, {})
    settings: dict[str, Any] = {
        "tool": "static optimisation, exact QP (pipeline/static_opt.py)" if method == "qp" else "OpenSim AnalyzeTool + StaticOptimization",
        "method": method,
        "workers": workers if method == "qp" else 1,
        "opensimVersion": str(osim.GetVersion()),
        "model": rel(model_path),
        "externalLoads": rel(loads_path),
        "grf": rel(grf_path),
        "kinematics": rel(kin_path),
        "timeStart": t0,
        "timeEnd": t1,
        "frames": len(times),
        "stepInterval": 1,
        "activationExponent": ACTIVATION_EXPONENT,
        "useMusclePhysiology": USE_MUSCLE_PHYSIOLOGY,
        "convergenceCriterion": CONVERGENCE_CRITERION if method == "analyze" else None,
        "maxIterations": MAX_ITERATIONS if method == "analyze" else None,
        "coordinateLowpassHz": None,
        "runtimeSeconds": round(seconds, 1),
        "actuators": [
            {"name": RESERVE_PREFIX + c, "coordinate": c, "kind": kind, "optimalForce": f, "peakAbsForce": peak_abs(frc_table, RESERVE_PREFIX + c), "rmsForce": rms(frc_table, RESERVE_PREFIX + c)}
            for c, f, kind in extras
        ],
    }
    out_settings.parent.mkdir(parents=True, exist_ok=True)
    out_settings.write_text(json.dumps(settings, indent=1) + "\n")
    return settings


BLAS_THREADS = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
"""Environment variables that cap BLAS threads at one per process: the QP's matrices are small,
and threads on top of `--workers` processes oversubscribe the cores (on 4 workers here: 57 s
wall and 3.4 CPU-minutes with one thread each, 64 s and 7.9 CPU-minutes without the cap)."""


def main(argv: Sequence[str] | None = None) -> int:
    for var in BLAS_THREADS:
        os.environ.setdefault(var, "1")
    p = argparse.ArgumentParser(prog="python -m pipeline.static_opt", description=__doc__.split("\n")[0])
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="merged OpenSim model (.osim)")
    p.add_argument("--external-loads", type=Path, default=DEFAULT_EXTERNAL_LOADS, help="OpenSim ExternalLoads (.xml)")
    p.add_argument("--grf", type=Path, default=DEFAULT_GRF, help="ground reaction forces (.mot) for the external loads")
    p.add_argument("--kinematics", type=Path, default=WORK / "kinematics.csv", help="output of loadModel")
    p.add_argument("--out-activations", type=Path, default=WORK / "activations.csv")
    p.add_argument("--out-forces", type=Path, default=WORK / "forces.csv")
    p.add_argument("--out-settings", type=Path, default=WORK / "static_opt.json")
    p.add_argument("--scratch", type=Path, default=WORK / "static_opt", help="directory for OpenSim's own files")
    p.add_argument("--method", choices=("qp", "analyze"), default="qp", help="exact QP (default) or OpenSim's AnalyzeTool")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="processes for method qp (default: the CPU count, at most 8)")
    a = p.parse_args(argv)
    s = run(a.model, a.external_loads, a.grf, a.kinematics, a.out_activations, a.out_forces, a.out_settings, a.scratch, a.method, a.workers)
    print(f"static_opt: {s['frames']} frames, method {s['method']}, {s['workers']} workers, wall time {s['runtimeSeconds']} s; wrote {a.out_activations}, {a.out_forces}, {a.out_settings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
