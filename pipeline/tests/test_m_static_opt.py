"""Workstream M, task K26: static optimisation as an exact QP (`pipeline/static_opt.py`, method
`qp`), against OpenSim's AnalyzeTool (method `analyze`).

Pinned numbers:
  - `solve_qp` meets the optimality conditions of min |x|^2 + |c|^2 subject to a x + d c = b and
    the bounds: residual below 1e-9 of |b|, x the clipped multiplier image.
  - On the scaled Rajagopal model (legs only, today's leg pipeline) the two methods agree muscle by
    muscle within `QP_VS_ANALYZE_RMS` of activation over the whole trial: `qp` solves the problem
    exactly, `analyze` to IPOPT's convergence criterion (1e-4), whose optimum costs slightly more.
  - Every muscle-coordinate pair with a moment arm in `data/work/moment_arms.csv` (stage
    `computeMomentArms` on the merged model) lies in `path_coordinates`, the pairs `qp` evaluates.
"""
from __future__ import annotations

import csv
import math
import random
from collections.abc import Iterator
from pathlib import Path

import pytest

from pipeline import static_opt as so
from pipeline.load_model import REPO, Table, read_csv

import pipeline_paths as paths

QP_VS_ANALYZE_RMS = 0.005


def test_solve_qp_meets_the_optimality_conditions() -> None:
    np = pytest.importorskip("numpy")
    rng = random.Random(7)
    for trial in range(20):
        m, n = rng.randint(1, 8), rng.randint(1, 40)
        a = np.array([[rng.gauss(0.0, 50.0) if rng.random() < 0.5 else 0.0 for _ in range(n)] for _ in range(m)])
        d = np.array([rng.choice([1.0, 1000.0]) for _ in range(m)])
        b = np.array([rng.gauss(0.0, 80.0) for _ in range(m)])
        lo, hi = np.full(n, 0.01), np.ones(n)
        x, c, lam, _ = so.solve_qp(np, a, d, b, lo, hi)
        assert float(np.abs(a @ x + d * c - b).max()) <= 1e-9 * (1.0 + float(np.abs(b).max()))
        assert np.allclose(x, np.clip(a.T @ lam / 2.0, lo, hi)) and np.allclose(c, d * lam / 2.0)
        assert float(x.min()) >= 0.01 - 1e-12 and float(x.max()) <= 1.0 + 1e-12


@pytest.fixture(scope="module")
def legs(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Table]]:
    pytest.importorskip("opensim")
    from pipeline import load_model

    d = tmp_path_factory.mktemp("k26")
    model = ["--model", str(REPO / paths.SCALED_MODEL)]
    assert load_model.main([*model, "--ik", str(REPO / paths.IK_MOTION), "--out-model", str(d / "model.json"), "--out-kinematics", str(d / "kinematics.csv"), "--out-grf", str(d / "grf.csv")]) == 0
    out: dict[str, Table] = {}
    for method in ("qp", "analyze"):
        m = d / method
        assert so.main([*model, "--method", method, "--kinematics", str(d / "kinematics.csv"), "--out-activations", str(m / "activations.csv"), "--out-forces", str(m / "forces.csv"), "--out-settings", str(m / "static_opt.json"), "--scratch", str(m / "so")]) == 0
        out[method] = read_csv(m / "activations.csv")
    yield out


def test_qp_matches_opensim_on_the_leg_model(legs: dict[str, Table]) -> None:
    qp, ref = legs["qp"], legs["analyze"]
    assert qp.labels == ref.labels and len(qp.labels) == 81
    assert qp.time == pytest.approx(ref.time)
    worst = max((math.sqrt(sum((x - y) ** 2 for x, y in zip(qp.columns[m], ref.columns[m])) / len(qp.time)), m) for m in qp.labels[1:])
    print("largest activation RMS difference", worst)
    assert worst[0] < QP_VS_ANALYZE_RMS


def test_path_coordinates_cover_every_moment_arm() -> None:
    osim = pytest.importorskip("opensim")
    arms = REPO / paths.MOMENT_ARMS
    model_file = REPO / paths.MERGED_MODEL
    if not arms.exists() or not model_file.exists():
        pytest.skip("data/work/ comes from the pipeline (ninja)")
    model = osim.Model(str(model_file))
    state = model.initSystem()
    covered = {(m, c) for m, cs in so.path_coordinates(osim, model, state).items() for c in cs}
    free = set(so.free_coordinates(model, state))
    with arms.open() as f:
        pairs = {(r["muscle"], r["coordinate"]) for r in csv.DictReader(f)}
    spanned = {p for p in pairs if p[1] in free}
    assert len(spanned) > 1000
    assert spanned <= covered, sorted(spanned - covered)[:10]
