# -*- coding: utf-8 -*-
"""前処理の本体（ファイルを読み書きしない）。処理の流れ（flow.py）から使う。

preprocess：SD の 1 回の記録（io.Ride）→ クリーニング → 1 秒窓の特徴量＋GPS 結合
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import clean, features, gps as gpsmod, io

WINDOW_COLS_FRONT = ["ride_id", "win", "t_rel", "t_abs", "lat", "lon", "has_gps", "speed_kmh", "is_edge", "is_clipped"]
ACCEL_EXPORT_COLS = ["t_rel", "ax_g", "ay_g", "az_g"]  # 書き出し（スペクトログラム・生波形）に使う加速度の列


@dataclass(frozen=True)
class Preprocessed:
    """1 走行の前処理の結果。"""

    ride_id: str
    windows: pd.DataFrame  # 1 秒窓の特徴量＋GPS（1 行＝1 窓）
    accel: pd.DataFrame    # クリーニング後の加速度（t_rel と 3 軸）
    gps: pd.DataFrame      # 妥当性を付けた GPS（valid・invalid_reason）
    memo: str
    fs: float
    duration_s: float
    has_abs_time: bool


def preprocess(ride: io.Ride, cfg: dict) -> Preprocessed:
    gcfg = cfg.get("gps", {})
    acc = clean.clean_accel(ride.acc, cfg["clip_g"])
    facc, ffs = features.for_features(acc, ride.fs)   # 800 Hz の走行は 400 Hz に間引いて特徴量を計算する
    win = features.compute_windows(facc, ffs, cfg["window_sec"], cfg.get("bands_hz"))

    gps = clean.validate_gps(ride.gps, gcfg)
    gv = gps[gps["valid"]].sort_values("t_rel").copy()
    if len(gv):
        if gv["speed_kmh"].isna().all():
            gv["speed_kmh"] = gpsmod.haversine_speed_kmh(gv)
        gv["speed_kmh"] = gpsmod.smooth_speed(gv["speed_kmh"], gcfg.get("speed_smooth_points", 3))
    joined = gpsmod.interpolate_to_windows(gv, win["t_rel"].to_numpy(), gcfg.get("max_gap_sec", 5))

    out = win.copy()
    out.insert(0, "ride_id", ride.ride_id)
    # Series のまま代入して tz 付き datetime 型を保つ（to_numpy() だと NaT だけの走行が object 型になり parquet で null 型になる）
    out["t_abs"] = io.to_jst(out["t_rel"].to_numpy(), ride.t0_us, ride.offset_s).set_axis(out.index)
    out["lat"] = joined["lat"].to_numpy()
    out["lon"] = joined["lon"].to_numpy()
    out["has_gps"] = joined["has_gps"].to_numpy()
    out["speed_kmh"] = joined["speed_kmh"].to_numpy()
    out["is_edge"] = clean.flag_edges(out["t_rel"], ride.duration_s(), cfg["edge_sec"])
    out["is_clipped"] = out["n_clipped"] > 0
    out = out[WINDOW_COLS_FRONT + [c for c in out.columns if c not in WINDOW_COLS_FRONT]]
    return Preprocessed(ride.ride_id, out, acc[ACCEL_EXPORT_COLS].copy(), gps, ride.memo, ride.fs, ride.duration_s(), ride.has_abs_time)


def describe(pre: Preprocessed) -> str:
    """1 行の要約（ログ用）。"""
    gps = pre.gps
    fix_ratio = float(gps["valid"].mean()) if len(gps) else 0.0
    reasons = gps.loc[~gps["valid"], "invalid_reason"].value_counts().to_dict()
    w = pre.windows
    return (
        f"{pre.ride_id}: {pre.duration_s / 60:.1f} 分, fs={pre.fs:.1f} Hz, 窓 {len(w)}, has_gps {w['has_gps'].mean():.2f}, "
        f"GPS 有効 {fix_ratio:.2f}（無効の理由 {reasons}）, 振り切れ窓 {int(w['is_clipped'].sum())}, 絶対時刻 {'あり' if pre.has_abs_time else 'なし'}"
    )
