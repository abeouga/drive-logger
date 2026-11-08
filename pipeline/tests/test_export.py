# -*- coding: utf-8 -*-
"""画面用の書き出し：列・null・見どころ・地図の判定。"""
import json

import numpy as np
import pandas as pd
import pytest

from ct125 import export

START = (35.0, 135.0)


def _scored(n=30, gps=True, gps_from=0):
    """START から東へ 1 秒に約 9 m ずつ離れていく走行。gps_from より前の窓は GPS なし（has_gps=False）。"""
    lat = np.full(n, START[0])
    lon = START[1] + np.arange(n) * 0.0001
    df = pd.DataFrame({
        "ride_id": "ride_t", "win": np.arange(n), "t_rel": np.arange(n) + 0.5,
        "t_abs": pd.date_range("2026-11-02 14:00", periods=n, freq="s", tz="Asia/Tokyo") if gps else pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns, Asia/Tokyo]"),
        "lat": lat if gps else np.nan, "lon": lon if gps else np.nan, "has_gps": (np.arange(n) >= gps_from) if gps else False,
        "speed_kmh": np.linspace(0, 40, n) if gps else np.nan,
        "is_edge": False, "is_clipped": False,
        "rms": np.linspace(0.1, 2.0, n), "p2p": 1.0, "crest": 2.5, "score_if": np.linspace(-0.2, 0.1, n),
        "band_1_5": 0.1, "band_5_15": 0.3, "band_15_40": 0.6,
        "is_stopped": (np.linspace(0, 40, n) < 5) if gps else False,
        "z_speed": np.linspace(-1, 2, n) if gps else np.nan, "is_anomaly_z": False, "is_anomaly_if": False,
    })
    df["log_rms"] = np.log(df["rms"] + 1e-6)
    df.loc[3, "rms"] = np.nan  # NaN が null になること
    return df


def test_windows_without_gps_have_null_coordinates():
    summary, payload = export.ride_payload(_scored(gps_from=5))
    c = payload["columns"]
    assert c["lat"][:5] == [None] * 5 and c["lon"][:5] == [None] * 5   # 補間できなかった窓は座標を出さない
    assert all(v is not None for v in c["lat"][5:])
    assert c["cls"][:5] == [-1] * 5            # 色のクラスも付けない
    assert "is_private" not in c and "n_private" not in summary


def test_json_is_strict_and_rounded(tmp_path):
    summary, payload = export.ride_payload(_scored())
    text = json.dumps(payload, allow_nan=False)  # NaN が残っていれば例外
    assert payload["columns"]["rms"][3] is None
    assert all(len(str(v).split(".")[-1]) <= 5 for v in payload["columns"]["lon"] if v is not None)
    assert set(export.WINDOW_COLUMNS) <= set(payload["columns"])
    assert {"t_abs_ms", "cls", "highlight"} <= set(payload["columns"])
    assert len(payload["columns"]["t_rel"]) == payload["n"] == 30
    assert len(summary["spark"]) == 30 and summary["gps"] in ("full", "partial", "none")


def test_no_gps_ride():
    summary, payload = export.ride_payload(_scored(gps=False))
    assert summary["gps"] == "none" and summary["start_ms"] is None and summary["max_speed_kmh"] is None
    assert payload["columns"]["t_abs_ms"] is None
    assert all(v is None for v in payload["columns"]["lat"])
    assert summary["highlight_basis"] == "score_if_top" and summary["n_highlights"] == 10


def test_highlights_fall_back_to_top_z():
    df = _scored()
    flag, basis = export.highlights(df)
    assert basis == "z_speed_top" and flag.sum() == 10
    df.loc[20, "is_anomaly_z"] = True
    flag, basis = export.highlights(df)
    assert basis == "z_speed>3" and flag.tolist().count(True) == 1


def test_gps_kind_thresholds():
    assert export.gps_kind(0.0) == "none"
    assert export.gps_kind(0.09) == "none"
    assert export.gps_kind(0.10) == "partial"
    assert export.gps_kind(0.90) == "partial"
    assert export.gps_kind(0.95) == "full"
    assert export.gps_kind(0.5, min_ratio=0.6) == "none"


def test_quintile_classes():
    cls = export.quintile_classes(pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, np.nan]))
    assert cls.tolist()[:10] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert cls[-1] == -1


def test_ride_distance_only_consecutive_windows():
    df = pd.DataFrame({
        "win": [0, 1, 2, 5],
        "has_gps": [True, True, True, True],
        "lat": [35.0, 35.0, 35.0, 35.1],
        "lon": [135.0, 135.001, 135.002, 135.1],
    })
    d = export.ride_distance_km(df)
    assert 0.17 < d < 0.19          # 0.001 度 ≈ 91 m × 2。win 2→5 の飛びは足さない


def test_sparkline_length_and_values():
    s = export.sparkline(pd.Series(np.arange(600, dtype=float)), points=60)
    assert len(s) == 60 and s[0] == pytest.approx(4.5) and s[-1] == pytest.approx(594.5)
