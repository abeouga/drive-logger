# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import pytest

from ct125 import model


def _windows(n_per_bin=50, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for b, med in [(0, -2.0), (1, -1.0), (2, 0.0)]:        # 0-5, 5-10, 10-15 km/h で log_rms の中央値が上がる
        spd = rng.uniform(b * 5, b * 5 + 5, n_per_bin)
        x = med + rng.normal(0, 0.1, n_per_bin)
        rows.append(pd.DataFrame({"speed_kmh": spd, "log_rms": x, "has_gps": True}))
    return pd.concat(rows, ignore_index=True)


def test_speed_baseline_medians_and_z():
    df = _windows()
    bl = model.fit_speed_baseline(df, bin_kmh=5.0, min_count=10)
    meds = [b["median"] for b in bl["bins"]]
    assert meds == pytest.approx([-2.0, -1.0, 0.0], abs=0.05)
    # 速度 7 km/h で log_rms が中央値ちょうどなら z≈0、中央値＋大きな正ならビン幅に応じて z が大きい
    q = pd.DataFrame({"speed_kmh": [7.0, 7.0, np.nan], "log_rms": [-1.0, 1.0, 0.0]})
    z = model.apply_speed_baseline(q, bl)
    assert abs(z.iloc[0]) < 0.5
    assert z.iloc[1] > 3
    assert np.isnan(z.iloc[2])          # 速度がない窓は NaN


def test_speed_baseline_sparse_bin_borrows_neighbor():
    df = _windows()
    # 15-20 km/h に 2 窓だけ足す → min_count 未満なので最寄り（10-15）の値を借りる
    extra = pd.DataFrame({"speed_kmh": [17.0, 18.0], "log_rms": [5.0, 5.0], "has_gps": True})
    bl = model.fit_speed_baseline(pd.concat([df, extra], ignore_index=True), 5.0, 10)
    b3 = bl["bins"][3]
    assert b3["n"] == 2 and b3["source_bin"] == 2 and b3["median"] == pytest.approx(0.0, abs=0.05)


def test_isolation_forest_flags_outlier():
    rng = np.random.default_rng(1)
    n = 500
    df = pd.DataFrame({c: rng.normal(0, 1, n) for c in model.IF_FEATURES})
    df.loc[0, model.IF_FEATURES] = 8.0      # 明らかな外れ値
    forest = model.fit_isolation_forest(df, contamination=0.03, n_estimators=100)
    s = model.apply_isolation_forest(df, forest)
    assert s["score_if"].iloc[0] == s["score_if"].max()
    assert bool(s["is_anomaly_if"].iloc[0])
    assert 0.0 < s["is_anomaly_if"].mean() < 0.1
