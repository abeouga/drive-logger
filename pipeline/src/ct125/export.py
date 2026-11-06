# -*- coding: utf-8 -*-
"""Web アプリ版（web-app/）用のデータ書き出し（docs/WEB_PLAN.md 4.）。

- rides.json：走行一覧（カード用の要約とスパークライン）
- ride_<id>.json：1 秒窓の列を列ごとの配列で
- 自宅周辺（is_private）の窓は lat/lon を null にして書き出す（隠すのではなく、データに入れない）。
- 自宅座標そのものはどこにも書き出さない。
- 書き出したファイル（とビルド後の dist/index.html）に、登録地点から半径 R 以内の座標が無いことを検査する関数も置く。
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .gps import haversine_m
from .viz import map_mode, quintile_classes, ride_distance_km

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
    "is_private": ("is_private", None),
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


def mask_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """is_private または has_gps=False の窓の lat/lon を NaN にした複製を返す。"""
    out = df.copy()
    hide = out["is_private"].fillna(False).astype(bool) | ~out["has_gps"].fillna(False).astype(bool)
    out.loc[hide, ["lat", "lon"]] = np.nan
    return out


def gps_kind(fix_ratio: float) -> str:
    """カードのバッジ：full（GPS あり）／partial（一部）／none（なし）。地図の判定と同じしきい値。"""
    return map_mode(fix_ratio)


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
    masked = mask_coordinates(df)
    hl, basis = highlights(df)
    drawable = masked["lat"].notna()
    cls = np.full(len(df), -1)
    if drawable.any():
        cls[drawable.to_numpy()] = quintile_classes(masked.loc[drawable, "log_rms"])

    t_abs = df["t_abs"]
    has_abs = t_abs.notna().any()
    t_abs_ms = [None if pd.isna(t) else int(pd.Timestamp(t).value // 1_000_000) for t in t_abs] if has_abs else None

    cols: dict[str, list] = {}
    for key, (col, digits) in WINDOW_COLUMNS.items():
        s = masked[col]
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
        "n_private": int(df["is_private"].fillna(False).sum()),
        "n_clipped": int(df["is_clipped"].fillna(False).sum()),
        "rms_median": round(float(df["rms"].median()), 3),
        "spark": sparkline(df["rms"]),
        "memo": memo,
    }
    payload = {"id": rid, "n": int(len(df)), "has_abs_time": bool(has_abs), "highlight_basis": basis, "columns": cols}
    return summary, payload


def _dump(obj, path: Path) -> int:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def export_all(processed_dir: Path, out_dir: Path, memos: dict[str, str] | None = None, verbose: bool = True) -> list[dict]:
    paths = sorted(processed_dir.glob("ride_*/scored.parquet"))
    if not paths:
        raise FileNotFoundError("scored.parquet がありません。先に process と score を実行してください")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("ride_*.json"):
        old.unlink()
    summaries = []
    for p in paths:
        df = pd.read_parquet(p)
        summary, payload = ride_payload(df, (memos or {}).get(p.parent.name, ""))
        size = _dump(payload, out_dir / f"ride_{summary['id']}.json")
        summaries.append(summary)
        if verbose:
            print(f"{summary['id']}: 窓 {payload['n']}, 座標あり {sum(v is not None for v in payload['columns']['lat'])}, "
                  f"見どころ {summary['n_highlights']}（{summary['highlight_basis']}）, {size / 1024:.0f} KB")
    total = _dump({"generated_at_ms": int(pd.Timestamp.now(tz="UTC").value // 1_000_000), "rides": summaries}, out_dir / "rides.json")
    if verbose:
        print(f"rides.json: {len(summaries)} 走行, {total / 1024:.1f} KB → {out_dir}")
    return summaries


# ------------------------------------------------------------------ 検査（自宅周辺の座標が無いこと）
# 緯度・経度らしい 10 進数の組（JSON の "lat":..,"lon":.. と、[lat, lon] / [lon, lat] の配列の両方を拾う）
_NUM = r"-?\d{1,3}\.\d+"  # 漏れを避けるため小数 1 桁から拾う（日本の範囲外は捨てる）
_PAIR = re.compile(rf"({_NUM})\s*,\s*({_NUM})")


def coordinate_pairs(text: str, lat_range=(20.0, 46.0), lon_range=(122.0, 154.0)) -> np.ndarray:
    """テキスト中の「緯度,経度」「経度,緯度」の組を日本の範囲で拾い、(lat, lon) の配列で返す。"""
    pts = []
    for a, b in _PAIR.findall(text):
        x, y = float(a), float(b)
        if lat_range[0] <= x <= lat_range[1] and lon_range[0] <= y <= lon_range[1]:
            pts.append((x, y))
        elif lat_range[0] <= y <= lat_range[1] and lon_range[0] <= x <= lon_range[1]:
            pts.append((y, x))
    return np.array(pts, dtype=float).reshape(-1, 2)


_ARRAY = {k: re.compile(rf'["\']?{k}["\']?\s*:\s*\[([^\]]*)\]') for k in ("lat", "lon")}


def column_array_points(text: str) -> np.ndarray:
    """JSON や JS に埋め込まれた `lat:[...]` と `lon:[...]` の列を出現順に対にして (lat, lon) を返す。

    ビルド後の 1 ファイル HTML ではデータが列ごとの配列で入るので、「緯度,経度」の組の検索では拾えない。
    """
    def arrays(key):
        out = []
        for m in _ARRAY[key].finditer(text):
            vals = []
            for tok in m.group(1).split(","):
                tok = tok.strip()
                try:
                    vals.append(float(tok))
                except ValueError:
                    vals.append(None)  # null など
            out.append(vals)
        return out

    pts = []
    for lat_arr, lon_arr in zip(arrays("lat"), arrays("lon")):
        for a, b in zip(lat_arr, lon_arr):
            if a is not None and b is not None and -90 <= a <= 90 and -180 <= b <= 180:
                pts.append((a, b))
    return np.array(pts, dtype=float).reshape(-1, 2)


def json_points(payload: dict) -> np.ndarray:
    """ride_<id>.json の lat/lon 列から (lat, lon) の配列（null は除く）。"""
    lat = payload["columns"]["lat"]
    lon = payload["columns"]["lon"]
    return np.array([(a, b) for a, b in zip(lat, lon) if a is not None and b is not None], dtype=float).reshape(-1, 2)


def min_distance_m(points: np.ndarray, places: list[tuple[float, float]]) -> float:
    """points のうち、登録地点のどれかに最も近い点までの距離 [m]。点が無ければ inf。"""
    if len(points) == 0 or not places:
        return math.inf
    return float(min(np.min(haversine_m(points[:, 0], points[:, 1], plat, plon)) for plat, plon in places))


def check_files(paths: list[Path], places: list[tuple[float, float]], radius_m: float) -> list[dict]:
    """各ファイルの座標を調べ、登録地点から radius_m 以内の点の数を返す。"""
    results = []
    for p in paths:
        text = p.read_text(encoding="utf-8", errors="ignore")
        pts = np.vstack([coordinate_pairs(text), column_array_points(text)])
        n_near = 0
        for plat, plon in places:
            if len(pts):
                n_near += int((haversine_m(pts[:, 0], pts[:, 1], plat, plon) <= radius_m).sum())
        results.append({"file": str(p), "points": int(len(pts)), "min_m": min_distance_m(pts, places), "within_radius": n_near})
    return results
