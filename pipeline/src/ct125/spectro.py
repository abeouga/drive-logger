# -*- coding: utf-8 -*-
"""スペクトログラムと生波形の書き出し（docs/WEB_PLAN.md 4.、Web アプリ版の 11/9 分）。

スペクトログラム
- 走行の 1 秒窓（windows.parquet と同じ区切り）ごとに、3 軸それぞれの平均を引いて Hann 窓を掛けて FFT し、
  パワーを足す（合成加速度にすると整流で周波数が 2 倍に写るため。features.band_ratios と同じ考え方）。
- 0〜199 Hz を 1 Hz ごとの行にして dB にし、走行の中の分位点で 0〜1 に正規化する。
- 画像は「強さ＝不透明度」の PNG（グレー＋アルファ）。画面側でテーマの色を当てて塗るので、明暗どちらでも 1 枚で済む。

生波形
- 全部の 1 秒窓について、その 1 秒の 3 軸（平均を引いたもの）を mg の整数で書き出す。
  ファイルは約 1 分（60 窓）ごとに分ける（export.wave_chunk_name）。
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

F_MAX_HZ = 200          # ナイキスト（約 199 Hz）まで
N_FFT = 400             # 1 秒窓（約 398 サンプル）をゼロ詰めして固定長に
ALPHA_LEVELS = 16       # 不透明度の段階（減らすと PNG がよく縮む）


def window_bounds(t_rel: np.ndarray, t_starts: np.ndarray, window_sec: float = 1.0) -> list[tuple[int, int]]:
    """各窓 [t_start, t_start + window_sec) に入るサンプルの添字範囲。"""
    lo = np.searchsorted(t_rel, t_starts, side="left")
    hi = np.searchsorted(t_rel, t_starts + window_sec, side="left")
    return list(zip(lo.tolist(), hi.tolist()))


def window_power(ax: np.ndarray, ay: np.ndarray, az: np.ndarray, fs: float, f_max: int = F_MAX_HZ, n_fft: int = N_FFT) -> np.ndarray:
    """1 窓の 3 軸合計パワーを 0..f_max-1 Hz の 1 Hz 刻みで返す（長さ f_max）。サンプルが少なければ NaN。"""
    n = len(ax)
    if n < 8:
        return np.full(f_max, np.nan)
    win = np.hanning(n)
    power = np.zeros(n_fft // 2 + 1)
    for s in (ax, ay, az):
        spec = np.fft.rfft((s - s.mean()) * win, n=n_fft)
        power += spec.real**2 + spec.imag**2
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / fs)
    grid = np.arange(f_max, dtype=float)
    out = np.interp(grid, freqs, power, right=np.nan)
    return out


def spectrogram(acc: pd.DataFrame, t_starts: np.ndarray, fs: float, window_sec: float = 1.0, f_max: int = F_MAX_HZ) -> np.ndarray:
    """窓 × 周波数（1 Hz）のパワー行列。acc は t_rel・ax_g・ay_g・az_g を持ち t_rel で昇順。"""
    t = acc["t_rel"].to_numpy(float)
    ax = acc["ax_g"].to_numpy(float)
    ay = acc["ay_g"].to_numpy(float)
    az = acc["az_g"].to_numpy(float)
    out = np.full((len(t_starts), f_max), np.nan)
    for k, (lo, hi) in enumerate(window_bounds(t, np.asarray(t_starts, float), window_sec)):
        out[k] = window_power(ax[lo:hi], ay[lo:hi], az[lo:hi], fs, f_max)
    return out


def to_alpha(power: np.ndarray, lo_pct: float = 5.0, hi_pct: float = 99.5, levels: int = ALPHA_LEVELS) -> tuple[np.ndarray, dict]:
    """パワー（窓 × 周波数）→ 画像用の不透明度（周波数 × 窓、上が高い周波数）と、色の範囲の情報。

    dB にして、DC（0 Hz）を除いた値の分位点 [lo_pct, hi_pct] を 0〜1 に割り当て、levels 段階に丸める。
    """
    db = 10 * np.log10(np.where(np.isfinite(power), power, np.nan) + 1e-12)
    body = db[:, 1:]
    finite = body[np.isfinite(body)]
    if finite.size == 0:
        lo, hi = 0.0, 1.0
    else:
        lo, hi = float(np.percentile(finite, lo_pct)), float(np.percentile(finite, hi_pct))
    if hi <= lo:
        hi = lo + 1.0
    x = np.clip((db - lo) / (hi - lo), 0.0, 1.0)
    x[:, 0] = 0.0                      # DC は描かない
    x = np.nan_to_num(x, nan=0.0)
    step = 255 / (levels - 1)
    alpha = (np.round(x * (levels - 1)) * step).astype(np.uint8)
    img = alpha.T[::-1]                # 行＝周波数（上が高い）、列＝窓
    return img, {"db_min": round(lo, 1), "db_max": round(hi, 1), "pct": [lo_pct, hi_pct]}


def png_alpha(alpha: np.ndarray) -> bytes:
    """グレー（黒）＋アルファの PNG の中身（外部ライブラリなし）。"""
    h, w = alpha.shape
    raw = bytearray()
    for row in alpha:
        raw.append(0)                  # フィルターなし
        la = np.zeros(w * 2, dtype=np.uint8)
        la[1::2] = row
        raw.extend(la.tobytes())

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 4, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")


def write_png_alpha(path: Path, alpha: np.ndarray) -> int:
    """png_alpha をファイルに書く。返り値はバイト数。"""
    png = png_alpha(alpha)
    Path(path).write_bytes(png)
    return len(png)


def waveforms(acc: pd.DataFrame, t_starts: np.ndarray, rows: list[int], fs: float, window_sec: float = 1.0) -> list[dict]:
    """rows（窓の添字）ごとに、その 1 秒の 3 軸（平均を引いた mg の整数）を返す。"""
    t = acc["t_rel"].to_numpy(float)
    bounds = window_bounds(t, np.asarray(t_starts, float), window_sec)
    out = []
    for i in rows:
        lo, hi = bounds[i]
        item = {"i": int(i), "fs": round(float(fs), 2), "t0": round(float(t_starts[i]), 3)}
        for key, col in (("ax", "ax_g"), ("ay", "ay_g"), ("az", "az_g")):
            s = acc[col].to_numpy(float)[lo:hi]
            item[key] = np.round((s - s.mean()) * 1000).astype(int).tolist()
        out.append(item)
    return out
