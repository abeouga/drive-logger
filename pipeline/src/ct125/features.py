# -*- coding: utf-8 -*-
"""1 秒窓の振動特徴量（docs/analysis_policy.md 2.）。

- 重力の除去：窓内で 3 軸それぞれの平均を引く。
- 主に使うのは重力除去後の合成加速度 |a| = sqrt(ax²+ay²+az²)。
- 帯域エネルギー比は、3 軸それぞれ（平均除去後）に Hann 窓を掛けて FFT し、パワーを足してから帯域で割合を取る。
  合成加速度（絶対値）に FFT を掛けると整流で周波数が 2 倍に写るため、ここだけ帯域の求め方を 3 軸ごとにしている（docs/analysis_policy.md 2.4）。
- 特徴量は 400 Hz 相当で計算する（for_features）。800 Hz の走行は 200 Hz より上を落として 400 Hz に間引いてから計算し、
  400 Hz の走行と同じ物差しで比べられるようにする（docs/analysis_policy.md 2.1）。スペクトログラムは間引かない。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import resample_poly

FEATURE_FS_HZ = 400.0   # 特徴量を計算する fs の目安（これの 2 倍以上の走行は間引く）
GAP_PERIODS = 2.5       # サンプルの間隔がこの周期数を超えたら途切れとみなし、またいで間引かない
MIN_FILTER_SAMPLES = 64 # これより短い区間は低域通過せずに間引くだけ（端の影響が大きいため）

FEATURE_COLS = ["rms", "log_rms", "p2p", "std", "crest", "jerk_rms"]


def decimation_factor(fs: float) -> int:
    """特徴量のために間引く割合（1 なら間引かない）。fs ≈ 400 なら 1、fs ≈ 800 なら 2。"""
    if not np.isfinite(fs) or fs <= 0:
        return 1
    return max(1, int(round(fs / FEATURE_FS_HZ)))


def for_features(acc: pd.DataFrame, fs: float) -> tuple[pd.DataFrame, float]:
    """特徴量を計算する加速度と fs。fs が 400 Hz 相当なら acc をそのまま返す。

    間引くときは、記録が途切れていない区間ごとに 3 軸を resample_poly（低域通過＋間引き）し、
    t_rel は区間の q 個ごとのサンプルの時刻を使う。is_clipped は間引いた q 個のどれかが振り切れていれば True。
    """
    q = decimation_factor(fs)
    if q == 1 or len(acc) < 2:
        return acc, fs
    t = acc["t_rel"].to_numpy(float)
    gaps = np.flatnonzero(np.diff(t) > GAP_PERIODS / fs) + 1
    starts = np.concatenate([[0], gaps])
    ends = np.concatenate([gaps, [len(t)]])
    clipped = acc["is_clipped"].to_numpy(bool) if "is_clipped" in acc else None
    parts = []
    for lo, hi in zip(starts, ends):
        idx = np.arange(lo, hi, q)
        part = {"t_rel": t[idx]}
        for col in ("ax_g", "ay_g", "az_g"):
            x = acc[col].to_numpy(float)[lo:hi]
            if hi - lo >= MIN_FILTER_SAMPLES:
                y = resample_poly(x, 1, q, padtype="line")[: len(idx)]
            else:
                y = x[::q]
            part[col] = y
        if clipped is not None:
            c = clipped[lo:hi]
            pad = (-len(c)) % q
            part["is_clipped"] = np.concatenate([c, np.zeros(pad, bool)]).reshape(-1, q).any(axis=1)
        parts.append(pd.DataFrame(part))
    return pd.concat(parts, ignore_index=True), fs / q


def dynamic_magnitude(ax: np.ndarray, ay: np.ndarray, az: np.ndarray) -> np.ndarray:
    """窓内平均（≒重力）を各軸から引いた後の合成加速度。"""
    dx = ax - ax.mean()
    dy = ay - ay.mean()
    dz = az - az.mean()
    return np.sqrt(dx * dx + dy * dy + dz * dz)


def band_ratios(ax: np.ndarray, ay: np.ndarray, az: np.ndarray, fs: float, bands: dict[str, tuple[float, float]]) -> dict[str, float]:
    """3 軸合計のパワースペクトルから、各帯域のエネルギー比（全帯域の合計で正規化、DC を除く）。"""
    n = len(ax)
    if n < 8 or not bands:
        return {k: np.nan for k in bands}
    win = np.hanning(n)
    power = np.zeros(n // 2 + 1)
    for s in (ax, ay, az):
        spec = np.fft.rfft((s - s.mean()) * win)
        power += (spec.real**2 + spec.imag**2)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    nyq = fs / 2
    total = 0.0
    out = {}
    for name, (lo, hi) in bands.items():
        hi_eff = min(float(hi), nyq)
        if float(lo) >= nyq:
            out[name] = np.nan
            continue
        sel = (freqs >= lo) & (freqs < hi_eff)
        out[name] = float(power[sel].sum())
        total += out[name]
    if total > 0:
        out = {k: (v / total if np.isfinite(v) else v) for k, v in out.items()}
    return out


def window_features(ax: np.ndarray, ay: np.ndarray, az: np.ndarray, fs: float, bands: dict | None = None) -> dict[str, float]:
    """1 窓分の特徴量。入力は g 単位の 3 軸（重力込みでよい。ここで窓内平均を引く）。"""
    mag = dynamic_magnitude(ax, ay, az)
    rms = float(np.sqrt(np.mean(mag * mag)))
    feats = {
        "rms": rms,
        "log_rms": float(np.log(rms + 1e-6)),
        "p2p": float(mag.max() - mag.min()),
        "std": float(mag.std()),
        "crest": float(mag.max() / rms) if rms > 0 else np.nan,
        "jerk_rms": float(np.sqrt(np.mean(np.diff(mag) ** 2)) * fs) if len(mag) > 1 else np.nan,
        "n_samples": int(len(mag)),
    }
    if bands:
        feats.update(band_ratios(ax, ay, az, fs, bands))
    return feats


def compute_windows(acc: pd.DataFrame, fs: float, window_sec: float = 1.0, bands: dict | None = None, min_fill: float = 0.5) -> pd.DataFrame:
    """重なりなしの固定長窓で特徴量を計算する。

    acc は `t_rel`・`ax_g`・`ay_g`・`az_g`（任意で `is_clipped`）を持ち t_rel で昇順。
    期待サンプル数の min_fill 倍に満たない窓（末尾の欠け）は捨てる。
    返り値の各行：win, t_rel（窓の中心秒）, t_start, n_samples, n_clipped, 特徴量…
    """
    t = acc["t_rel"].to_numpy(float)
    ax = acc["ax_g"].to_numpy(float)
    ay = acc["ay_g"].to_numpy(float)
    az = acc["az_g"].to_numpy(float)
    clipped = acc["is_clipped"].to_numpy(bool) if "is_clipped" in acc else np.zeros(len(acc), dtype=bool)
    n_win = int(np.floor(t[-1] / window_sec)) + 1
    edges = np.arange(n_win + 1) * window_sec
    bounds = np.searchsorted(t, edges, side="left")
    expected = fs * window_sec
    rows = []
    for w in range(n_win):
        lo, hi = bounds[w], bounds[w + 1]
        if hi - lo < min_fill * expected:
            continue
        f = window_features(ax[lo:hi], ay[lo:hi], az[lo:hi], fs, bands)
        f.update(win=w, t_start=float(edges[w]), t_rel=float(edges[w] + window_sec / 2), n_clipped=int(clipped[lo:hi].sum()))
        rows.append(f)
    df = pd.DataFrame(rows)
    front = ["win", "t_start", "t_rel", "n_samples", "n_clipped"]
    return df[front + [c for c in df.columns if c not in front]]
