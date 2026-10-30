"""Smoke test for the OpenSim environment; run with the env's Python (see setup.sh).

Loads the scaled Rajagopal model and the walking trial's inverse-kinematics coordinates,
checks the motion's columns against the model's coordinates, and prints the counts.
Exit code 0 on success. Usage: check_env.py [RAJAGOPAL_DIR]   (default data/raw/rajagopal)
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

# opensim ships no type stubs and exists only in the conda env; Any keeps mypy clean everywhere.
opensim: Any = importlib.import_module("opensim")

REPO = Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    opensim.Logger.setLevelString("Warn")
    raj = Path(argv[1]) if len(argv) > 1 else REPO / "data" / "raw" / "rajagopal"
    model_file = raj / "walk_pipeline" / "Scale" / "subject_scaled_walk.osim"
    motion_file = raj / "walk_pipeline" / "IK" / "results_walk" / "ik_output_walk.mot"
    for f in (model_file, motion_file):
        if not f.is_file():
            print(f"check_env: missing {f}; run pipeline/env/fetch_data.sh", file=sys.stderr)
            return 1

    opensim.ModelVisualizer.addDirToGeometrySearchPaths(str(raj / "Geometry"))
    model = opensim.Model(str(model_file))
    model.initSystem()
    coords = model.getCoordinateSet()
    coord_names = {coords.get(i).getName() for i in range(coords.getSize())}

    table = opensim.TimeSeriesTable(str(motion_file))
    labels = set(table.getColumnLabels())
    unknown = sorted(labels - coord_names)
    # Coordinates absent from the motion (e.g. locked or constrained) are counted, not fatal.
    uncovered = sorted(coord_names - labels)
    times = table.getIndependentColumn()
    print(f"opensim version : {opensim.GetVersionAndDate()}")
    print(f"model           : {model.getName()} ({model_file.name})")
    print(f"muscles         : {model.getMuscles().getSize()}")
    print(f"coordinates     : {coords.getSize()}")
    print(f"bodies          : {model.getBodySet().getSize()}")
    print(f"motion columns  : {len(labels)} (all match model coordinates: {not unknown})")
    print(f"frames          : {table.getNumRows()}")
    print(f"time range      : {times[0]:.3f} .. {times[-1]:.3f} s")
    print(f"coordinates without motion column: {len(uncovered)} {uncovered}")
    if unknown:
        print(f"check_env: motion columns not in model: {unknown}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
