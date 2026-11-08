# -*- coding: utf-8 -*-
"""コマンドライン：`python -m ct125 <命令>`。

process：CSV → クリーニング（data/interim）→ 1 秒窓の特徴量＋GPS 結合（data/processed/<ride>/windows.parquet）
score  ：全走行の windows.parquet で学習し、scored.parquet とモデル（data/models/<版>/）
export ：画面用のデータ（rides.json・ride_/spec_/wave_）を書き出す
upload ：raw/ processed/ models/ を S3 へ（raw/ を上げると AWS の自動処理が動く）
register-device / revoke-device：ESP32 の機器トークンの登録と取り消し
処理の本体は processing.py（AWS の Lambda からも使う）。ここは引数を読んで呼ぶだけ。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import io
from .config import load_config
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
    up = sub.add_parser("upload", help="raw/ processed/ models/ を S3 へ")
    up.add_argument("--ride", action="append", default=[], help="走行（既定は全走行）")
    up.add_argument("--parts", default="raw,processed", help="上げる種類（カンマ区切り：raw,processed,models）")
    up.add_argument("--root", default=None)
    up.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    ex = sub.add_parser("export", help="画面用のデータ（rides.json・ride_/spec_/wave_）を書き出す")
    ex.add_argument("--out", default=None, help="出力先（既定 <root>/data/app/v1）")
    ex.add_argument("--root", default=None)
    ex.add_argument("--raw", default=None, help=argparse.SUPPRESS)
    rg = sub.add_parser("register-device", help="ESP32 の機器トークンを作り、ハッシュだけを SSM に登録する")
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
    elif args.cmd == "export":
        from . import export as exportmod

        memos = {rid: io.read_memo(raw_dir / rid) for rid in io.list_rides(raw_dir)}
        out = Path(args.out) if args.out else root / "data" / "app" / "v1"
        exportmod.export_all(processed_dir, out, memos, interim_dir=interim_dir)
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
    elif args.cmd == "upload":
        from . import aws as awsmod

        s3, bucket = _s3(cfg)
        if s3 is None:
            return 2
        parts = tuple(x.strip() for x in args.parts.split(",") if x.strip())
        rides = args.ride or [p.name for p in sorted(processed_dir.glob("ride_*"))]
        ride_parts = tuple(x for x in parts if x != "models")
        for r in rides if ride_parts else []:
            awsmod.upload_ride(s3, bucket, root, r, ride_parts)
        if "models" in parts:
            print("models/ →")
            awsmod.upload_files(s3, bucket, awsmod.model_pairs(root))
    return 0


def _aws_settings(cfg: dict) -> dict:
    return {**cfg.get("aws", {}), **((cfg.get("local") or {}).get("aws") or {})}


def _ssm(cfg: dict):
    from . import aws as awsmod

    return awsmod.make_session(_aws_settings(cfg)).client("ssm")


def _s3(cfg: dict):
    """(s3 クライアント, バケット名)。バケットが未設定なら (None, None)。"""
    from . import aws as awsmod

    acfg = _aws_settings(cfg)
    bucket = acfg.get("bucket")
    if not bucket:
        print("aws.bucket が設定されていません（config/default.yaml または config/local.yaml）", file=sys.stderr)
        return None, None
    return awsmod.make_s3(awsmod.make_session(acfg)), bucket
