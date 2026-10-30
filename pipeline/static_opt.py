"""Stage `runStaticOpt`: muscle activations per frame by OpenSim static optimisation.

Method. OpenSim `AnalyzeTool` with one `StaticOptimization` analysis over every frame of the
filtered kinematics (`kinematics.csv` from `loadModel`), with the measured ground reaction forces
applied to the feet through the trial's external loads (`grf_walk.xml`: right GRF on `calcn_r`,
left on `calcn_l`, force and point expressed in ground). At each frame the analysis finds the
actuator controls that reproduce the model's generalised forces for the measured motion and
loads, minimising the sum over actuators of control squared (`ACTIVATION_EXPONENT` = 2), with
muscle force bounded by the force-length-velocity properties (`use_muscle_physiology`).

Actuators besides the 80 muscles (`extra_actuators`), each a `CoordinateActuator` with controls
unbounded; its generalised force equals control times optimal force, so its cost per unit of
force or torque falls as its optimal force rises:
  - residuals on the 6 pelvis coordinates, optimal force `RESIDUAL_OPTIMAL_FORCE` (N, N·m).
    Muscles act between body segments and therefore exert zero generalised force on the pelvis
    coordinates; the residuals alone balance the pelvis, so their strength leaves the muscle
    solution unchanged. A large value keeps their controls near 1 and their cost small.
  - joint actuators on the lumbar and arm coordinates, which carry no muscles in this model:
    the model's own actuators (optimal force 10 N·m) are replaced by ones of optimal force
    `NONMUSCLE_OPTIMAL_FORCE` for the same reason.
  - reserves on every unlocked lower-limb coordinate the muscles cross (hip ×3, knee, ankle per
    side), optimal force `RESERVE_OPTIMAL_FORCE` = 1 N·m: one N·m of reserve torque costs as
    much as one fully active muscle, so the reserves fill in only what the muscles cannot supply.
  Locked (subtalar, mtp, wrist) and coupled (knee beta) coordinates get no actuator.

Trial note. The left foot stands outside the force plates before ≈0.40 s and after ≈1.98 s (its
heel and toes sit at ground height while its measured force is 0 N). Over those frames the pelvis
residuals carry the missing load; the right-leg muscles see the measured right GRF throughout.
`static_opt.json` reports the peak residual and reserve per coordinate.

Inputs: --model (.osim), --external-loads (.xml), --grf (.mot, the data file the external loads
read), --kinematics (kinematics.csv). The AnalyzeTool reads coordinates from a `.mot`; this stage
writes that file from `kinematics.csv` (radians, `inDegrees=no`) into --scratch, and turns the
tool's own coordinate filter off (the values are filtered already).
Outputs (defaults under `data/work/`):
  --out-activations  activations.csv     `time`, then one column per muscle (model order), 0–1
  --out-forces       forces.csv          `time`, then one column per actuator: muscle tendon
                                         force (N), then the extra actuators' generalised force
                                         (N or N·m), named `reserve_<coordinate>`
  --out-settings     static_opt.json     solver settings, actuators, peak residuals and reserves
  --scratch          static_opt/         OpenSim setup, model, loads, coordinates and raw .sto
Run with the OpenSim environment's Python: `python -m pipeline.static_opt`.
"""
from __future__ import annotations

import argparse
import json
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


def coordinates_mot(kin: Table) -> Table:
    """The coordinate columns of `kinematics.csv` (speeds dropped) as a `.mot` table."""
    labels = [c for c in kin.labels if not c.endswith(SPEED_SUFFIX)]
    return Table(labels, {c: kin.columns[c] for c in labels}, {})


def extra_actuators(model: Any, state: Any) -> list[tuple[str, float, str]]:
    """`(coordinate, optimal force, kind)` for every non-muscle actuator this stage adds; kind is
    `residual`, `nonmuscle` (coordinate crossed by no muscle) or `reserve`."""
    cs = model.getCoordinateSet()
    ms = model.getMuscles()
    crossed: set[str] = set()
    for i in range(cs.getSize()):
        c = cs.get(i)
        if c.getName() in RESIDUAL_COORDINATES or c.getLocked(state) or c.isConstrained(state):
            continue
        if any(abs(ms.get(k).computeMomentArm(state, c)) > 1e-6 for k in range(ms.getSize())):
            crossed.add(c.getName())
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


def write_setup(osim: Any, scratch: Path, model_file: Path, coords_file: Path, loads_src: Path, grf: Path, t0: float, t1: float) -> Path:
    """Write the external loads (data file `grf`, absolute) and the AnalyzeTool setup; return
    the setup path. Both forces and their points are expressed in ground, so the loads need no
    model kinematics (OpenSim 4 reads none)."""
    loads = osim.ExternalLoads(str(loads_src), True)
    loads.setDataFileName(str(grf.resolve()))
    loads_file = scratch / "external_loads.xml"
    loads.printToXML(str(loads_file))
    # The upstream file carries `external_loads_model_kinematics_file`, which OpenSim 4 ignores
    # with a warning; drop it from the copy.
    text = re.sub(r"\s*<external_loads_model_kinematics_file>.*?</external_loads_model_kinematics_file>", "", loads_file.read_text(), flags=re.S)
    loads_file.write_text(text)

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


def peak_abs(table: Table, label: str) -> float:
    return max(abs(v) for v in table.columns[label])


def run(model_path: Path, loads_path: Path, grf_path: Path, kin_path: Path, out_act: Path, out_forces: Path, out_settings: Path, scratch: Path) -> dict[str, Any]:
    osim = opensim_module()
    # The model written to --scratch names its meshes relative to the source model's folder.
    osim.ModelVisualizer.addDirToGeometrySearchPaths(str(model_path.resolve().parent / "Geometry"))
    scratch.mkdir(parents=True, exist_ok=True)
    kin = read_csv(kin_path)
    coords_file = scratch / "coordinates.mot"
    write_sto(coords_file, coordinates_mot(kin), "coordinates", in_degrees=False)
    model_file = scratch / "model_static_opt.osim"
    muscles, extras = prepare_model(osim, model_path, model_file)
    t0, t1 = kin.time[0], kin.time[-1]
    setup = write_setup(osim, scratch, model_file, coords_file, loads_path, grf_path, t0, t1)

    started = time.monotonic()
    tool = osim.AnalyzeTool(str(setup))
    if not tool.run():
        raise RuntimeError("static_opt: AnalyzeTool failed")
    seconds = time.monotonic() - started

    act = read_sto(scratch / f"{TOOL_NAME}_StaticOptimization_activation.sto")
    frc = read_sto(scratch / f"{TOOL_NAME}_StaticOptimization_force.sto")
    write_csv(out_act, ["time", *muscles], {"time": act.time, **{m: act.columns[m] for m in muscles}})
    extra_names = [RESERVE_PREFIX + c for c, _, _ in extras]
    write_csv(out_forces, ["time", *muscles, *extra_names], {"time": frc.time, **{c: frc.columns[c] for c in [*muscles, *extra_names]}})

    settings: dict[str, Any] = {
        "tool": "OpenSim AnalyzeTool + StaticOptimization",
        "opensimVersion": str(osim.GetVersion()),
        "model": rel(model_path),
        "externalLoads": rel(loads_path),
        "grf": rel(grf_path),
        "kinematics": rel(kin_path),
        "timeStart": t0,
        "timeEnd": t1,
        "frames": len(act.time),
        "stepInterval": 1,
        "activationExponent": ACTIVATION_EXPONENT,
        "useMusclePhysiology": USE_MUSCLE_PHYSIOLOGY,
        "convergenceCriterion": CONVERGENCE_CRITERION,
        "maxIterations": MAX_ITERATIONS,
        "coordinateLowpassHz": None,
        "runtimeSeconds": round(seconds, 1),
        "actuators": [
            {"name": RESERVE_PREFIX + c, "coordinate": c, "kind": kind, "optimalForce": f, "peakAbsForce": peak_abs(frc, RESERVE_PREFIX + c)}
            for c, f, kind in extras
        ],
    }
    out_settings.parent.mkdir(parents=True, exist_ok=True)
    out_settings.write_text(json.dumps(settings, indent=1) + "\n")
    return settings


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.static_opt", description=__doc__.split("\n")[0])
    p.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="scaled OpenSim model (.osim)")
    p.add_argument("--external-loads", type=Path, default=DEFAULT_EXTERNAL_LOADS, help="OpenSim ExternalLoads (.xml)")
    p.add_argument("--grf", type=Path, default=DEFAULT_GRF, help="ground reaction forces (.mot) for the external loads")
    p.add_argument("--kinematics", type=Path, default=WORK / "kinematics.csv", help="output of loadModel")
    p.add_argument("--out-activations", type=Path, default=WORK / "activations.csv")
    p.add_argument("--out-forces", type=Path, default=WORK / "forces.csv")
    p.add_argument("--out-settings", type=Path, default=WORK / "static_opt.json")
    p.add_argument("--scratch", type=Path, default=WORK / "static_opt", help="directory for OpenSim's own files")
    a = p.parse_args(argv)
    s = run(a.model, a.external_loads, a.grf, a.kinematics, a.out_activations, a.out_forces, a.out_settings, a.scratch)
    print(f"static_opt: {s['frames']} frames in {s['runtimeSeconds']} s; wrote {a.out_activations}, {a.out_forces}, {a.out_settings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
