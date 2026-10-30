"""Smoke test for the OpenSim environment; run with the env's Python (see setup.sh).

Loads the scaled Rajagopal model and the walking trial's inverse-kinematics coordinates,
checks the motion's columns against the model's coordinates, and prints the counts. Then
loads the upper-body source models (Holzbaur arm, Mortensen neck; `initSystem()`) and
checks their muscle counts. A Christophy lumbar model placed by hand under
data/raw/christophy/ is loaded and reported too; a failure there is a note, not an error,
because that model is in the older OpenSim 2 format (survey K19 left it "to test").
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
RAW = REPO / "data" / "raw"

# Upper-body source models: (label, folder under data/raw, model file, expected muscle count).
UPPER_BODY = (
    ("holzbaur", "holzbaur", "Stanford_VA_Upper_Limb_original.osim", 50),
    ("mortensen", "mortensen", "HYOID_1.2_ScaledStrenght_UpdatedInertia.osim", 72),
)


def load_counts(folder: Path, model_file: Path) -> dict[str, Any]:
    """Load a model with its Geometry folder on the search path, run initSystem(), count parts."""
    opensim.ModelVisualizer.addDirToGeometrySearchPaths(str(folder / "Geometry"))
    # The Holzbaur file repeats wrap-object names in its paths; OpenSim renames them and
    # warns once per path, so the loader reads it at Error level.
    opensim.Logger.setLevelString("Error")
    try:
        model = opensim.Model(str(model_file))
        model.initSystem()
    finally:
        opensim.Logger.setLevelString("Warn")
    return {
        "name": model.getName(),
        "muscles": model.getMuscles().getSize(),
        "coordinates": model.getCoordinateSet().getSize(),
        "bodies": model.getBodySet().getSize(),
    }


def check_upper_body() -> int:
    """Load each fetched upper-body model; return the number of failures."""
    failures = 0
    for label, folder, name, expected in UPPER_BODY:
        path = RAW / folder / name
        if not path.is_file():
            print(f"check_env: missing {path}; run pipeline/env/fetch_data.sh", file=sys.stderr)
            failures += 1
            continue
        c = load_counts(RAW / folder, path)
        print(f"{label:<16}: {c['name']} ({name})")
        print(f"  muscles       : {c['muscles']} (expected {expected})")
        print(f"  coordinates   : {c['coordinates']}   bodies: {c['bodies']}")
        if c["muscles"] != expected:
            print(f"check_env: {label} has {c['muscles']} muscles, expected {expected}", file=sys.stderr)
            failures += 1
    chr_dir = RAW / "christophy"
    chr_models = sorted(chr_dir.glob("*.osim")) if chr_dir.is_dir() else []
    if not chr_models:
        print("christophy      : absent (manual download from simtk.org, see data/raw/christophy/README.md)")
    for path in chr_models:
        try:
            c = load_counts(chr_dir, path)
            print(f"christophy      : {c['name']} ({path.name}), muscles {c['muscles']}, "
                  f"coordinates {c['coordinates']}, bodies {c['bodies']}")
        except Exception as err:
            first = str(err).strip().splitlines()[0] if str(err).strip() else "load failed"
            print(f"christophy      : {path.name} does not load in this OpenSim ({first})")
    return failures


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
    return 1 if check_upper_body() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
