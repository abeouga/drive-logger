# -*- coding: utf-8 -*-
"""GPS の距離・速度・補間。"""
from __future__ import annotations

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6371000.0
KMH_PER_KNOT = 1.852


def knots_to_kmh(knots):
    return np.asarray(knots, dtype=float) * KMH_PER_KNOT


def haversine_m(lat1, lon1, lat2, lon2):
    """2 点間の大圏距離 [m]。引数は度（スカラーでも配列でも可）。"""
    lat1, lon1, lat2, lon2 = (np.deg2rad(np.asarray(x, dtype=float)) for x in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def haversine_speed_kmh(gps: pd.DataFrame) -> pd.Series:
    """連続する行の距離 ÷ 経過秒 [km/h]。先頭行は NaN。`t_rel`・`lat`・`lon` を使う。"""
    d = haversine_m(gps["lat"].shift(), gps["lon"].shift(), gps["lat"], gps["lon"])
    dt = gps["t_rel"].diff()
    out = pd.Series(d, index=gps.index) / dt * 3.6
    out[dt <= 0] = np.nan
    return out


def smooth_speed(speed: pd.Series, points: int = 3) -> pd.Series:
    """移動中央値（中心合わせ）。端は使える点だけで計算。"""
    if points <= 1:
        return speed
    return speed.rolling(points, center=True, min_periods=1).median()


def interpolate_to_windows(gps_valid: pd.DataFrame, t_centers: np.ndarray, max_gap_sec: float) -> pd.DataFrame:
    """窓の中心時刻（相対秒）に、直近の有効 fix を線形補間で割り当てる。

    - 前後の fix の間隔が max_gap_sec を超える区間、および最初の fix より 1 秒以上前・最後の fix より 1 秒以上後は
      補間せず has_gps=False（lat/lon/speed は NaN）。
    - gps_valid は `t_rel` で昇順、列 lat・lon・speed_kmh を持つ。
    """
    t_centers = np.asarray(t_centers, dtype=float)
    n = len(t_centers)
    out = pd.DataFrame({"lat": np.full(n, np.nan), "lon": np.full(n, np.nan), "speed_kmh": np.full(n, np.nan), "has_gps": np.zeros(n, dtype=bool)})
    if len(gps_valid) == 0:
        return out
    t = gps_valid["t_rel"].to_numpy(dtype=float)
    vals = gps_valid[["lat", "lon", "speed_kmh"]].to_numpy(dtype=float)
    idx = np.searchsorted(t, t_centers)  # t[idx-1] <= tc < t[idx]
    left = np.clip(idx - 1, 0, len(t) - 1)
    right = np.clip(idx, 0, len(t) - 1)
    inside = (idx > 0) & (idx < len(t))
    gap = t[right] - t[left]
    ok_inside = inside & (gap <= max_gap_sec)
    # 端：最寄りの fix から 1 秒以内なら最寄り値を使う
    edge = ~inside & (np.abs(t[np.clip(idx, 0, len(t) - 1)] - t_centers) <= 1.0) | (~inside & (np.abs(t[left] - t_centers) <= 1.0))
    w = np.zeros(n)
    w[ok_inside] = (t_centers[ok_inside] - t[left[ok_inside]]) / gap[ok_inside]
    interp = vals[left] * (1 - w)[:, None] + vals[right] * w[:, None]
    nearest = np.where(np.abs(t[left] - t_centers) <= np.abs(t[right] - t_centers), left, right)
    use = ok_inside | edge
    res = np.where(ok_inside[:, None], interp, vals[nearest])
    out.loc[use, ["lat", "lon", "speed_kmh"]] = res[use]
    out["has_gps"] = use & np.isfinite(res[:, 0])
    out.loc[~out["has_gps"], ["lat", "lon", "speed_kmh"]] = np.nan
    return out
