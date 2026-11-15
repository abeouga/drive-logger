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


# ------------------------------------------------------------------ 800 Hz の走行（#112）
def _acc(fs, seconds, comps, gap_at=None):
    n = int(fs * seconds)
    t = np.arange(n) / fs
    if gap_at is not None:
        t = np.where(t >= gap_at, t + 2.0, t)   # gap_at 秒で 2 秒途切れる
    ax = sum(a * np.sin(2 * np.pi * f * t) for f, a in comps)
    return pd.DataFrame({"t_rel": t, "ax_g": ax, "ay_g": 1.0, "az_g": 0.0, "is_clipped": False})


def test_400hz_is_not_decimated():
    acc = _acc(398.5, 2, [(10, 1.0)])
    out, fs = features.for_features(acc, 398.5)
    assert out is acc and fs == 398.5


def test_800hz_features_match_400hz():
    # 200 Hz より下だけの振動なら、800 Hz で記録しても 400 Hz と同じ特徴量になる
    comps = [(24, 0.5), (90, 0.2)]
    w4 = features.compute_windows(_acc(400.0, 4, comps), 400.0, 1.0, None)
    a8, fs8 = features.for_features(_acc(800.0, 4, comps), 800.0)
    assert fs8 == 400.0
    w8 = features.compute_windows(a8, fs8, 1.0, None)
    assert list(w8["n_samples"]) == list(w4["n_samples"])
    mid = slice(1, 3)   # 走行の端（フィルターの端の影響）を除く
    for col in ("rms", "std", "p2p"):
        assert np.allclose(w8[col].iloc[mid], w4[col].iloc[mid], rtol=0.02), col


def test_800hz_drops_above_200hz():
    # 300 Hz の振動は特徴量に入らない（400 Hz の走行では記録されない帯域のため）
    a8, fs8 = features.for_features(_acc(800.0, 4, [(300, 1.0)]), 800.0)
    w8 = features.compute_windows(a8, fs8, 1.0, None)
    assert (w8["rms"].iloc[1:3] < 0.01).all()


def test_800hz_does_not_filter_across_gaps():
    a8, _ = features.for_features(_acc(800.0, 4, [(24, 0.5)], gap_at=2.0), 800.0)
    t = a8["t_rel"].to_numpy()
    assert np.diff(t).max() > 1.9                 # 途切れはそのまま残る
    assert np.all(np.diff(t) > 0)


def test_800hz_clipped_flag_survives():
    acc = _acc(800.0, 2, [(24, 0.5)])
    acc.loc[801, "is_clipped"] = True              # 間引くと消える添字（奇数）でも残ること
    a8, _ = features.for_features(acc, 800.0)
    assert a8["is_clipped"].sum() == 1
