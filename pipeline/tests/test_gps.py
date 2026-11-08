# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import pytest

from ct125 import clean, gps


def test_haversine_known_distance():
    # 北緯 35 度で経度差 0.01 度 ≈ 111.32 km × cos(35°) × 0.01 ≈ 912 m
    d = gps.haversine_m(35.0, 135.0, 35.0, 135.01)
    assert d == pytest.approx(111320 * np.cos(np.deg2rad(35.0)) * 0.01, rel=0.01)
    # 緯度差 1 度 ≈ 111.2 km
    assert gps.haversine_m(0.0, 0.0, 1.0, 0.0) == pytest.approx(111195, rel=0.002)
    assert gps.haversine_m(10.0, 20.0, 10.0, 20.0) == 0.0


def test_knots_to_kmh():
    assert gps.knots_to_kmh(10) == pytest.approx(18.52)
    assert gps.knots_to_kmh(np.array([0, 1])).tolist() == pytest.approx([0.0, 1.852])


def test_interpolate_to_windows_gap_and_edges():
    gv = pd.DataFrame({"t_rel": [10.0, 11.0, 12.0, 20.0, 21.0], "lat": [35.0, 35.0, 35.0, 35.1, 35.1], "lon": [135.0, 135.001, 135.002, 135.1, 135.1], "speed_kmh": [0, 10, 20, 30, 30]})
    centers = np.array([5.0, 10.5, 11.5, 15.0, 20.5, 21.5, 30.0])
    out = gps.interpolate_to_windows(gv, centers, max_gap_sec=5)
    assert out["has_gps"].tolist() == [False, True, True, False, True, True, False]
    assert out["speed_kmh"].iloc[1] == pytest.approx(5.0)        # 10 と 11 の中点
    assert out["lon"].iloc[2] == pytest.approx(135.0015)
    assert np.isnan(out["lat"].iloc[3])                          # 12→20 秒は 8 秒空くので補間しない
    assert out["lat"].iloc[5] == pytest.approx(35.1)             # 最後の fix から 0.5 秒後：最寄り値


def test_validate_gps_reasons():
    g = pd.DataFrame({
        "t_rel": [0, 1, 2, 3, 4, 5, 6],
        "status": ["V", "A", "A", "A", "A", "A", "A"],
        "lat": [np.nan, 35.0, 35.0, 35.0, 35.0, 35.0, 35.0],
        "lon": [np.nan, 135.0, 135.0001, 135.0002, 135.01, 135.0003, 135.0004],
        "sats": [0, 10, 10, 10, 10, 3, 10],
        "hdop": [25.5, 1.0, 1.0, 1.0, 1.0, 1.0, 9.0],
        "speed_kmh": [np.nan, 30.0, 30.0, 30.0, 30.0, 30.0, 30.0],
    })
    cfg = {"min_sats": 5, "max_hdop": 5.0, "max_jump_mps": 50, "max_speed_mismatch_kmh": 25}
    v = clean.validate_gps(g, cfg)
    # 0.0001 度 ≈ 9 m/s ≈ 33 km/h（RMC 30 km/h と整合）、0.01 度 ≈ 890 m/s → jump
    assert v["invalid_reason"].tolist() == ["status", "", "", "", "jump", "sats", "hdop"]
    # 速度の整合：位置はほぼ止まっているのに RMC が 30 km/h → inconsistent
    g2 = g.iloc[1:3].copy(); g2["lon"] = [135.0, 135.0]; g2["speed_kmh"] = [0.0, 30.0]
    v2 = clean.validate_gps(g2.reset_index(drop=True), cfg)
    assert v2["invalid_reason"].tolist() == ["", "inconsistent"]


def test_flag_edges():
    t = np.array([0, 30, 61, 100, 140, 170])
    assert clean.flag_edges(t, 200.0, 60).tolist() == [True, True, False, False, False, True]
