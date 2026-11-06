# -*- coding: utf-8 -*-
"""コマンドライン：`python -m ct125 process --ride ride_004` / `--all`。

process：CSV → クリーニング（data/interim）→ 1 秒窓の特徴量＋GPS 結合（data/processed/<ride>/windows.parquet）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import clean, features, gps as gpsmod, io
from .config import load_config, private_points

WINDOW_COLS_FRONT = ["ride_id", "win", "t_rel", "t_abs", "lat", "lon", "has_gps", "speed_kmh", "is_edge", "is_private", "is_clipped"]


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

    pts = private_points(cfg)
    out = win.copy()
    out.insert(0, "ride_id", ride_id)
    # Series のまま代入して tz 付き datetime 型を保つ（to_numpy() だと NaT だけの走行が object 型になり parquet で null 型になる）
    out["t_abs"] = io.to_jst(out["t_rel"].to_numpy(), ride.t0_us, ride.offset_s).set_axis(out.index)
    out["lat"] = joined["lat"].to_numpy()
    out["lon"] = joined["lon"].to_numpy()
    out["has_gps"] = joined["has_gps"].to_numpy()
    out["speed_kmh"] = joined["speed_kmh"].to_numpy()
    out["is_edge"] = clean.flag_edges(out["t_rel"], ride.duration_s(), cfg["edge_sec"])
    out["is_private"] = gpsmod.mask_private(out["lat"], out["lon"], pts, cfg["private_radius_m"]) if pts else np.zeros(len(out), dtype=bool)
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
            f"GPS 有効 {fix_ratio:.2f}（無効の理由 {reasons}）, is_private {int(out['is_private'].sum())}, "
            f"振り切れ窓 {int(out['is_clipped'].sum())}, 絶対時刻 {'あり' if ride.has_abs_time else 'なし'}"
            + ("" if pts else "  ※ config/local.yaml がないので自宅マスクは未適用")
        )
    return out


def score_all(cfg: dict, processed_dir: Path, models_dir: Path, rides: list[str] | None = None, verbose: bool = True) -> pd.DataFrame:
    """全走行の windows.parquet を集めて学習・スコア付けし、各走行の scored.parquet とモデルを保存する。"""
    from datetime import date

    from . import model as modelmod

    paths = sorted(processed_dir.glob("ride_*/windows.parquet"))
    if rides:
        paths = [p for p in paths if p.parent.name in rides]
    if not paths:
        raise FileNotFoundError("windows.parquet がありません。先に process を実行してください")
    allw = pd.concat([pd.read_parquet(p) for p in paths], ignore_index=True)
    scored, baseline, forest = modelmod.score_windows(allw, cfg.get("model", {}), cfg.get("stop_speed_kmh", 5.0))

    mdir = models_dir / date.today().strftime("%Y%m%d")
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
    return scored


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ct125", description="CT125 走行データの解析パイプライン")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("process", help="CSV → 1 秒窓の特徴量（windows.parquet）")
    sp.add_argument("--ride", action="append", default=[], help="ride_id（複数指定可）")
    sp.add_argument("--all", action="store_true", help="data/raw の全走行")
    sp.add_argument("--raw", default=None, help="生データのフォルダー（既定 <root>/data/raw）")
    sp.add_argument("--root", default=None, help="リポジトリのルート（既定は自動）")
    sc = sub.add_parser("score", help="全走行の windows.parquet から異常スコア（scored.parquet）")
    sc.add_argument("--ride", action="append", default=[], help="学習・スコア対象を絞る（既定は全走行）")
    sc.add_argument("--root", default=None)
    sc.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    cfg = load_config(args.root) if args.root else load_config()
    root = Path(cfg["_root"])
    raw_dir = Path(args.raw) if args.raw else root / "data" / "raw"
    interim_dir = root / "data" / "interim"
    processed_dir = root / "data" / "processed"

    if args.cmd == "process":
        rides = io.list_rides(raw_dir) if args.all else args.ride
        if not rides:
            print("--ride か --all を指定してください", file=sys.stderr)
            return 2
        for r in rides:
            process_ride(r, cfg, raw_dir, interim_dir, processed_dir)
    elif args.cmd == "score":
        score_all(cfg, processed_dir, root / "data" / "models", args.ride or None)
    return 0
