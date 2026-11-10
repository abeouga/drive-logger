# -*- coding: utf-8 -*-
"""画面用の書き出し：列・null・いつもと違う振動・地図の判定。"""
import json

import numpy as np
import pandas as pd
import pytest

from ct125 import export, model

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
    assert {"t_abs_ms", "cls", "anomaly", "anomaly_score"} <= set(payload["columns"])
    assert len(payload["columns"]["t_rel"]) == payload["n"] == 30
    assert len(summary["spark"]) == 30 and summary["gps"] in ("full", "partial", "none")


def test_no_gps_ride():
    summary, payload = export.ride_payload(_scored(gps=False))
    assert summary["gps"] == "none" and summary["start_ms"] is None and summary["max_speed_kmh"] is None
    assert payload["columns"]["t_abs_ms"] is None
    assert all(v is None for v in payload["columns"]["lat"])
    # GPS なしの走行は判定しない（Isolation Forest の上位で埋めない）
    assert summary["anomaly_method"] == "none" and summary["n_anomalies"] == 0
    assert payload["anomaly"] == {"method": "none", "threshold": None, "model_version": None}
    assert not any(payload["columns"]["anomaly"]) and all(v is None for v in payload["columns"]["anomaly_score"])


def test_no_anomaly_stays_zero():
    """しきい値を超えた所が無ければ 0 件のまま（上位 N 件で埋めない）。"""
    summary, payload = export.ride_payload(_scored(), model_version="20261108-180231", rule=model.AnomalyRule("speed_baseline", 3.0))
    assert summary["anomaly_method"] == "speed_baseline" and summary["n_anomalies"] == 0
    assert payload["anomaly"] == {"method": "speed_baseline", "threshold": 3.0, "model_version": "20261108-180231"}
    assert not any(payload["columns"]["anomaly"])
    assert payload["columns"]["anomaly_score"] == payload["columns"]["z"]  # 判定に使ったスコア＝z_speed


def test_anomaly_follows_model_judgement():
    df = _scored()
    df.loc[20, ["z_speed", "is_anomaly_z"]] = [3.5, True]
    summary, payload = export.ride_payload(df)
    assert summary["n_anomalies"] == 1
    assert [i for i, f in enumerate(payload["columns"]["anomaly"]) if f] == [20]
    assert payload["columns"]["anomaly_score"][20] == 3.5


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


def _accel_for(n_windows: int, fs: float = 40.0) -> pd.DataFrame:
    t = np.arange(int(n_windows * fs)) / fs
    return pd.DataFrame({"t_rel": t, "ax_g": 0.1 * np.sin(2 * np.pi * 8 * t), "ay_g": 1.0, "az_g": 0.0})


def test_waveforms_of_every_window_are_split_per_minute():
    df = _scored(n=130)
    df["t_start"] = df["t_rel"] - 0.5
    _, files = export.ride_files(df, _accel_for(130))
    waves = sorted(name for name in files if name.startswith("wave_"))
    assert waves == ["wave_ride_t_000.json", "wave_ride_t_001.json", "wave_ride_t_002.json"]
    seen = []
    for k, name in enumerate(waves):
        doc = json.loads(files[name])
        assert doc["chunk"] == k
        assert all(60 * k <= w["i"] < 60 * (k + 1) for w in doc["windows"])
        seen += [w["i"] for w in doc["windows"]]
    assert seen == list(range(130))  # 基準を超えた振動が 0 件でも、全部の窓


def test_ride_output_files_finds_every_minute_and_the_old_single_file():
    names = ["rides.json", "ride_ride_t.json", "spec_ride_t.png", "spec_ride_t.json", "wave_ride_t.json",
             "wave_ride_t_000.json", "wave_ride_t_012.json", "wave_ride_t2_000.json", "ride_ride_t2.json"]
    assert export.ride_output_files("ride_t", names) == names[1:7]


def test_speed_iforest_rule_is_written_with_its_threshold():
    df = _scored()
    df["is_anomaly_sif"] = False
    df.loc[25, "is_anomaly_sif"] = True
    summary, payload = export.ride_payload(df, model_version="20261111-000000", rule=model.AnomalyRule("speed_iforest", 0.07812345))
    assert summary["anomaly_method"] == "speed_iforest" and summary["n_anomalies"] == 1
    assert payload["anomaly"] == {"method": "speed_iforest", "threshold": 0.0781, "model_version": "20261111-000000"}
    assert [i for i, f in enumerate(payload["columns"]["anomaly"]) if f] == [25]
    assert payload["columns"]["anomaly_score"] == payload["columns"]["score_if"]  # 判定に使ったスコア＝score_if


def test_no_gps_ride_is_not_judged_with_speed_iforest():
    df = _scored(gps=False)
    df["is_anomaly_sif"] = False
    summary, payload = export.ride_payload(df, rule=model.AnomalyRule("speed_iforest", 0.08))
    assert summary["anomaly_method"] == "none" and payload["anomaly"]["threshold"] is None
