# -*- coding: utf-8 -*-
"""ECU の値を 1 秒窓にそろえる（#130。docs/analysis_policy.md 2.5）。

ecu.csv（contracts/sd/ecu.table.json）は、ESP32 が項目を順番に読んだ値を 1 行に 1 つずつ書いたもの。
時計は加速度と同じ ESP32 の t_us なので、io.load_ride が付けた t_rel で、加速度の窓（features.compute_windows）と同じ区切りにそろえる。

- 回転数（0C）は 1 秒に約 2.8 個入るので、窓の平均・最小・最大を出す
- ほかの項目は 1 秒に 1 個未満（スロットル開度・負荷・吸気圧・点火時期は約 1.5 秒ごと、油温・吸気温・電圧は約 10 秒ごと）なので、
  窓の中の値の平均を「その窓の状態」として使う
- 窓の中に値が無ければ、窓の始まりより前の最後の値で埋める。ただし、その値が HOLD_SEC より古ければ埋めずに欠損にする
  （Bluetooth が切れた区間に古い値が続かないように）。秒数は 2026-11-22 の 2 走行の読む間隔（99% 点）より少し長くした
- ECU の無い走行（ecu.csv が無い・列名の行だけ）は、すべての列が欠損で has_ecu=False。GPS が無い走行と同じ扱い

ECU の値は、市販の ELM327 互換アダプター越しに読んだもの（docs/analysis_policy.md 1.3）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RPM_PID = "0C"
# PID → (窓の列名, 埋める上限の秒数)。回転数は平均・最小・最大の 3 列にする
STATE_COLUMNS = {
    "11": ("ecu_throttle_pct", 3.0),   # スロットル開度（%）
    "04": ("ecu_load_pct", 3.0),       # 負荷（%）
    "0B": ("ecu_map_kpa", 3.0),        # 吸気圧（kPa）
    "0E": ("ecu_timing_deg", 3.0),     # 点火時期（度、上死点前が正）
    "5C": ("ecu_oil_temp_c", 15.0),    # 油温（℃）
    "0F": ("ecu_intake_temp_c", 15.0), # 吸気温（℃）
    "42": ("ecu_volt_v", 15.0),        # ECU の電圧（V）
}
RPM_HOLD_SEC = 2.0
RPM_COLUMNS = ["ecu_rpm_mean", "ecu_rpm_min", "ecu_rpm_max"]
ECU_COLUMNS = ["has_ecu", *RPM_COLUMNS, *(col for col, _ in STATE_COLUMNS.values())]


def empty_columns(n: int) -> pd.DataFrame:
    """ECU の無い走行の列（すべて欠損、has_ecu=False）。"""
    out = pd.DataFrame({col: np.full(n, np.nan) for col in ECU_COLUMNS[1:]})
    out.insert(0, "has_ecu", np.zeros(n, dtype=bool))
    return out


def _held(t: np.ndarray, v: np.ndarray, t_start: np.ndarray, t_end: np.ndarray, hold_sec: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """窓ごとの (平均, 最小, 最大)。窓の中に値が無ければ、hold_sec 以内の前の値で埋める。t は昇順で、v に NaN は無い。"""
    n = len(t_start)
    mean, lo, hi = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    if len(t) == 0:
        return mean, lo, hi
    first = np.searchsorted(t, t_start, side="left")
    last = np.searchsorted(t, t_end, side="left")
    for w in range(n):
        a, b = first[w], last[w]
        if b > a:
            seg = v[a:b]
            mean[w], lo[w], hi[w] = seg.mean(), seg.min(), seg.max()
        elif a > 0 and t_start[w] - t[a - 1] <= hold_sec:
            mean[w] = lo[w] = hi[w] = v[a - 1]
    return mean, lo, hi


def window_columns(ecu: pd.DataFrame | None, t_start: np.ndarray, window_sec: float) -> pd.DataFrame:
    """窓（始まりの秒 t_start、長さ window_sec）ごとの ECU の列。ecu は io.read_ecu の結果に t_rel を付けたもの（None 可）。

    返り値は窓と同じ並び・同じ長さ（index は 0 から）。has_ecu は回転数が入った（埋めた値を含む）窓。
    """
    t_start = np.asarray(t_start, dtype=float)
    if ecu is None or len(ecu) == 0:
        return empty_columns(len(t_start))
    t_end = t_start + window_sec
    valid = ecu[np.isfinite(ecu["value"].to_numpy(float))]
    out = {}
    rpm = valid[valid["pid"] == RPM_PID]
    out["ecu_rpm_mean"], out["ecu_rpm_min"], out["ecu_rpm_max"] = _held(
        rpm["t_rel"].to_numpy(float), rpm["value"].to_numpy(float), t_start, t_end, RPM_HOLD_SEC
    )
    for pid, (col, hold) in STATE_COLUMNS.items():
        item = valid[valid["pid"] == pid]
        out[col] = _held(item["t_rel"].to_numpy(float), item["value"].to_numpy(float), t_start, t_end, hold)[0]
    frame = pd.DataFrame(out)
    frame.insert(0, "has_ecu", np.isfinite(frame["ecu_rpm_mean"].to_numpy(float)))
    return frame[ECU_COLUMNS]
