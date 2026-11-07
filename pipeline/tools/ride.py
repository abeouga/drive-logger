# -*- coding: utf-8 -*-
"""ノートブック用：1セッション（ride_NNN）を読み込んで日本時間を付ける（データ仕様.md v2 の形式用）。

    from ride import load
    r = load("data/raw/ride_004")
    r.acc   # n, t_us, ax_g, ay_g, az_g, t_s（起動からの秒）, jst, mag_g
    r.gps   # gps.csv ＋ t_s, jst（有効行のみ status=A のものは r.gps_valid）
    r.fs    # 実測サンプリング周波数 [Hz]
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

JST = pd.Timedelta(hours=9)


@dataclass
class Ride:
    name: str
    acc: pd.DataFrame
    gps: pd.DataFrame
    gps_valid: pd.DataFrame
    events: pd.DataFrame
    status: pd.DataFrame
    memo: str
    fs: float
    offset_s: float | None  # UTC秒 − ESP秒（日付込みのUNIX秒）


def _gps_unix(g):
    # date=ddmmyy, utc=hhmmss.sss → UNIX秒
    d = pd.to_datetime(g["date"].astype(str).str.zfill(6), format="%d%m%y", utc=True)
    u = g["utc"].astype(float)
    sec = (u // 10000) * 3600 + (u // 100 % 100) * 60 + u % 100
    return (d - pd.Timestamp(0, tz="UTC")).dt.total_seconds() + sec


def load(d):
    d = Path(d)
    acc = pd.read_csv(d / "accel.csv")
    gps = pd.read_csv(d / "gps.csv", dtype={"utc": str, "date": str})
    events = pd.read_csv(d / "events.csv")
    status = pd.read_csv(d / "status.csv")
    memo = "".join(p.read_text(encoding="utf-8").strip() for p in d.glob("*.txt"))

    acc["t_s"] = acc["t_us"] / 1e6
    acc["mag_g"] = np.sqrt(acc.ax_g**2 + acc.ay_g**2 + acc.az_g**2)
    gps["t_s"] = gps["t_rx_us"] / 1e6
    gv = gps[gps["status"] == "A"].copy()

    offset = None
    if len(gv):
        # 時刻の対応（データ仕様.md 第2章）：offset = 中央値(UTC − t_rx)
        offset = float(np.median(_gps_unix(gv) - gv["t_s"]))
        for df in (acc, gps, events):
            t = df["t_s"] if "t_s" in df else df["t_us"] / 1e6
            df["jst"] = pd.to_datetime(t + offset, unit="s", utc=True).dt.tz_convert("Asia/Tokyo").dt.tz_localize(None)
        gv = gps[gps["status"] == "A"].copy()

    fs = (len(acc) - 1) / (acc["t_s"].iloc[-1] - acc["t_s"].iloc[0])
    return Ride(d.name, acc, gps, gv, events, status, memo, fs, offset)
