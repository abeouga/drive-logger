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
    rd = sub.add_parser("render", help="scored.parquet から web/<ride_id>/index.html と web/index.html")
    rd.add_argument("--ride", action="append", default=[], help="描く走行（既定は全走行）")
    rd.add_argument("--root", default=None)
    rd.add_argument("--raw", default=None, help="memo.txt を読む生データのフォルダー（既定 <root>/data/raw）")
    bk = sub.add_parser("bucket", help="S3 バケットを作る（公開ブロック有効・既定暗号化）。既にあれば何もしない")
    bk.add_argument("--root", default=None)
    bk.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    up = sub.add_parser("upload", help="raw/ processed/ site/ を S3 へ（自宅マスク適用後）")
    up.add_argument("--ride", action="append", default=[], help="走行（既定は全走行）")
    up.add_argument("--parts", default="raw,processed,site", help="上げる種類（カンマ区切り：raw,processed,site,models）")
    up.add_argument("--allow-unmasked", action="store_true", help="local.yaml がなくても processed/site を上げる（公開しない前提でのみ）")
    up.add_argument("--root", default=None)
    up.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    ex = sub.add_parser("export", help="Web アプリ用の JSON（rides.json、ride_<id>.json）を web-app/src/data/ に書き出す")
    ex.add_argument("--out", default=None, help="出力先（既定 <root>/web-app/src/data）")
    ex.add_argument("--root", default=None)
    ex.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    ck = sub.add_parser("check-privacy", help="ファイル内の座標に、登録地点から半径 private_radius_m 以内の点が無いか検査")
    ck.add_argument("files", nargs="+")
    ck.add_argument("--root", default=None)
    ck.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    sh = sub.add_parser("share", help="site/<ride_id>/index.html の署名付き URL を発行")
    sh.add_argument("--ride", action="append", required=True)
    sh.add_argument("--expires-hours", type=float, default=72)
    sh.add_argument("--root", default=None)
    sh.add_argument("--raw", default=None, help=argparse.SUPPRESS)
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
    elif args.cmd == "render":
        from . import viz

        memos = {}
        for rid in io.list_rides(raw_dir):
            memos[rid] = " ".join(q.read_text(encoding="utf-8").strip() for q in sorted((raw_dir / rid).glob("*.txt")))
        viz.render_all(processed_dir, root / "web", cfg, memos, args.ride or None)
    elif args.cmd == "export":
        from . import export as exportmod

        memos = {rid: " ".join(q.read_text(encoding="utf-8").strip() for q in sorted((raw_dir / rid).glob("*.txt"))) for rid in io.list_rides(raw_dir)}
        out = Path(args.out) if args.out else root / "web-app" / "src" / "data"
        exportmod.export_all(processed_dir, out, memos)
        if private_points(cfg):
            res = exportmod.check_files(sorted(out.glob("*.json")), private_points(cfg), cfg["private_radius_m"])
            bad = [r for r in res if r["within_radius"]]
            near = min((r["min_m"] for r in res), default=float("inf"))
            print(f"検査：{len(res)} ファイル、登録地点から {cfg['private_radius_m']} m 以内の点 {sum(r['within_radius'] for r in res)}、最も近い点 {near:.0f} m")
            if bad:
                print("登録地点の周辺の座標が書き出されています。中止してください", file=sys.stderr)
                return 1
        else:
            print("注意：config/local.yaml に home がないので自宅マスクは未適用です。この出力を配布しないでください", file=sys.stderr)
    elif args.cmd == "check-privacy":
        from . import export as exportmod

        pts = private_points(cfg)
        if not pts:
            print("config/local.yaml に home がないので検査できません", file=sys.stderr)
            return 2
        res = exportmod.check_files([Path(f) for f in args.files], pts, cfg["private_radius_m"])
        for r in res:
            print(f"{r['file']}: 座標 {r['points']} 点、{cfg['private_radius_m']} m 以内 {r['within_radius']} 点、最も近い点 {r['min_m']:.0f} m")
        return 1 if any(r["within_radius"] for r in res) else 0
    elif args.cmd in ("bucket", "upload", "share"):
        from . import aws as awsmod

        acfg = {**cfg.get("aws", {}), **((cfg.get("local") or {}).get("aws") or {})}
        bucket = acfg.get("bucket")
        if not bucket:
            print("aws.bucket が設定されていません（config/default.yaml または config/local.yaml）", file=sys.stderr)
            return 2
        session = awsmod.make_session(acfg)
        s3 = awsmod.make_s3(session)
        if args.cmd == "bucket":
            region = awsmod.bucket_region(session)
            awsmod.create_bucket(s3, bucket, region)
            print(f"バケット s3://{bucket}（{region}）を用意しました。公開ブロック有効、既定暗号化 SSE-S3")
        elif args.cmd == "upload":
            parts = tuple(x.strip() for x in args.parts.split(",") if x.strip())
            masked = bool(private_points(cfg))
            rides = args.ride or [p.name for p in sorted(processed_dir.glob("ride_*"))]
            ride_parts = tuple(x for x in parts if x != "models")
            try:
                for r in rides if ride_parts else []:
                    awsmod.upload_ride(s3, bucket, root, r, ride_parts, masked, args.allow_unmasked)
            except awsmod.UnmaskedError as e:
                print(e, file=sys.stderr)
                return 2
            if "models" in parts:
                print("models/ →")
                awsmod.upload_files(s3, bucket, awsmod.model_pairs(root))
        else:
            for r in args.ride:
                print(f"{r}: {awsmod.presigned_site_url(s3, bucket, r, args.expires_hours)}")
    return 0
