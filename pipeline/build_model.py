"""Stage `buildModel`: the one model and the one motion every later stage reads.

Today the stage is a pass-through: it copies the scaled Rajagopal model
(`pipeline_paths.SCALED_MODEL`) to `pipeline_paths.MERGED_MODEL` and the inverse-kinematics
motion (`pipeline_paths.IK_MOTION`) to `pipeline_paths.IK_FULL`, and reads the merge recipe
`pipeline/config/model.yaml` (`sources: []`, an empty recipe). Workstream M (`plan.md`) turns
it into the model merge of D-008 (trunk, arm and neck muscles attached to the Rajagopal
bodies), the head split of D-009, and the neck angles of D-010.

Run from the repository root: `python -m pipeline.build_model` (pure Python with PyYAML).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from pipeline.load_model import REPO
from pipeline.segment_phases import GENERATED  # noqa: F401  (puts generated/py on sys.path)

import pipeline_paths as paths  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="python -m pipeline.build_model", description=doc.split("\n")[0])
    ap.add_argument("--model", type=Path, default=REPO / paths.SCALED_MODEL)
    ap.add_argument("--ik", type=Path, default=REPO / paths.IK_MOTION)
    ap.add_argument("--recipe", type=Path, default=REPO / paths.MERGE_RECIPE)
    ap.add_argument("--out-model", type=Path, default=REPO / paths.MERGED_MODEL)
    ap.add_argument("--out-ik", type=Path, default=REPO / paths.IK_FULL)
    a = ap.parse_args(argv)
    recipe = yaml.safe_load(a.recipe.read_text()) or {}
    if recipe.get("sources"):
        raise ValueError(f"{a.recipe}: the pass-through build takes an empty `sources` list")
    a.out_model.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a.model, a.out_model)
    shutil.copyfile(a.ik, a.out_ik)
    print(f"build_model: pass-through; wrote {a.out_model}, {a.out_ik}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
