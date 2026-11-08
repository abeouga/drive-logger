# -*- coding: utf-8 -*-
"""走行の分類（docs/data_flow_design.md 9.、#3 の決定）。振動と GPS から自動で決める。

| 分類       | 条件（上から順に判定）                                              | 画面   | 学習   |
|------------|---------------------------------------------------------------------|--------|--------|
| desk       | 振動の中央値が desk_vib_median_g 未満（エンジンの振動が無い）       | 出さない | 使わない |
| ride       | GPS で始点から move_dist_m 以上動き、止まる速さ以上の窓が min_moving_windows 以上 | 出す | 使う |
| idle       | GPS のある窓が min_gps_windows 以上で、始点から move_dist_m 動いていない | 出す | 使う |
| ride_nogps | どれにも当たらない（GPS が足りなくて動いたか分からない、など）       | 出す   | 使わない |

しきい値は config/default.yaml の classify。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .gps import haversine_m

KINDS = ("desk", "idle", "ride", "ride_nogps")


def metrics(windows: pd.DataFrame, stop_speed_kmh: float) -> dict:
    """分類の理由になる数値（run.json と台帳に残す）。"""
    gps = windows[windows["has_gps"].fillna(False).astype(bool)]
    if len(gps):
        dist = haversine_m(gps["lat"].iloc[0], gps["lon"].iloc[0], gps["lat"], gps["lon"])
        max_dist = float(np.nanmax(dist))
        max_dist_m = round(max_dist, 1) if math.isfinite(max_dist) else None
    else:
        max_dist_m = None
    moving = int((gps["speed_kmh"] >= stop_speed_kmh).sum()) if len(gps) else 0
    vib = float(windows["rms"].median()) if len(windows) else 0.0
    return {"vib_median_g": round(vib, 4), "gps_windows": int(len(gps)), "max_dist_m": max_dist_m, "moving_windows": moving}


def kind_of(m: dict, ccfg: dict) -> str:
    if m["vib_median_g"] < ccfg["desk_vib_median_g"]:
        return "desk"
    moved = m["max_dist_m"] is not None and m["max_dist_m"] >= ccfg["move_dist_m"]
    if moved and m["moving_windows"] >= ccfg["min_moving_windows"]:
        return "ride"
    if m["gps_windows"] >= ccfg["min_gps_windows"] and not moved:
        return "idle"
    return "ride_nogps"


def classify(windows: pd.DataFrame, cfg: dict) -> tuple[str, dict]:
    """(分類, 理由の数値)。"""
    m = metrics(windows, cfg.get("stop_speed_kmh", 5.0))
    return kind_of(m, cfg["classify"]), m


def used_for_training(kind: str | None, deleted: bool, cfg: dict) -> tuple[bool, str | None]:
    """学習に使うか、使わないならその理由（model.json の excluded）。"""
    if deleted:
        return False, "deleted"
    if kind is None:
        return False, "unclassified"
    if kind not in cfg["classify"]["train_kinds"]:
        return False, kind
    return True, None


def shown_on_screen(kind: str | None, deleted: bool, cfg: dict) -> bool:
    """画面に出すか（消した走行と、机上の走行は出さない）。"""
    return not deleted and kind is not None and kind not in cfg["classify"]["hidden_kinds"]
