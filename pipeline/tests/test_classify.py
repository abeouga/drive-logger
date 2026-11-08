# -*- coding: utf-8 -*-
"""走行の分類（classify.py）。しきい値は config/default.yaml の classify。"""
import numpy as np
import pandas as pd
import pytest

from ct125 import classify
from ct125.config import load_config

CFG = load_config()


def _windows(n=200, rms=0.3, gps=True, moved_m=0.0, speed=0.0):
    lon = 135.0 + np.linspace(0, moved_m, n) / (111320 * np.cos(np.deg2rad(35.0)))
    return pd.DataFrame({
        "rms": np.full(n, rms),
        "has_gps": np.full(n, gps),
        "lat": np.full(n, 35.0) if gps else np.nan,
        "lon": lon if gps else np.nan,
        "speed_kmh": np.full(n, speed) if gps else np.nan,
    })


@pytest.mark.parametrize(
    "windows, kind",
    [
        (_windows(rms=0.015), "desk"),                                   # エンジンの振動が無い
        (_windows(rms=0.13, moved_m=19, speed=1.0), "idle"),            # その場でアイドリング
        (_windows(rms=0.4, moved_m=2300, speed=30.0), "ride"),          # 走った
        (_windows(rms=0.9, gps=False), "ride_nogps"),                   # GPS が無い
        (_windows(n=40, rms=0.13), "ride_nogps"),                       # GPS の窓が少なすぎて止まっていたか分からない
        (_windows(rms=0.4, moved_m=500, speed=3.0), "ride_nogps"),      # 動いたが、走っていた窓が少ない
    ],
)
def test_kinds(windows, kind):
    assert classify.classify(windows, CFG)[0] == kind


def test_metrics_are_reasons():
    kind, m = classify.classify(_windows(rms=0.13, moved_m=19, speed=6.0), CFG)
    assert m == {"vib_median_g": 0.13, "gps_windows": 200, "max_dist_m": pytest.approx(19, abs=0.5), "moving_windows": 200}
    assert classify.metrics(_windows(gps=False), 5.0)["max_dist_m"] is None


def test_training_and_screen_rules():
    assert classify.used_for_training("idle", False, CFG) == (True, None)
    assert classify.used_for_training("ride", True, CFG) == (False, "deleted")
    assert classify.used_for_training("desk", False, CFG) == (False, "desk")
    assert classify.used_for_training("ride_nogps", False, CFG) == (False, "ride_nogps")
    assert classify.used_for_training(None, False, CFG) == (False, "unclassified")
    assert classify.shown_on_screen("ride_nogps", False, CFG) and not classify.shown_on_screen("desk", False, CFG)
    assert not classify.shown_on_screen("ride", True, CFG)
