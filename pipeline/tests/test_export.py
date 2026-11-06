# -*- coding: utf-8 -*-
"""Web アプリ用の書き出し：自宅マスク・列・null・検査関数。"""
import json

import numpy as np
import pandas as pd
import pytest

from ct125 import export

HOME = (35.0, 135.0)


def _scored(n=30, private_first=5, gps=True):
    """自宅（HOME）から東へ 1 秒に約 9 m ずつ離れていく走行。先頭 private_first 窓を is_private にする。"""
    lat = np.full(n, HOME[0])
    lon = HOME[1] + np.arange(n) * 0.0001
    df = pd.DataFrame({
        "ride_id": "ride_t", "win": np.arange(n), "t_rel": np.arange(n) + 0.5,
        "t_abs": pd.date_range("2026-11-02 14:00", periods=n, freq="s", tz="Asia/Tokyo") if gps else pd.Series(pd.NaT, index=range(n), dtype="datetime64[ns, Asia/Tokyo]"),
        "lat": lat if gps else np.nan, "lon": lon if gps else np.nan, "has_gps": gps,
        "speed_kmh": np.linspace(0, 40, n) if gps else np.nan,
        "is_edge": False, "is_private": np.arange(n) < private_first if gps else False, "is_clipped": False,
        "rms": np.linspace(0.1, 2.0, n), "p2p": 1.0, "crest": 2.5, "score_if": np.linspace(-0.2, 0.1, n),
        "band_1_5": 0.1, "band_5_15": 0.3, "band_15_40": 0.6,
        "is_stopped": (np.linspace(0, 40, n) < 5) if gps else False,
        "z_speed": np.linspace(-1, 2, n) if gps else np.nan, "is_anomaly_z": False, "is_anomaly_if": False,
    })
    df["log_rms"] = np.log(df["rms"] + 1e-6)
    df.loc[3, "rms"] = np.nan  # NaN が null になること
    return df


def test_private_windows_have_null_coordinates():
    summary, payload = export.ride_payload(_scored(private_first=5))
    c = payload["columns"]
    assert c["lat"][:5] == [None] * 5 and c["lon"][:5] == [None] * 5
    assert all(v is not None for v in c["lat"][5:])
    assert c["is_private"][:5] == [True] * 5
    assert c["cls"][:5] == [-1] * 5            # 色のクラスも付けない
    assert summary["n_private"] == 5


def test_json_is_strict_and_rounded(tmp_path):
    summary, payload = export.ride_payload(_scored())
    text = json.dumps(payload, allow_nan=False)  # NaN が残っていれば例外
    assert payload["columns"]["rms"][3] is None
    assert all(len(str(v).split(".")[-1]) <= 5 for v in payload["columns"]["lon"] if v is not None)
    assert set(export.WINDOW_COLUMNS) <= set(payload["columns"])
    assert {"t_abs_ms", "cls", "highlight"} <= set(payload["columns"])
    assert len(payload["columns"]["t_rel"]) == payload["n"] == 30
    assert len(summary["spark"]) == 30 and summary["gps"] in ("full", "partial", "none")
    assert "home" not in text


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


def test_check_files_detects_points_near_home(tmp_path):
    _, payload = export.ride_payload(_scored(private_first=5))
    ok = tmp_path / "ride_t.json"
    ok.write_text(json.dumps(payload), encoding="utf-8")
    # 先頭 5 窓（0〜36 m）は null。残りは 45 m〜。半径 40 m なら 0 点、半径 100 m なら近い点がある
    assert export.check_files([ok], [HOME], 40)[0]["within_radius"] == 0
    assert export.check_files([ok], [HOME], 100)[0]["within_radius"] > 0
    # ビルド後の JS の形（キーに引用符なし）でも拾える
    js = tmp_path / "index.html"
    js.write_text('const d={lat:[null,35.0,35.0],lon:[null,135.0001,135.01]};', encoding="utf-8")
    r = export.check_files([js], [HOME], 50)[0]
    assert r["points"] == 2 and r["within_radius"] == 1
    # 「緯度,経度」の組の形でも拾える
    pair = tmp_path / "pair.html"
    pair.write_text("L.polyline([[35.0, 135.0002],[35.0,135.02]])", encoding="utf-8")
    assert export.check_files([pair], [HOME], 50)[0]["within_radius"] == 1


def test_sparkline_length_and_values():
    s = export.sparkline(pd.Series(np.arange(600, dtype=float)), points=60)
    assert len(s) == 60 and s[0] == pytest.approx(4.5) and s[-1] == pytest.approx(594.5)
