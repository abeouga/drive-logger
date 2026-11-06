# -*- coding: utf-8 -*-
"""1 秒窓の振動特徴量（計画書 9.1〜9.4）。

- 重力の除去：窓内で 3 軸それぞれの平均を引く。
- 主に使うのは重力除去後の合成加速度 |a| = sqrt(ax²+ay²+az²)。
- 帯域エネルギー比は、3 軸それぞれ（平均除去後）に Hann 窓を掛けて FFT し、パワーを足してから帯域で割合を取る。
  合成加速度（絶対値）に FFT を掛けると整流で周波数が 2 倍に写るため、ここだけ計画書 9.4 から変えている（docs/QUESTIONS.md）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLS = ["rms", "log_rms", "p2p", "std", "crest", "jerk_rms"]


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
