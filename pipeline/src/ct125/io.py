# -*- coding: utf-8 -*-
"""CSV の読み込みと時刻基準の統一（docs/data_schema.md 2.・4.）。

- すべての時計は ESP32 の `t_us`（起動からのマイクロ秒）。走行内の相対時間 `t_rel` [s] を全行に付ける。
- GPS 有効行（status=A）があれば offset = 中央値(UTC − t_rx_us/1e6) を求め、絶対時刻（JST）を付けられる。
  GPS なし走行では offset は None、絶対時刻は NaT。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

JST = "Asia/Tokyo"
# SD の 1 回の記録の約束（contracts/sd/）。合っているかは tests/test_contracts.py で確かめる
ACCEL_COLS = ["n", "t_us", "ax_g", "ay_g", "az_g"]
GPS_COLS = ["t_rx_us", "utc", "date", "status", "fix", "sats", "hdop", "lat", "lon", "speed_kmh", "course_deg"]
EVENT_COLS = ["t_us", "type", "detail"]
ECU_COLS = ["t_us", "pid", "value", "raw"]  # contracts/sd/ecu.table.json（V3.8 から。無い走行もある）
REQUIRED_FILES = ("accel.csv", "gps.csv", "meta.json")
MEMO_FILES = ("notes.md", "memo.txt", "readme.txt")  # 走行メモ。notes.md が今の名前、残りは古い名前


@dataclass
class Ride:
    ride_id: str
    acc: pd.DataFrame
    gps: pd.DataFrame
    events: pd.DataFrame
    meta: dict
    memo: str
    t0_us: int
    fs: float
    offset_s: float | None  # UTC の UNIX 秒 − t_us/1e6。GPS なしなら None
    status: pd.DataFrame | None = field(default=None, repr=False)
    ecu: pd.DataFrame | None = field(default=None, repr=False)  # ECU の値。ecu.csv が無い走行は None

    @property
    def has_abs_time(self) -> bool:
        return self.offset_s is not None

    def duration_s(self) -> float:
        return float(self.acc["t_rel"].iloc[-1])


def gps_unix(gps: pd.DataFrame) -> pd.Series:
    """`date`(ddmmyy) と `utc`(hhmmss.sss) から UNIX 秒を作る。欠損行は NaN。"""
    ok = gps["utc"].notna() & gps["date"].notna()
    out = pd.Series(np.nan, index=gps.index, dtype=float)
    if ok.any():
        g = gps.loc[ok]
        day = pd.to_datetime(g["date"].astype(str).str.zfill(6), format="%d%m%y", utc=True)
        u = g["utc"].astype(float)
        sec = (u // 10000) * 3600 + (u // 100 % 100) * 60 + u % 100
        out.loc[ok] = (day - pd.Timestamp(0, tz="UTC")).dt.total_seconds() + sec
    return out


def utc_offset(gps: pd.DataFrame) -> float | None:
    """有効行から offset = 中央値(UTC − t_rx_us/1e6) を求める。有効行がなければ None。"""
    gv = gps[(gps["status"] == "A") & gps["utc"].notna() & gps["date"].notna()]
    if len(gv) == 0:
        return None
    return float(np.median(gps_unix(gv) - gv["t_rx_us"] / 1e6))


def to_jst(t_rel: np.ndarray | pd.Series, t0_us: int, offset_s: float | None) -> pd.Series:
    """相対秒 → JST（tz 付き）。offset がなければ全行 NaT。"""
    t_rel = np.asarray(t_rel, dtype=float)
    if offset_s is None:
        return pd.Series(pd.NaT, index=range(len(t_rel)), dtype="datetime64[ns, Asia/Tokyo]")
    unix = t0_us / 1e6 + t_rel + offset_s
    return pd.Series(pd.to_datetime(unix, unit="s", utc=True).tz_convert(JST))


def load_ride(ride_id: str, raw_dir: Path | str) -> Ride:
    """`raw_dir/<ride_id>/` の CSV を読み、t_rel と offset を付けて返す。原本は書き換えない。"""
    d = Path(raw_dir) / ride_id
    if not d.is_dir():
        raise FileNotFoundError(f"{d} がありません")
    missing = [name for name in REQUIRED_FILES if not (d / name).exists()]
    if missing:
        raise FileNotFoundError(f"{ride_id} に必要なファイルがありません：{', '.join(missing)}")
    acc = pd.read_csv(d / "accel.csv", usecols=ACCEL_COLS)
    gps = pd.read_csv(d / "gps.csv", dtype={"utc": str, "date": str, "status": str})
    events = pd.read_csv(d / "events.csv") if (d / "events.csv").exists() else pd.DataFrame(columns=EVENT_COLS)
    status = pd.read_csv(d / "status.csv") if (d / "status.csv").exists() else None
    ecu = read_ecu(d / "ecu.csv")
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    memo = read_memo(d)

    acc = acc.sort_values("t_us", kind="stable").reset_index(drop=True)
    t0 = int(acc["t_us"].iloc[0])
    acc["t_rel"] = (acc["t_us"] - t0) / 1e6
    gps["t_rel"] = (gps["t_rx_us"] - t0) / 1e6
    fs = (len(acc) - 1) / float(acc["t_rel"].iloc[-1]) if len(acc) > 1 else float("nan")
    if ecu is not None:
        ecu["t_rel"] = (ecu["t_us"] - t0) / 1e6
    return Ride(ride_id, acc, gps, events, meta, memo, t0, fs, utc_offset(gps), status, ecu)


def read_ecu(path: Path) -> pd.DataFrame | None:
    """ecu.csv（ECU の値。1 行に 1 つの値）を読む。ファイルが無い・列名の行だけなら None。

    pid は 16 進の文字列（"0C" など）のまま読む（数として読むと "0E" などが壊れるため）。読めなかった値は NaN。
    """
    if not path.exists():
        return None
    ecu = pd.read_csv(path, dtype={"pid": str, "raw": str})
    if len(ecu) == 0:
        return None
    ecu["value"] = pd.to_numeric(ecu["value"], errors="coerce")
    return ecu.sort_values("t_us", kind="stable").reset_index(drop=True)


def read_memo(ride_dir: Path | str) -> str:
    """走行メモ（notes.md、古い名前の memo.txt・readme.txt）をこの順につないだもの。無ければ空文字。"""
    paths = [Path(ride_dir) / name for name in MEMO_FILES]
    return " ".join(p.read_text(encoding="utf-8").strip() for p in paths if p.exists())


def list_rides(raw_dir: Path | str) -> list[str]:
    return sorted(p.name for p in Path(raw_dir).glob("ride_*") if (p / "accel.csv").exists())
