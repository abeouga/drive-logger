# -*- coding: utf-8 -*-
"""ECU の値を 1 秒窓にそろえる（#130）。"""
import numpy as np
import pandas as pd
import pytest

from ct125 import ecu, io, processing
from ct125.config import load_config
from ct125.model import apply_models, fit_models

from sd_sessions import session_files


def _ecu(rows):
    frame = pd.DataFrame(rows, columns=["t_rel", "pid", "value"])
    frame["value"] = frame["value"].astype(float)
    return frame


def test_rpm_is_averaged_and_held_for_a_short_gap():
    rows = [(0.1, "0C", 1500), (0.5, "0C", 1700), (0.9, "0C", 1600),   # 窓 0：3 個
            (1.2, "0C", 2000),                                          # 窓 1：1 個
            # 窓 2・3 は値なし。窓 2 は 1.2 秒の値から 0.8 秒、窓 3 は 1.8 秒なので埋める。窓 4 は 2.8 秒で埋めない
            ]
    cols = ecu.window_columns(_ecu(rows), np.arange(5.0), 1.0)
    assert cols["ecu_rpm_mean"].iloc[0] == pytest.approx(1600)
    assert (cols["ecu_rpm_min"].iloc[0], cols["ecu_rpm_max"].iloc[0]) == (1500, 1700)
    assert list(cols["ecu_rpm_mean"].iloc[1:4]) == [2000, 2000, 2000]
    assert np.isnan(cols["ecu_rpm_mean"].iloc[4])
    assert list(cols["has_ecu"]) == [True, True, True, True, False]


def test_slow_items_are_held_longer_than_fast_items():
    rows = [(0.2, "0C", 1500), (0.3, "11", 15.0), (0.4, "5C", 90.0), (9.5, "0C", 1600)]
    cols = ecu.window_columns(_ecu(rows), np.arange(10.0), 1.0)
    throttle = cols["ecu_throttle_pct"].to_numpy()
    oil = cols["ecu_oil_temp_c"].to_numpy()
    assert throttle[0] == 15.0 and throttle[3] == 15.0      # 2.7 秒前の値までは埋める（上限 3 秒）
    assert np.isnan(throttle[4])                             # 3.7 秒前は古すぎる
    assert (oil == 90.0).all()                               # 油温は 10 秒ごとにしか読まないので 15 秒まで埋める
    assert not cols["has_ecu"].iloc[5] and cols["has_ecu"].iloc[9]


def test_unreadable_values_are_skipped():
    rows = [(0.1, "0C", np.nan), (0.2, "0C", 1800), (0.3, "04", np.nan)]
    cols = ecu.window_columns(_ecu(rows), np.array([0.0]), 1.0)
    assert cols["ecu_rpm_mean"].iloc[0] == 1800
    assert np.isnan(cols["ecu_load_pct"].iloc[0])


def test_ride_without_ecu_has_empty_columns():
    cols = ecu.window_columns(None, np.arange(3.0), 1.0)
    assert list(cols.columns) == ecu.ECU_COLUMNS
    assert not cols["has_ecu"].any()
    assert cols.drop(columns="has_ecu").isna().all().all()


def _write_ride(folder, with_ecu: bool):
    folder.mkdir(parents=True)
    for name, data in session_files("ride", seconds=240).items():
        (folder / name).write_bytes(data)
    if with_ecu:
        t0_us = 1_000_000
        lines = ["t_us,pid,value,raw"]
        for i in range(int(240 / 0.36)):
            lines.append(f"{t0_us + int(i * 360_000)},0C,{3000 + i % 7 * 10},41 0C 00 00")
            if i % 4 == 0:
                lines.append(f"{t0_us + int(i * 360_000) + 1000},11,20.0,41 11 33")
        (folder / "ecu.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_ecu_columns_do_not_change_vibration_features_or_scores(tmp_path):
    cfg = load_config()
    _write_ride(tmp_path / "with" / "ride_001", with_ecu=True)
    _write_ride(tmp_path / "without" / "ride_001", with_ecu=False)
    with_ecu = processing.preprocess(io.load_ride("ride_001", tmp_path / "with"), cfg).windows
    without = processing.preprocess(io.load_ride("ride_001", tmp_path / "without"), cfg).windows

    assert with_ecu["has_ecu"].mean() > 0.95 and not without["has_ecu"].any()
    assert with_ecu["ecu_rpm_mean"].between(3000, 3060).all()
    others = [c for c in without.columns if c not in ecu.ECU_COLUMNS]
    pd.testing.assert_frame_equal(with_ecu[others], without[others])

    # 異常のスコアは ECU の列を使わないので、ECU のある走行も無い走行も同じ点数になる（今までと同じ結果）
    baseline, forest, info = fit_models(without, cfg["model"])
    scored_with = apply_models(with_ecu, baseline, forest, cfg["model"], cfg["stop_speed_kmh"], info)
    scored_without = apply_models(without, baseline, forest, cfg["model"], cfg["stop_speed_kmh"], info)
    score_cols = ["z_speed", "is_anomaly_z", "score_if", "is_anomaly_if", "is_anomaly_sif"]
    pd.testing.assert_frame_equal(scored_with[score_cols], scored_without[score_cols])
