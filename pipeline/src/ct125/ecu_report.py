# -*- coding: utf-8 -*-
"""ECU のある走行で、振動と ECU の値を突き合わせる確かめ（#130。`python -m ct125 ecu-report`）。

採点（model.py）には使わない。結果は Markdown にして docs/ に残す。

1. 基準の比べ方：振動の大きさ（log_rms）を、次の区切りごとの中央値で説明したときの残り（log_rms − 区切りの中央値）の広がり。
   - 速度だけ（今の速度補正ベースライン。5 km/h ごと）
   - 回転数だけ（500 rpm ごと）
   - 回転数と負荷（500 rpm × 負荷 20% ごと）
   残りの広がりが小さいほど、その区切りで「ふつうの揺れ」をよく言い当てている。広がりは 1.4826 × MAD（外れ値に強い標準偏差）。
   同じ走行で作って同じ走行に当てた値と、ほかの走行で作って当てた値の両方を出す（同じ走行だけだと、区切りが細かいほど有利になる）。
2. 振動から推定した回転数：1 秒窓ごとに、3 軸のパワーを足したスペクトルの 15〜110 Hz（900〜6,600 rpm）で一番強い山を
   エンジンの 1 次（クランク 1 回転に 1 回）とみなし、回転数 = 周波数 × 60 とする（引き継ぎの資料の 2026-11-15 の調べもの）。
   ECU の回転数（窓の平均）との差を出す。0.5 倍・2 倍に当たった窓は、別の次数の山を拾ったものとして数を分ける。
3. 速度と回転数の比（rpm ÷ km/h）の分布。ギアごとに山ができるかを見る（ギアの推定を列に入れるかの判断材料）。

言い方は docs/analysis_policy.md のとおり。「回転数を取得した」は ECU の値だけに使い、振動からのものは「振動から推定した回転数」と書く。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MAD_SCALE = 1.4826
ORDER_BAND_HZ = (15.0, 110.0)   # エンジンの 1 次を探す帯域（900〜6,600 rpm）
MATCH_TOLERANCE = 0.10          # ECU の回転数との差がこの割合以内なら「合った」
MIN_BIN_COUNT = 10              # 区切りの中央値を作るのに要る窓の数（少ない区切りの窓は数えない）

BASELINES = {
    "速度だけ（5 km/h）": [("speed_kmh", 5.0)],
    "回転数だけ（500 rpm）": [("ecu_rpm_mean", 500.0)],
    "回転数と負荷（500 rpm × 20%）": [("ecu_rpm_mean", 500.0), ("ecu_load_pct", 20.0)],
}


# ------------------------------------------------------------------ 振動から推定した回転数
def vibration_rpm(acc: pd.DataFrame, fs: float, t_start: np.ndarray, window_sec: float = 1.0, band_hz: tuple[float, float] = ORDER_BAND_HZ) -> np.ndarray:
    """窓ごとの、振動から推定した回転数（rpm）。acc は t_rel・ax_g・ay_g・az_g（クリーニング後、間引く前）。

    3 軸それぞれの平均を引いて Hann 窓を掛け、パワーを足したスペクトルの band_hz で一番強い山の周波数 × 60。
    山の周波数は、両隣との放物線で 1 刻みより細かく求める。サンプルが半分に満たない窓は NaN。
    """
    t = acc["t_rel"].to_numpy(float)
    axes = [acc[c].to_numpy(float) for c in ("ax_g", "ay_g", "az_g")]
    t_start = np.asarray(t_start, dtype=float)
    lo = np.searchsorted(t, t_start, side="left")
    hi = np.searchsorted(t, t_start + window_sec, side="left")
    out = np.full(len(t_start), np.nan)
    for w in range(len(t_start)):
        n = hi[w] - lo[w]
        if n < 0.5 * fs * window_sec or n < 16:
            continue
        win = np.hanning(n)
        power = np.zeros(n // 2 + 1)
        for x in axes:
            seg = x[lo[w]:hi[w]]
            spec = np.fft.rfft((seg - seg.mean()) * win)
            power += spec.real**2 + spec.imag**2
        freqs = np.fft.rfftfreq(n, d=1.0 / fs)
        sel = np.flatnonzero((freqs >= band_hz[0]) & (freqs <= band_hz[1]))
        if len(sel) < 3:
            continue
        k = sel[np.argmax(power[sel])]
        shift = 0.0
        if 0 < k < len(power) - 1:
            a, b, c = np.log(power[k - 1] + 1e-30), np.log(power[k] + 1e-30), np.log(power[k + 1] + 1e-30)
            denom = a - 2 * b + c
            shift = 0.5 * (a - c) / denom if denom != 0 else 0.0
        out[w] = (freqs[k] + shift * (freqs[1] - freqs[0])) * 60.0
    return out


@dataclass(frozen=True)
class RpmCheck:
    n: int                 # ECU と振動の両方がある窓
    matched: float         # 差が MATCH_TOLERANCE 以内の割合
    half: float            # 推定が ECU の約 0.5 倍（0.5 次などを拾った）
    double: float          # 推定が ECU の約 2 倍（2 次などを拾った）
    median_abs_diff: float # 差の絶対値の中央値（rpm）
    median_diff_matched: float  # 合った窓の差（推定 − ECU）の中央値（rpm）


def compare_rpm(estimated: np.ndarray, ecu_rpm: np.ndarray, tolerance: float = MATCH_TOLERANCE) -> RpmCheck:
    est = np.asarray(estimated, float)
    ref = np.asarray(ecu_rpm, float)
    ok = np.isfinite(est) & np.isfinite(ref) & (ref > 0)
    if not ok.any():
        return RpmCheck(0, np.nan, np.nan, np.nan, np.nan, np.nan)
    e, r = est[ok], ref[ok]
    ratio = e / r
    matched = np.abs(ratio - 1) <= tolerance
    return RpmCheck(
        n=int(ok.sum()),
        matched=float(matched.mean()),
        half=float((np.abs(ratio - 0.5) <= tolerance * 0.5).mean()),
        double=float((np.abs(ratio - 2) <= tolerance * 2).mean()),
        median_abs_diff=float(np.median(np.abs(e - r))),
        median_diff_matched=float(np.median((e - r)[matched])) if matched.any() else np.nan,
    )


# ------------------------------------------------------------------ 基準の比べ方
def _bin_keys(df: pd.DataFrame, keys: list[tuple[str, float]]) -> pd.Series:
    parts = [np.floor(df[col].to_numpy(float) / width).astype("int64").astype(str) for col, width in keys]
    joined = parts[0]
    for p in parts[1:]:
        joined = np.char.add(np.char.add(joined.astype(str), "|"), p)
    return pd.Series(joined, index=df.index)


def baseline_residuals(train: pd.DataFrame, test: pd.DataFrame, keys: list[tuple[str, float]], target: str = "log_rms", min_count: int = MIN_BIN_COUNT) -> np.ndarray:
    """train で区切りごとの中央値を作り、test の各窓の残り（target − 区切りの中央値）。窓が min_count 未満の区切りは NaN。"""
    tb = _bin_keys(train, keys)
    medians = train.groupby(tb)[target].median()
    counts = tb.value_counts()
    usable = medians[counts.reindex(medians.index).fillna(0) >= min_count]
    sb = _bin_keys(test, keys)
    return test[target].to_numpy(float) - sb.map(usable).to_numpy(float)


def spread(residuals: np.ndarray) -> tuple[float, float]:
    """(広がり＝1.4826 × MAD, 区切りの中央値が使えた窓の割合)。"""
    r = np.asarray(residuals, float)
    ok = np.isfinite(r)
    if not ok.any():
        return np.nan, 0.0
    x = r[ok]
    return float(MAD_SCALE * np.median(np.abs(x - np.median(x)))), float(ok.mean())


def comparable(windows: pd.DataFrame, stop_speed_kmh: float) -> pd.DataFrame:
    """比べるのに使う窓：先頭・末尾でなく、振り切れておらず、速度と ECU の回転数・負荷があり、走っている窓。"""
    w = windows
    keep = (~w["is_edge"]) & (~w["is_clipped"]) & w["has_gps"].fillna(False).astype(bool) & w["has_ecu"].fillna(False).astype(bool)
    keep &= np.isfinite(w["speed_kmh"]) & np.isfinite(w["ecu_load_pct"]) & np.isfinite(w["log_rms"])
    keep &= w["speed_kmh"] >= stop_speed_kmh
    return w[keep]


# ------------------------------------------------------------------ まとめ
def _pct(x: float) -> str:
    return "—" if not np.isfinite(x) else f"{x * 100:.0f}%"


def _num(x: float, digits: int = 3) -> str:
    return "—" if not np.isfinite(x) else f"{x:.{digits}f}"


def render(rides: dict[str, pd.DataFrame], names: dict[str, str] | None = None, stop_speed_kmh: float = 5.0) -> str:
    """rides：走行 ID → 窓（processing.preprocess の windows に vib_rpm 列を足したもの）。Markdown の本文を返す。"""
    names = names or {}
    ids = sorted(rides)
    usable = {rid: comparable(rides[rid], stop_speed_kmh) for rid in ids}
    lines = ["## 対象の走行", "", "| 走行 | 名前 | 窓 | ECU の回転数がある窓 | 比べるのに使った窓（走行中） |", "|---|---|---|---|---|"]
    for rid in ids:
        w = rides[rid]
        lines.append(f"| {rid} | {names.get(rid, '')} | {len(w)} | {_pct(float(w['has_ecu'].mean()))} | {len(usable[rid])} |")

    lines += ["", "## 1. 基準の比べ方（振動の大きさ log_rms の残りの広がり。小さいほど、その区切りでふつうの揺れを言い当てている）", ""]
    header = "| 基準 | " + " | ".join(f"{rid}（同じ走行）" for rid in ids)
    if len(ids) > 1:
        header += " | " + " | ".join(f"{rid}（ほかの走行で作った基準）" for rid in ids)
    lines += [header + " |", "|---" * (1 + len(ids) * (2 if len(ids) > 1 else 1)) + "|"]
    for label, keys in BASELINES.items():
        cells = []
        for rid in ids:
            s, cover = spread(baseline_residuals(usable[rid], usable[rid], keys))
            cells.append(f"{_num(s)}（{_pct(cover)}）")
        if len(ids) > 1:
            for rid in ids:
                train = pd.concat([usable[o] for o in ids if o != rid], ignore_index=True)
                s, cover = spread(baseline_residuals(train, usable[rid], keys))
                cells.append(f"{_num(s)}（{_pct(cover)}）")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "括弧の中は、区切りに窓が 10 以上あって中央値を使えた窓の割合。"]

    lines += ["", "## 2. 振動から推定した回転数と ECU の回転数", "",
              "| 走行 | 両方ある窓 | ±10% で合った | 約 0.5 倍 | 約 2 倍 | 差の絶対値の中央値 | 合った窓の差の中央値（推定 − ECU） |",
              "|---|---|---|---|---|---|---|"]
    for rid in ids:
        w = rides[rid]
        moving = w["has_gps"].fillna(False).astype(bool) & (w["speed_kmh"] >= stop_speed_kmh)
        for label, mask in (("全部", np.ones(len(w), bool)), ("走行中", moving.to_numpy())):
            c = compare_rpm(w["vib_rpm"].to_numpy(float)[mask], w["ecu_rpm_mean"].to_numpy(float)[mask])
            lines.append(f"| {rid}（{label}） | {c.n} | {_pct(c.matched)} | {_pct(c.half)} | {_pct(c.double)} | {_num(c.median_abs_diff, 0)} rpm | {_num(c.median_diff_matched, 0)} rpm |")

    lines += ["", "## 3. 速度と回転数の比（rpm ÷ km/h、走行中・20 km/h 以上）", "", "| 走行 | 比の分布（10 刻みの窓の数。多い順に 6 つ） |", "|---|---|"]
    for rid in ids:
        u = usable[rid]
        fast = u[u["speed_kmh"] >= 20]
        ratio = (fast["ecu_rpm_mean"] / fast["speed_kmh"]).to_numpy(float)
        ratio = ratio[np.isfinite(ratio)]
        counts = pd.Series(np.floor(ratio / 10) * 10).value_counts().head(6)
        text = "、".join(f"{int(k)}〜{int(k) + 10}：{v}" for k, v in counts.items()) or "—"
        lines.append(f"| {rid} | {text} |")
    return "\n".join(lines) + "\n"
