# -*- coding: utf-8 -*-
"""振動と ECU の値の突き合わせ（#130 の確かめ）。"""
import numpy as np
import pandas as pd
import pytest

from ct125 import ecu_report

FS = 800.0


def _accel(freqs_hz, seconds=3, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS)) / FS
    f = np.repeat(np.asarray(freqs_hz, float), int(FS))[: len(t)]
    phase = 2 * np.pi * np.cumsum(f) / FS
    return pd.DataFrame({"t_rel": t, "ax_g": 0.3 * np.sin(phase) + rng.normal(0, noise, len(t)), "ay_g": 1.0, "az_g": 0.05 * np.sin(2 * phase)})


def test_vibration_rpm_follows_the_strongest_line_in_the_band():
    acc = _accel([23.0, 50.0, 83.3], noise=0.01)   # アイドリング約 1,380 rpm → 3,000 → 5,000 rpm
    rpm = ecu_report.vibration_rpm(acc, FS, np.arange(3.0))
    assert rpm == pytest.approx([1380, 3000, 4998], abs=20)


def test_vibration_rpm_ignores_peaks_outside_the_band_and_short_windows():
    acc = _accel([5.0, 5.0], seconds=2)            # 5 Hz（300 rpm）は帯域の外。帯域の中は雑音だけ
    acc.loc[:, "az_g"] = 0.0
    rpm = ecu_report.vibration_rpm(acc, FS, np.array([0.0, 1.9]))
    assert np.isfinite(rpm[0]) and not (290 <= rpm[0] <= 310)
    assert np.isnan(rpm[1])                         # 0.1 秒しかない窓は推定しない


def test_compare_rpm_counts_matches_and_other_orders():
    ecu = np.array([3000, 3000, 3000, 3000, np.nan])
    est = np.array([3100, 1500, 6000, 4500, 3000])
    c = ecu_report.compare_rpm(est, ecu)
    assert c.n == 4
    assert (c.matched, c.half, c.double) == (0.25, 0.25, 0.25)
    assert c.median_diff_matched == 100


def test_finer_baseline_explains_rpm_driven_vibration():
    # 振動が回転数で決まる走行：速度だけの基準より、回転数の基準のほうが残りの広がりが小さい
    rng = np.random.default_rng(0)
    n = 2000
    rpm = rng.uniform(2000, 6000, n)
    speed = rng.uniform(10, 60, n)                  # 速度は回転数と関係なく動く（ギアが違う）
    w = pd.DataFrame({"speed_kmh": speed, "ecu_rpm_mean": rpm, "ecu_load_pct": rng.uniform(0, 80, n),
                      "log_rms": rpm / 1000 + rng.normal(0, 0.05, n)})
    s_speed, _ = ecu_report.spread(ecu_report.baseline_residuals(w, w, ecu_report.BASELINES["速度だけ（5 km/h）"]))
    s_rpm, cover = ecu_report.spread(ecu_report.baseline_residuals(w, w, ecu_report.BASELINES["回転数だけ（500 rpm）"]))
    assert s_rpm < s_speed / 3 and cover == 1.0


def test_sparse_bins_are_not_used():
    w = pd.DataFrame({"speed_kmh": [1.0] * 12 + [40.0], "log_rms": [0.0] * 12 + [5.0]})
    r = ecu_report.baseline_residuals(w, w, [("speed_kmh", 5.0)])
    assert np.isnan(r[-1]) and (r[:-1] == 0).all()
