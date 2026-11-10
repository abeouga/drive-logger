# -*- coding: utf-8 -*-
"""判定の確かめ（1 走行ずつ抜いて学習し、抜いた走行に点数を付ける）。"""
import numpy as np
import pandas as pd

from ct125 import evaluate, model


def _ride(ride_id: str, n=300, seed=0, bump_at=None):
    rng = np.random.default_rng(seed)
    speed = rng.uniform(5, 50, n)
    frame = pd.DataFrame({"ride_id": ride_id, "t_rel": np.arange(n) + 0.5, "speed_kmh": speed, "has_gps": True, "is_edge": False, "is_clipped": False})
    frame["log_rms"] = -2 + speed / 20 + rng.normal(0, 0.1, n)
    frame["rms"] = np.exp(frame["log_rms"])
    for name in model.VIBRATION_FEATURES:
        if name != "log_rms":
            frame[name] = frame["log_rms"] * 0.5 + rng.normal(0, 0.1, n)
    if bump_at is not None:  # 段差の 1 秒（ふだんよりずっと大きい）
        frame.loc[bump_at, model.VIBRATION_FEATURES] += 3.0
        frame.loc[bump_at, "rms"] = np.exp(frame.loc[bump_at, "log_rms"])
    return frame


def test_leave_one_ride_out_scores_each_held_out_ride():
    windows = {"a": _ride("a", seed=0), "b": _ride("b", seed=1, bump_at=100), "c": _ride("c", seed=2)}
    mcfg = {"anomaly_method": "speed_iforest", "anomaly_quantile": 0.99, "n_estimators": 100, "random_state": 0}
    result = evaluate.leave_one_ride_out(windows, mcfg, top_n=5)
    assert result.method == "speed_iforest"
    assert result.rides["ride_id"].tolist() == ["a", "b", "c"]
    assert (result.rides["n_windows"] == 300).all()
    top = result.top.iloc[0]
    assert top["ride_id"] == "b" and top["t_rel"] == 100.5 and bool(top["judged"])   # 段差の 1 秒が一番上
    assert len(result.top) == 5
    text = evaluate.format_evaluation(result)
    assert "speed_iforest" in text and "| 1 | b | 100.5 |" in text


def test_leave_one_ride_out_needs_two_rides():
    import pytest

    with pytest.raises(ValueError, match="2 本以上"):
        evaluate.leave_one_ride_out({"a": _ride("a")}, {})
