# -*- coding: utf-8 -*-
"""画面（web）用のデータ書き出し（web/docs/data_contract.md）。

- rides.json：走行一覧（カード用の要約とスパークライン）
- ride_<id>.json：1 秒窓の列を列ごとの配列で。GPS のない窓は lat/lon を null にする
- spec_<id>.png・spec_<id>.json：スペクトログラム、wave_<id>.json：見どころの生波形
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd

from .gps import haversine_m

SPARK_POINTS = 60
HIGHLIGHT_TOP_N = 10

# 列名（JSON のキー）→ (scored.parquet の列, 丸める桁数)。桁数 None は真偽値
WINDOW_COLUMNS: dict[str, tuple[str, int | None]] = {
    "t_rel": ("t_rel", 1),
    "lat": ("lat", 5),          # 5 桁 ≈ 1 m
    "lon": ("lon", 5),
    "speed": ("speed_kmh", 1),
    "rms": ("rms", 3),
    "log_rms": ("log_rms", 3),
    "p2p": ("p2p", 3),
    "crest": ("crest", 2),
    "z": ("z_speed", 2),
    "score_if": ("score_if", 3),
    "band_1_5": ("band_1_5", 3),
    "band_5_15": ("band_5_15", 3),
    "band_15_40": ("band_15_40", 3),
    "has_gps": ("has_gps", None),
    "is_stopped": ("is_stopped", None),
    "is_edge": ("is_edge", None),
    "is_clipped": ("is_clipped", None),
    "is_anomaly_z": ("is_anomaly_z", None),
    "is_anomaly_if": ("is_anomaly_if", None),
}


# ------------------------------------------------------------------ 値の整形
def _round_list(s: pd.Series, digits: int) -> list:
    """丸めて list に。NaN・inf は None（JSON の null）。"""
    out = []
    for v in s.to_numpy(dtype=float):
        out.append(None if not math.isfinite(v) else round(float(v), digits))
    return out


def _bool_list(s: pd.Series) -> list[bool]:
    return [bool(v) for v in s.fillna(False).to_numpy()]


def without_gps_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """has_gps=False の窓の lat/lon を NaN にした複製を返す（補間できなかった窓に座標を出さない）。"""
    out = df.copy()
    out.loc[~out["has_gps"].fillna(False).astype(bool), ["lat", "lon"]] = np.nan
    return out


def gps_kind(fix_ratio: float, min_ratio: float = 0.10, full_ratio: float = 0.95) -> str:
    """カードのバッジ：none（GPS なし。地図を描かない）／partial（一部）／full（GPS あり）。"""
    if fix_ratio < min_ratio:
        return "none"
    return "full" if fix_ratio >= full_ratio else "partial"


def quintile_classes(values: pd.Series) -> np.ndarray:
    """地図の色の段階：5 分位で 0〜4。NaN は -1。値が少なく分位が重なるときは rank で割る。"""
    v = values.to_numpy(float)
    cls = np.full(len(v), -1)
    ok = np.isfinite(v)
    if ok.sum() == 0:
        return cls
    ranks = pd.Series(v[ok]).rank(method="first")
    cls[ok] = pd.qcut(ranks, 5, labels=False).to_numpy().astype(int) if ok.sum() >= 5 else np.clip(np.floor((ranks - 1) / max(ok.sum(), 1) * 5), 0, 4).astype(int)
    return cls


def ride_distance_km(df: pd.DataFrame) -> float:
    """has_gps の連続する窓の間の距離の合計 [km]（1 秒窓なので窓番号が連続しているときだけ足す）。"""
    g = df[df["has_gps"]].sort_values("win")
    if len(g) < 2:
        return 0.0
    consecutive = np.diff(g["win"].to_numpy()) == 1
    d = haversine_m(g["lat"].to_numpy()[:-1], g["lon"].to_numpy()[:-1], g["lat"].to_numpy()[1:], g["lon"].to_numpy()[1:])
    return float(np.nansum(d[consecutive]) / 1000)


def highlights(df: pd.DataFrame, top_n: int = HIGHLIGHT_TOP_N) -> tuple[np.ndarray, str]:
    """見どころの窓（bool 配列）とその根拠。

    - z_speed > 3 の窓があればそれ（根拠 "z_speed>3"）
    - なければ、走行中・先頭末尾以外で z_speed の上位 N 窓（"z_speed_top"）
    - z_speed がない走行（GPS なし）は、先頭末尾以外で score_if の上位 N 窓（"score_if_top"）
    """
    flag = np.zeros(len(df), dtype=bool)
    if df["is_anomaly_z"].fillna(False).any():
        return df["is_anomaly_z"].fillna(False).to_numpy(bool), "z_speed>3"
    base = ~df["is_edge"].fillna(False)
    if df["z_speed"].notna().any():
        cand = df[base & df["z_speed"].notna() & ~df["is_stopped"].fillna(False)]
        idx = cand.nlargest(top_n, "z_speed").index
        flag[df.index.get_indexer(idx)] = True
        return flag, "z_speed_top"
    cand = df[base & df["score_if"].notna()]
    idx = cand.nlargest(top_n, "score_if").index
    flag[df.index.get_indexer(idx)] = True
    return flag, "score_if_top"


def sparkline(rms: pd.Series, points: int = SPARK_POINTS) -> list:
    """rms を points 個のビンに分けた平均（スパークライン用）。"""
    v = rms.to_numpy(dtype=float)
    if len(v) == 0:
        return []
    edges = np.linspace(0, len(v), min(points, len(v)) + 1).astype(int)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        seg = v[a:b]
        seg = seg[np.isfinite(seg)]
        out.append(round(float(seg.mean()), 3) if len(seg) else None)
    return out


# ------------------------------------------------------------------ 書き出し
def ride_payload(df: pd.DataFrame, memo: str = "") -> tuple[dict, dict]:
    """1 走行分の (一覧用の要約, 窓の列データ) を作る。df は scored.parquet。"""
    df = df.sort_values("win").reset_index(drop=True)
    rid = str(df["ride_id"].iloc[0])
    located = without_gps_coordinates(df)
    hl, basis = highlights(df)
    drawable = located["lat"].notna()
    cls = np.full(len(df), -1)
    if drawable.any():
        cls[drawable.to_numpy()] = quintile_classes(located.loc[drawable, "log_rms"])

    t_abs = df["t_abs"]
    has_abs = t_abs.notna().any()
    t_abs_ms = [None if pd.isna(t) else int(pd.Timestamp(t).value // 1_000_000) for t in t_abs] if has_abs else None

    cols: dict[str, list] = {}
    for key, (col, digits) in WINDOW_COLUMNS.items():
        s = located[col]
        cols[key] = _bool_list(s) if digits is None else _round_list(s, digits)
    cols["t_abs_ms"] = t_abs_ms
    cols["cls"] = cls.tolist()
    cols["highlight"] = hl.tolist()

    fix_ratio = float(df["has_gps"].mean())
    speed = df.loc[df["has_gps"], "speed_kmh"]
    first_abs = t_abs.dropna()
    summary = {
        "id": rid,
        "start_ms": int(pd.Timestamp(first_abs.iloc[0]).value // 1_000_000) if len(first_abs) else None,
        "duration_s": round(float(df["t_rel"].max()), 1),
        "distance_km": round(ride_distance_km(df), 2),
        "max_speed_kmh": round(float(speed.max()), 1) if len(speed) else None,
        "fix_ratio": round(fix_ratio, 3),
        "gps": gps_kind(fix_ratio),
        "n_windows": int(len(df)),
        "n_highlights": int(hl.sum()),
        "highlight_basis": basis,
        "n_anomaly_z": int(df["is_anomaly_z"].fillna(False).sum()),
        "n_anomaly_if": int(df["is_anomaly_if"].fillna(False).sum()),
        "n_clipped": int(df["is_clipped"].fillna(False).sum()),
        "rms_median": round(float(df["rms"].median()), 3),
        "spark": sparkline(df["rms"]),
        "memo": memo,
    }
    payload = {"id": rid, "n": int(len(df)), "has_abs_time": bool(has_abs), "highlight_basis": basis, "columns": cols}
    return summary, payload


def extras_payload(df: pd.DataFrame, acc: pd.DataFrame, highlight_rows: list[int], window_sec: float = 1.0) -> tuple[np.ndarray, dict, dict]:
    """スペクトログラムの画像（不透明度）とその情報、見どころの生波形。df は scored.parquet（win 順）。"""
    from . import spectro

    t = acc["t_rel"].to_numpy(float)
    fs = (len(t) - 1) / float(t[-1] - t[0]) if len(t) > 1 else float("nan")
    t_starts = df["t_start"].to_numpy(float)
    power = spectro.spectrogram(acc, t_starts, fs, window_sec)
    img, scale = spectro.to_alpha(power)
    # 各窓で最も強い周波数（5 Hz 未満は車体の揺れ・姿勢の変化が混ざるので除く）。カーソルの説明用
    body = power[:, 5:]
    peak = [None if not np.isfinite(row).any() else int(np.nanargmax(row)) + 5 for row in body]
    spec_meta = {"id": str(df["ride_id"].iloc[0]), "n_cols": int(img.shape[1]), "f_max_hz": spectro.F_MAX_HZ, "window_sec": window_sec, **scale, "peak_hz": peak}
    waves = {"id": spec_meta["id"], "unit": "mg", "windows": spectro.waveforms(acc, t_starts, highlight_rows, fs, window_sec)}
    return img, spec_meta, waves


def ride_output_files(ride_id: str) -> list[str]:
    """1 走行分の画面用のファイル名（rides.json は含まない）。"""
    return [f"ride_{ride_id}.json", f"spec_{ride_id}.png", f"spec_{ride_id}.json", f"wave_{ride_id}.json"]


def rides_document(summaries: list[dict], generated_at_ms: int | None = None) -> dict:
    """rides.json の中身。走行は ID 順に並べる。"""
    ordered = sorted(summaries, key=lambda s: s["id"])
    if generated_at_ms is None:
        generated_at_ms = int(pd.Timestamp.now(tz="UTC").value // 1_000_000)
    return {"generated_at_ms": generated_at_ms, "rides": ordered}


def dump_json(obj) -> bytes:
    """画面用 JSON の中身（区切りの空白なし、NaN なし）。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def ride_files(scored: pd.DataFrame, accel: pd.DataFrame | None, memo: str = "") -> tuple[dict, dict[str, bytes]]:
    """1 走行分の (rides.json に載せる要約, {ファイル名: 中身})。ファイルには書かない。

    scored は点数付きの窓、accel はクリーニング後の加速度（t_rel・ax_g・ay_g・az_g）。
    accel が無ければスペクトログラムと生波形は作らない。
    """
    from . import spectro

    df = scored.sort_values("win").reset_index(drop=True)
    summary, payload = ride_payload(df, memo)
    ride_id = summary["id"]
    files = {f"ride_{ride_id}.json": dump_json(payload)}
    if accel is not None:
        rows = [i for i, h in enumerate(payload["columns"]["highlight"]) if h]
        img, meta, waves = extras_payload(df, accel, rows)
        files[f"spec_{ride_id}.png"] = spectro.png_alpha(img)
        files[f"spec_{ride_id}.json"] = dump_json(meta)
        files[f"wave_{ride_id}.json"] = dump_json(waves)
    return summary, files
