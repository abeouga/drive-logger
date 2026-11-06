# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd

from ct125 import viz


def test_map_mode_thresholds():
    assert viz.map_mode(0.0) == "none"
    assert viz.map_mode(0.09) == "none"
    assert viz.map_mode(0.10) == "partial"
    assert viz.map_mode(0.90) == "partial"
    assert viz.map_mode(0.95) == "full"
    assert viz.map_mode(0.5, min_ratio=0.6) == "none"


def test_quintile_classes():
    cls = viz.quintile_classes(pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, np.nan]))
    assert cls.tolist()[:10] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert cls[-1] == -1


def test_ride_distance_only_consecutive_windows():
    df = pd.DataFrame({
        "win": [0, 1, 2, 5],
        "has_gps": [True, True, True, True],
        "lat": [35.0, 35.0, 35.0, 35.1],
        "lon": [135.0, 135.001, 135.002, 135.1],
    })
    d = viz.ride_distance_km(df)
    assert 0.17 < d < 0.19          # 0.001 度 ≈ 91 m × 2。win 2→5 の飛びは足さない
