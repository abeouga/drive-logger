# -*- coding: utf-8 -*-
"""欠損・外れ値・重複の処理と GPS の妥当性チェック（計画書フェーズ 1-2、docs/data_schema.md 5.）。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .gps import haversine_m


def clean_accel(acc: pd.DataFrame, clip_g: float) -> pd.DataFrame:
    """重複 t_us を落とし（先に出た行を残す）、レンジ上限付近のサンプルに is_clipped を付ける。"""
    out = acc.drop_duplicates(subset="t_us", keep="first").reset_index(drop=True)
    out["is_clipped"] = (out[["ax_g", "ay_g", "az_g"]].abs() >= clip_g).any(axis=1)
    return out


def validate_gps(gps: pd.DataFrame, gcfg: dict) -> pd.DataFrame:
    """各行に `valid`（bool）と `invalid_reason`（str、有効なら空）を付ける。

    無効にする条件（順に判定、最初に当たった理由を記録）：
      status      : RMC の status が A でない
      latlon      : 緯度経度が欠損・0・範囲外
      sats        : 衛星数 < min_sats
      hdop        : HDOP > max_hdop
      speed_cap   : speed_kmh > max_speed_kmh（設定があるときだけ）
      jump        : 直前の有効 fix から 1 秒あたり max_jump_mps [m] を超えて飛ぶ
      inconsistent: RMC の速度と、直前の有効 fix からの距離で求めた速度の差が max_speed_mismatch_kmh を超える
    """
    g = gps.copy()
    reason = pd.Series("", index=g.index, dtype=object)

    def mark(cond, name):
        cond = cond & (reason == "")
        reason[cond] = name

    mark(g["status"] != "A", "status")
    bad_ll = g["lat"].isna() | g["lon"].isna() | (g["lat"] == 0) | (g["lon"] == 0) | (g["lat"].abs() > 90) | (g["lon"].abs() > 180)
    mark(bad_ll, "latlon")
    mark(g["sats"].fillna(0) < gcfg.get("min_sats", 0), "sats")
    mark(g["hdop"].fillna(np.inf) > gcfg.get("max_hdop", np.inf), "hdop")
    cap = gcfg.get("max_speed_kmh")
    if cap is not None:
        mark(g["speed_kmh"].fillna(0) > cap, "speed_cap")

    # 飛びと速度の整合は「直前の有効 fix」との比較なので逐次に見る
    max_jump = gcfg.get("max_jump_mps", np.inf)
    max_mismatch = gcfg.get("max_speed_mismatch_kmh", np.inf)
    lat = g["lat"].to_numpy(float)
    lon = g["lon"].to_numpy(float)
    t = g["t_rel"].to_numpy(float)
    spd = g["speed_kmh"].to_numpy(float)
    r = reason.to_numpy(dtype=object).copy()  # pandas の copy-on-write で読み取り専用になるため複製する
    prev = -1
    for i in range(len(g)):
        if r[i] != "":
            continue
        if prev >= 0:
            dt = t[i] - t[prev]
            if dt > 0 and dt <= 2.0:  # 隣接する fix だけ比べる（長い欠損の後は比べない）
                d = float(haversine_m(lat[prev], lon[prev], lat[i], lon[i]))
                v_kmh = d / dt * 3.6
                if d / dt > max_jump:
                    r[i] = "jump"
                    continue
                if np.isfinite(spd[i]) and abs(v_kmh - spd[i]) > max_mismatch:
                    r[i] = "inconsistent"
                    continue
        prev = i
    g["invalid_reason"] = r
    g["valid"] = g["invalid_reason"] == ""
    return g


def flag_edges(t_rel: np.ndarray | pd.Series, duration_s: float, edge_sec: float) -> np.ndarray:
    """走行の先頭・末尾 edge_sec 秒を True にする。"""
    t = np.asarray(t_rel, dtype=float)
    return (t < edge_sec) | (t > duration_s - edge_sec)
