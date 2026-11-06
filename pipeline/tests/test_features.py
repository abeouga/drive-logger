# -*- coding: utf-8 -*-
"""既知の正弦波で RMS・ピーク・帯域比が理論値に一致することを確認する。"""
import numpy as np
import pandas as pd
import pytest

from ct125 import features

FS = 400.0


def _sine(freq, amp, n=400, fs=FS, offset=0.0):
    t = np.arange(n) / fs
    return offset + amp * np.sin(2 * np.pi * freq * t)


def test_rms_of_sine_single_axis():
    # 1 軸だけ振幅 A の正弦波（他軸は重力 1g の定数）。重力は窓内平均で消え、|a| = A|sin| → RMS = A/√2
    A = 2.0
    ax = _sine(10, A)
    ay = np.full(400, 1.0)
    az = np.zeros(400)
    f = features.window_features(ax, ay, az, FS)
    assert f["rms"] == pytest.approx(A / np.sqrt(2), rel=1e-3)
    assert f["p2p"] == pytest.approx(A, rel=1e-3)          # |a| は 0〜A
    assert f["crest"] == pytest.approx(np.sqrt(2), rel=1e-3)
    assert f["n_samples"] == 400
    assert np.isfinite(f["jerk_rms"]) and f["jerk_rms"] > 0


def test_gravity_removed():
    ax = np.zeros(400)
    ay = np.full(400, 0.96)   # 静止、重力のみ
    az = np.zeros(400)
    f = features.window_features(ax, ay, az, FS)
    assert f["rms"] == pytest.approx(0.0, abs=1e-9)
    assert f["p2p"] == pytest.approx(0.0, abs=1e-9)


def test_band_ratio_concentrates_in_right_band():
    bands = {"band_1_5": (1, 5), "band_5_15": (5, 15), "band_15_40": (15, 40)}
    ax = _sine(10, 1.0)
    f = features.window_features(ax, np.zeros(400), np.zeros(400), FS, bands)
    assert f["band_5_15"] > 0.95
    assert f["band_1_5"] + f["band_5_15"] + f["band_15_40"] == pytest.approx(1.0, abs=1e-6)
    # 24 Hz（アイドリング相当）が 2 倍の 48 Hz に写らず 15〜40 Hz 帯に入ること
    f2 = features.window_features(_sine(24, 1.0), np.zeros(400), np.zeros(400), FS, bands)
    assert f2["band_15_40"] > 0.95


def test_compute_windows_splits_by_second():
    n = int(FS * 3.5)
    t = np.arange(n) / FS
    acc = pd.DataFrame({"t_rel": t, "ax_g": _sine(10, 1.0, n), "ay_g": 1.0, "az_g": 0.0, "is_clipped": False})
    w = features.compute_windows(acc, FS, 1.0, None)
    assert list(w["win"]) == [0, 1, 2, 3]            # 末尾 0.5 秒の窓は期待数の半分ちょうどで残る
    assert w["t_rel"].iloc[0] == pytest.approx(0.5)
    assert (w["n_samples"].iloc[:3] == 400).all()
    assert w["rms"].iloc[0] == pytest.approx(1 / np.sqrt(2), rel=1e-3)
