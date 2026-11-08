# -*- coding: utf-8 -*-
"""前処理と点数付けの本体。ローカルの CLI（cli.py）と AWS の Lambda（cloud/）の両方から使う。

process_ride：CSV → クリーニング（interim）→ 1 秒窓の特徴量＋GPS 結合（processed/<ride>/windows.parquet）
score_all   ：全走行の windows.parquet で学習し、各走行の scored.parquet とモデルを保存する
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from . import clean, features, gps as gpsmod, io

WINDOW_COLS_FRONT = ["ride_id", "win", "t_rel", "t_abs", "lat", "lon", "has_gps", "speed_kmh", "is_edge", "is_clipped"]


def process_ride(ride_id: str, cfg: dict, raw_dir: Path, interim_dir: Path, processed_dir: Path, verbose: bool = True) -> pd.DataFrame:
    gcfg = cfg.get("gps", {})
    ride = io.load_ride(ride_id, raw_dir)
    acc = clean.clean_accel(ride.acc, cfg["clip_g"])
    win = features.compute_windows(acc, ride.fs, cfg["window_sec"], cfg.get("bands_hz"))

    gps = clean.validate_gps(ride.gps, gcfg)
    gv = gps[gps["valid"]].sort_values("t_rel").copy()
    if len(gv):
        if gv["speed_kmh"].isna().all():
            gv["speed_kmh"] = gpsmod.haversine_speed_kmh(gv)
        gv["speed_kmh"] = gpsmod.smooth_speed(gv["speed_kmh"], gcfg.get("speed_smooth_points", 3))
    joined = gpsmod.interpolate_to_windows(gv, win["t_rel"].to_numpy(), gcfg.get("max_gap_sec", 5))

    out = win.copy()
    out.insert(0, "ride_id", ride_id)
    # Series のまま代入して tz 付き datetime 型を保つ（to_numpy() だと NaT だけの走行が object 型になり parquet で null 型になる）
    out["t_abs"] = io.to_jst(out["t_rel"].to_numpy(), ride.t0_us, ride.offset_s).set_axis(out.index)
    out["lat"] = joined["lat"].to_numpy()
    out["lon"] = joined["lon"].to_numpy()
    out["has_gps"] = joined["has_gps"].to_numpy()
    out["speed_kmh"] = joined["speed_kmh"].to_numpy()
    out["is_edge"] = clean.flag_edges(out["t_rel"], ride.duration_s(), cfg["edge_sec"])
    out["is_clipped"] = out["n_clipped"] > 0
    out = out[WINDOW_COLS_FRONT + [c for c in out.columns if c not in WINDOW_COLS_FRONT]]

    (interim_dir / ride_id).mkdir(parents=True, exist_ok=True)
    (processed_dir / ride_id).mkdir(parents=True, exist_ok=True)
    acc.to_parquet(interim_dir / ride_id / "accel.parquet", index=False)
    gps.to_parquet(interim_dir / ride_id / "gps.parquet", index=False)
    out.to_parquet(processed_dir / ride_id / "windows.parquet", index=False)

    if verbose:
        fix_ratio = float(gps["valid"].mean()) if len(gps) else 0.0
        reasons = gps.loc[~gps["valid"], "invalid_reason"].value_counts().to_dict()
        print(
            f"{ride_id}: {ride.duration_s()/60:.1f} 分, fs={ride.fs:.1f} Hz, 窓 {len(out)}, has_gps {out['has_gps'].mean():.2f}, "
            f"GPS 有効 {fix_ratio:.2f}（無効の理由 {reasons}）, "
            f"振り切れ窓 {int(out['is_clipped'].sum())}, 絶対時刻 {'あり' if ride.has_abs_time else 'なし'}"
        )
    return out


def score_all(cfg: dict, processed_dir: Path, models_dir: Path, rides: list[str] | None = None, verbose: bool = True, version: str | None = None) -> Path:
    """全走行の windows.parquet を集めて学習・スコア付けし、各走行の scored.parquet とモデルを保存する。

    モデルは models_dir/<version>/ に置き、そのフォルダーを返す。version の既定は今日の日付（YYYYMMDD）。
    """
    from . import model as modelmod

    paths = sorted(processed_dir.glob("ride_*/windows.parquet"))
    if rides:
        paths = [p for p in paths if p.parent.name in rides]
    if not paths:
        raise FileNotFoundError("windows.parquet がありません。先に process を実行してください")
    allw = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    scored, baseline, forest = modelmod.score_windows(allw, cfg.get("model", {}), cfg.get("stop_speed_kmh", 5.0))

    mdir = models_dir / (version or datetime.now().strftime("%Y%m%d"))
    mdir.mkdir(parents=True, exist_ok=True)
    modelmod.save_baseline(baseline, mdir / "baseline.json")
    modelmod.save_model(forest, mdir / "isolation_forest.pkl")
    for rid, g in scored.groupby("ride_id", sort=True):
        g.to_parquet(processed_dir / rid / "scored.parquet", index=False)
        if verbose:
            zs = g["z_speed"]
            print(
                f"{rid}: 窓 {len(g)}, z_speed あり {int(zs.notna().sum())}, z>3 {int(g['is_anomaly_z'].sum())}, "
                f"IF 異常 {int(g['is_anomaly_if'].sum())}, 両方 {int((g['is_anomaly_z'] & g['is_anomaly_if']).sum())}"
            )
    if verbose:
        print(f"ベースライン：学習窓 {baseline['n_train']}, ビン {len(baseline['bins'])} → {mdir}")
    return mdir
