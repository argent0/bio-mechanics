"""Derive the walking trial's coordinates from the upstream Rajagopal setups.

Runs, with the OpenSim Python API and the same order as the upstream pipeline
(Pipelines/Rajagopal/scripts/makeSimulation.m, walking branch):
  1. ScaleTool  Scale/scale_setup_walk_scaleOnly.xml  (measurement scaling, static_walk_1.trc)
  2. ScaleTool  Scale/scale_setup_walk.xml            (marker placement, static_walk_2.trc)
  3. InverseKinematicsTool IK/ik_setup_walk.xml       (motion_capture_walk.trc -> coordinates)
Outputs under <rajagopal dir>/walk_pipeline/:
  Scale/subject_scaled_walk.osim            scaled model with the 80 muscles
  IK/results_walk/ik_output_walk.mot        joint coordinates per frame (degrees for rotations)
Skips the work when the IK output is newer than every input. Usage: make_trial.py DIR
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

# opensim ships no type stubs and exists only in the conda env; Any keeps mypy clean everywhere.
opensim: Any = importlib.import_module("opensim")


def run_scale(setup: Path) -> None:
    os.chdir(setup.parent)  # the setups use paths relative to their own directory
    opensim.ScaleTool(str(setup)).run()


def main(argv: list[str]) -> int:
    opensim.Logger.setLevelString("Warn")  # IK logs one line per frame at Info
    rajagopal = Path(argv[1]).resolve()
    pipe = rajagopal / "walk_pipeline"
    opensim.ModelVisualizer.addDirToGeometrySearchPaths(str(rajagopal / "Geometry"))
    out = pipe / "IK" / "results_walk" / "ik_output_walk.mot"
    inputs = [rajagopal / "Rajagopal2016.osim", *sorted(pipe.glob("*/*.xml")), *sorted(pipe.glob("ExpData/*"))]
    if out.exists() and all(out.stat().st_mtime >= p.stat().st_mtime for p in inputs):
        print(f"make_trial: up to date: {out}")
        return 0
    run_scale(pipe / "Scale" / "scale_setup_walk_scaleOnly.xml")
    run_scale(pipe / "Scale" / "scale_setup_walk.xml")
    ik_dir = pipe / "IK"
    (ik_dir / "results_walk").mkdir(exist_ok=True)
    os.chdir(ik_dir)
    opensim.InverseKinematicsTool(str(ik_dir / "ik_setup_walk.xml")).run()
    if not out.exists():
        print(f"make_trial: IK produced no {out}", file=sys.stderr)
        return 1
    print(f"make_trial: wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
