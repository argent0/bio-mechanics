"""Pure-numerics tests of pipeline stages 1–3; they run in any Python (no OpenSim, no numpy)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from pipeline.load_model import (
    CoordinateInfo,
    Table,
    butterworth2,
    central_difference,
    contact_intervals,
    grf_table,
    interp_linear,
    kinematics_table,
    read_csv,
    read_sto,
    write_csv,
    write_sto,
    zero_lag_lowpass,
)
from pipeline.static_opt import coordinates_mot


def sine(freq: float, rate: float, n: int) -> list[float]:
    return [math.sin(2 * math.pi * freq * i / rate) for i in range(n)]


def amplitude(x: list[float]) -> float:
    """Peak amplitude over the middle half, away from the ends."""
    n = len(x)
    return max(abs(v) for v in x[n // 4 : 3 * n // 4])


def test_lowpass_keeps_constant_and_slow_signals() -> None:
    assert zero_lag_lowpass([3.0] * 50, 6.0, 100.0) == pytest.approx([3.0] * 50)
    assert amplitude(zero_lag_lowpass(sine(0.5, 100.0, 400), 6.0, 100.0)) == pytest.approx(1.0, abs=1e-3)


def test_lowpass_halves_cutoff_and_removes_fast_signals() -> None:
    # One pass has gain 1/sqrt(2) at the cutoff; forward + backward gives 1/2.
    assert amplitude(zero_lag_lowpass(sine(6.0, 100.0, 1000), 6.0, 100.0)) == pytest.approx(0.5, abs=0.01)
    assert amplitude(zero_lag_lowpass(sine(30.0, 100.0, 1000), 6.0, 100.0)) < 0.02


def test_lowpass_has_zero_lag() -> None:
    x = sine(1.0, 100.0, 400)
    y = zero_lag_lowpass(x, 6.0, 100.0)
    peak_x = max(range(100, 300), key=lambda i: x[i])
    peak_y = max(range(100, 300), key=lambda i: y[i])
    assert peak_x == peak_y


def test_butterworth_dc_gain_is_one() -> None:
    b, a = butterworth2(6.0, 100.0)
    assert sum(b) / sum(a) == pytest.approx(1.0)


def test_lowpass_matches_scipy_filtfilt() -> None:
    signal = pytest.importorskip("scipy.signal")
    x = [math.sin(0.1 * i) + 0.3 * math.sin(1.7 * i) + 0.01 * i for i in range(238)]
    b, a = signal.butter(2, 6.0, fs=100.0)
    expected = list(signal.filtfilt(b, a, x, padlen=50))
    assert zero_lag_lowpass(x, 6.0, 100.0) == pytest.approx(expected, abs=1e-12)


def test_central_difference_exact_for_quadratic_on_uneven_times() -> None:
    t = [0.0, 0.1, 0.25, 0.3, 0.5, 0.55]
    x = [2 * ti * ti - ti + 1 for ti in t]
    d = central_difference(t, x)
    assert d[1:-1] == pytest.approx([4 * ti - 1 for ti in t[1:-1]])
    assert d[0] == pytest.approx((x[1] - x[0]) / 0.1)


def test_interp_linear() -> None:
    assert interp_linear([0.0, 1.0, 2.0], [0.0, 10.0, 0.0], [-1.0, 0.25, 1.0, 1.5, 3.0]) == pytest.approx([0.0, 2.5, 10.0, 5.0, 0.0])


def test_contact_intervals_threshold_and_clipping() -> None:
    t = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    fy = [30.0, 25.0, 10.0, 21.0, 500.0, 19.9, 40.0]
    assert contact_intervals(t, fy, 20.0) == [(0.0, 0.1), (0.3, 0.4), (0.6, 0.6)]
    assert contact_intervals(t, [0.0] * 7, 20.0) == []


def test_sto_and_csv_roundtrip(tmp_path: Path) -> None:
    table = Table(["time", "a", "b"], {"time": [0.0, 0.01], "a": [1.5, -2.0], "b": [3.0, 4.25]}, {})
    write_sto(tmp_path / "x.mot", table, "x", in_degrees=False)
    back = read_sto(tmp_path / "x.mot")
    assert back.labels == table.labels and back.columns == table.columns
    assert back.header["inDegrees"] == "no"
    write_csv(tmp_path / "x.csv", table.labels, table.columns)
    assert read_csv(tmp_path / "x.csv").columns == table.columns


def test_kinematics_converts_rotational_degrees_only_and_adds_speeds() -> None:
    n = 50
    t = [i / 100 for i in range(n)]
    ik = Table(
        ["time", "rot", "beta", "tx"],
        {"time": t, "rot": [90.0] * n, "beta": [1.0] * n, "tx": [0.01 * i for i in range(n)]},
        {"inDegrees": "yes"},
    )
    coords = [
        CoordinateInfo("rot", "rotational", 0.0),
        CoordinateInfo("beta", "coupled", 0.0),
        CoordinateInfo("tx", "translational", 0.0),
        CoordinateInfo("missing", "rotational", 0.5),
    ]
    kin = kinematics_table(ik, coords, 6.0)
    assert kin.labels == ["time", "rot", "beta", "tx", "missing", "rot_speed", "beta_speed", "tx_speed", "missing_speed"]
    assert kin.columns["rot"] == pytest.approx([math.pi / 2] * n)
    assert kin.columns["beta"] == pytest.approx([1.0] * n)
    assert kin.columns["missing"] == pytest.approx([0.5] * n)
    assert kin.columns["tx_speed"][5:-5] == pytest.approx([1.0] * (n - 10), abs=1e-6)
    assert coordinates_mot(kin).labels == ["time", "rot", "beta", "tx", "missing"]


def test_grf_table_renames_and_resamples() -> None:
    src = {f"ground_{k}_{s}_{a}": [0.0, 2.0] for s in "rl" for k, a in [("force", "vx"), ("force", "vy"), ("force", "vz"), ("force", "px"), ("force", "py"), ("force", "pz")]}
    src.update({f"ground_torque_{s}_{a}": [0.0, 2.0] for s in "rl" for a in "xyz"})
    grf = Table(["time", *src], {"time": [0.0, 1.0], **src}, {})
    out = grf_table(grf, [0.0, 0.5, 1.0])
    assert out.labels[:4] == ["time", "force_x_r", "force_y_r", "force_z_r"]
    assert len(out.labels) == 19
    assert out.columns["force_y_l"] == pytest.approx([0.0, 1.0, 2.0])
