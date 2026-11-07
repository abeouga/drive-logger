# -*- coding: utf-8 -*-
"""コマンドライン：`python -m ct125 process --ride ride_004` / `--all`。

process：CSV → クリーニング（data/interim）→ 1 秒窓の特徴量＋GPS 結合（data/processed/<ride>/windows.parquet）
処理の本体は processing.py（AWS の Lambda からも使う）。ここは引数を読んで呼ぶだけ。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import io
from .config import load_config, private_points
from .processing import process_ride, score_all

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
    up.add_argument("--site-app", default=None, metavar="HTML", help="Web アプリの 1 ファイル（web/dist/index.html）を site-app/index.html へ。上げる前に座標を検査する")
    up.add_argument("--root", default=None)
    up.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    ex = sub.add_parser("export", help="Web アプリ用のデータ（rides.json・ride_/spec_/wave_）を書き出す。--upload で S3 の app/v1/ へ")
    ex.add_argument("--out", default=None, help="出力先（既定 <root>/data/app/v1）。../web/cache を指定すると S3 を通さずにアプリの cache へ")
    ex.add_argument("--upload", action="store_true", help="書き出して検査が通ったら s3://<bucket>/<aws.app_prefix> へ上げる")
    ex.add_argument("--root", default=None)
    ex.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    ck = sub.add_parser("check-privacy", help="ファイル内の座標に、登録地点から半径 private_radius_m 以内の点が無いか検査")
    ck.add_argument("files", nargs="+")
    ck.add_argument("--root", default=None)
    ck.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    sh = sub.add_parser("share", help="site/<ride_id>/index.html（--app なら site-app/index.html）の署名付き URL を発行")
    sh.add_argument("--ride", action="append", default=[])
    sh.add_argument("--app", action="store_true", help="Web アプリ版（site-app/index.html）の URL")
    sh.add_argument("--expires-hours", type=float, default=72)
    sh.add_argument("--root", default=None)
    sh.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    pp = sub.add_parser("sync-private-points", help="config/local.yaml のマスクする地点（座標だけ）を SSM の SecureString に上げる。AWS の Lambda が使う")
    pp.add_argument("--name", default="/ct125/private-points", help="SSM パラメーター名")
    pp.add_argument("--root", default=None)
    pp.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    rg = sub.add_parser("register-device", help="ESP32 の機器トークンを作り、ハッシュだけを SSM に登録する（C：機器から S3 へ直接送る）")
    rg.add_argument("--id", required=True, help="機器 ID（英小文字・数字・-。例 d01）")
    rg.add_argument("--token-file", default=None, help="トークンをこのファイルに書く（画面には出さない）。省略すると画面に 1 回だけ出す")
    rg.add_argument("--rotate", action="store_true", help="登録済みの機器のトークンを作り直す（古いトークンは使えなくなる）")
    rg.add_argument("--root", default=None)
    rg.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    rv = sub.add_parser("revoke-device", help="機器の登録を消す（その機器はもう送れない）")
    rv.add_argument("--id", required=True)
    rv.add_argument("--root", default=None)
    rv.add_argument("--raw", default=None, help=argparse.SUPPRESS)
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

        memos = {rid: io.read_memo(raw_dir / rid) for rid in io.list_rides(raw_dir)}
        viz.render_all(processed_dir, root / "web", cfg, memos, args.ride or None)
    elif args.cmd == "export":
        from . import export as exportmod

        memos = {rid: io.read_memo(raw_dir / rid) for rid in io.list_rides(raw_dir)}
        out = Path(args.out) if args.out else root / "data" / "app" / "v1"
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
            if args.upload:
                print("自宅マスクが未適用なので S3 には上げません", file=sys.stderr)
                return 2
        if args.upload:
            from . import aws as awsmod

            s3, bucket, acfg = _s3(cfg)
            if s3 is None:
                return 2
            prefix = acfg.get("app_prefix", "app/v1/")
            print(f"→ s3://{bucket}/{prefix}")
            awsmod.upload_files(s3, bucket, awsmod.app_pairs(out, prefix))
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
    elif args.cmd == "sync-private-points":
        return _sync_private_points(cfg, args.name)
    elif args.cmd in ("register-device", "revoke-device"):
        from . import devices

        ssm = _ssm(cfg)
        if args.cmd == "revoke-device":
            devices.revoke(ssm, args.id)
            print(f"{args.id} の登録を消しました（もう送れません）")
            return 0
        token = devices.register(ssm, args.id, rotate=args.rotate)
        if args.token_file:
            Path(args.token_file).write_text(token, encoding="ascii")
            print(f"{args.id} を登録しました。トークンは {args.token_file} に書きました（画面には出していません）")
        else:
            print(f"{args.id} を登録しました。トークン（この 1 回だけ表示。ESP32 に書き込んだら、どこにも残さない）：\n{token}")
    elif args.cmd in ("bucket", "upload", "share"):
        from . import aws as awsmod

        s3, bucket, acfg = _s3(cfg)
        if s3 is None:
            return 2
        if args.cmd == "bucket":
            session = awsmod.make_session(acfg)
            region = awsmod.bucket_region(session)
            awsmod.create_bucket(s3, bucket, region)
            print(f"バケット s3://{bucket}（{region}）を用意しました。公開ブロック有効、既定暗号化 SSE-S3")
        elif args.cmd == "upload" and args.site_app:
            from . import export as exportmod

            html = Path(args.site_app)
            pts = private_points(cfg)
            if not pts:
                print("config/local.yaml に home がないので検査できません。上げません", file=sys.stderr)
                return 2
            r = exportmod.check_files([html], pts, cfg["private_radius_m"])[0]
            print(f"検査：{html} の座標 {r['points']} 点、{cfg['private_radius_m']} m 以内 {r['within_radius']} 点、最も近い点 {r['min_m']:.0f} m")
            if r["within_radius"]:
                print("登録地点の周辺の座標が入っています。上げません", file=sys.stderr)
                return 1
            key = acfg.get("site_app_key", "site-app/index.html")
            awsmod.upload_files(s3, bucket, [(html, key)])
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
            if not args.app and not args.ride:
                print("--ride か --app を指定してください", file=sys.stderr)
                return 2
            if args.app:
                key = acfg.get("site_app_key", "site-app/index.html")
                print(f"app: {awsmod.presigned_url(s3, bucket, key, args.expires_hours, 'text/html; charset=utf-8')}")
            for r in args.ride:
                print(f"{r}: {awsmod.presigned_site_url(s3, bucket, r, args.expires_hours)}")
    return 0


def _sync_private_points(cfg: dict, name: str) -> int:
    """マスクする地点の座標を SSM に上げる（地点の名前は上げない）。値は画面にも出さない。"""
    from . import aws as awsmod
    from .cloud.private_points import to_parameter_value

    pts = private_points(cfg)
    if not pts:
        print("config/local.yaml に home・places がないので上げません", file=sys.stderr)
        return 2
    ssm = _ssm(cfg)
    ssm.put_parameter(Name=name, Value=to_parameter_value(cfg["local"]), Type="SecureString", Overwrite=True)
    print(f"SSM {name} に {len(pts)} 地点を上げました（SecureString）")
    return 0


def _ssm(cfg: dict):
    from . import aws as awsmod

    acfg = {**cfg.get("aws", {}), **((cfg.get("local") or {}).get("aws") or {})}
    return awsmod.make_session(acfg).client("ssm")


def _s3(cfg: dict):
    """(s3 クライアント, バケット名, aws の設定)。バケットが未設定なら (None, None, 設定)。"""
    from . import aws as awsmod

    acfg = {**cfg.get("aws", {}), **((cfg.get("local") or {}).get("aws") or {})}
    bucket = acfg.get("bucket")
    if not bucket:
        print("aws.bucket が設定されていません（config/default.yaml または config/local.yaml）", file=sys.stderr)
        return None, None, acfg
    return awsmod.make_s3(awsmod.make_session(acfg)), bucket, acfg
