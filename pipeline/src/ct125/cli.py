# -*- coding: utf-8 -*-
"""コマンドライン：`python -m ct125 <命令>`。

ローカルでも、AWS の Lambda と同じ処理の流れ（flow.py）を使い、S3 から読み、S3 に書く。手元にデータのフォルダーは置かない。
ローカルの処理は作業用の場所に結果を置くだけで、画面（公開用）は変えない。公開するときは Lambda に頼む（publish）。

process        ：走行を処理する（生データ → 作業用に結果と記録）
retrain        ：全走行で学習し直す（新しいモデルの版を作業用に置く。今使うモデルは変えない）
publish        ：処理の結果を公開するよう、処理の Lambda に頼む
rides          ：走行の台帳を表で見る
evaluate       ：判定の確かめ。学習に使う走行を 1 本ずつ抜いて学習し、抜いた走行に点数を付ける（読むだけ。どこにも書かない）
upload-sd      ：PC から SD の走行を送る（ESP32 と同じデバイス API を通す。同じ走行は 2 回受け付けない）
register-device / revoke-device：ESP32・PC の機器トークンの登録と取り消し

向き先（本番 prod・test）は --env か環境変数 CT125_ENV で選ぶ（既定は config の aws.env。docs/test_environment.md）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ct125", description="CT125 走行データの解析パイプライン")
    p.add_argument("--root", default=None, help=argparse.SUPPRESS)
    p.add_argument("--env", default=None, help="向き先の環境（prod か test）。省くと CT125_ENV、無ければ config の aws.env")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("process", help="走行を処理する（S3 の生データ → 作業用に結果と記録。公開はしない）")
    sp.add_argument("--ride", action="append", required=True, help="走行 ID（複数指定可）")
    sub.add_parser("retrain", help="全走行で学習し直す（新しいモデルを作業用に置く。公開・切り替えはしない）")
    pb = sub.add_parser("publish", help="処理の結果を公開するよう、処理の Lambda に頼む")
    pb.add_argument("--run", default=None, help="公開する処理の ID（省くと台帳のとおりに作り直すだけ）")
    sub.add_parser("rides", help="走行の台帳を表で見る")
    ev = sub.add_parser("evaluate", help="判定の確かめ（1 走行ずつ抜いて学習し、抜いた走行に点数を付ける。どこにも書かない）")
    ev.add_argument("--leave-one-ride-out", action="store_true", required=True, help="1 走行ずつ抜く（今はこの確かめ方だけ）")
    ev.add_argument("--top", type=int, default=20, help="スコアの上位を何件出すか（既定 20）")
    ev.add_argument("--method", default=None, help="判定の方法（speed_baseline・speed_iforest。既定は config の model.anomaly_method）")
    ev.add_argument("--quantile", type=float, default=None, help="speed_iforest のしきい値の分位点（既定は config の model.anomaly_quantile）")
    ev.add_argument("--windows-dir", default=None, help="S3 から読まず、このフォルダーの <走行 ID>*.parquet（windows.parquet。学習に使う走行だけ）を使う")
    us = sub.add_parser("upload-sd", help="PC から SD の走行を送る（デバイス API を通す。走行 ID はサーバーが付ける）")
    us.add_argument("paths", nargs="+", help="SD の走行のフォルダー（accel.csv がある所）か、その親（/sessions など）")
    us.add_argument("--device-id", default=None, help="機器 ID（既定は config の upload.device_id）")
    us.add_argument("--token-file", default=None, help="register-device --token-file で作ったファイル（既定は config の upload.token_file）")
    us.add_argument("--base-url", default=None, help="送り先の URL（既定は config/local.yaml の upload.base_url）")
    us.add_argument("--resume", default=None, metavar="RIDE_ID", help="途中で切れたとき：前回の走行 ID（フォルダーを 1 つだけ渡す）")
    rg = sub.add_parser("register-device", help="ESP32 の機器トークンを作り、ハッシュだけを SSM に登録する")
    rg.add_argument("--id", required=True, help="機器 ID（英小文字・数字・-。例 d01）")
    rg.add_argument("--token-file", default=None, help="トークンをこのファイルに書く（画面には出さない）。省略すると画面に 1 回だけ出す")
    rg.add_argument("--rotate", action="store_true", help="登録済みの機器のトークンを作り直す（古いトークンは使えなくなる）")
    rv = sub.add_parser("revoke-device", help="機器の登録を消す（その機器はもう送れない）")
    rv.add_argument("--id", required=True)
    args = p.parse_args(argv)

    cfg = load_config(args.root, env=args.env) if args.root else load_config(env=args.env)
    acfg = aws_settings(cfg)
    print(f"向き先：{cfg['_env']}", file=sys.stderr)

    if args.cmd in ("process", "retrain"):
        pipeline = local_pipeline(cfg, acfg)
        result = pipeline.process(args.ride, publish=False) if args.cmd == "process" else pipeline.retrain(publish=False)
        _print_result(result)
        return 0 if result["status"] == "succeeded" else 1
    if args.cmd == "publish":
        return _invoke_publish(acfg, args.run)
    if args.cmd == "rides":
        return _print_ledger(cfg, acfg)
    if args.cmd == "evaluate":
        return _evaluate(cfg, acfg, args)
    if args.cmd == "upload-sd":
        return _upload_sd(cfg, args)
    if args.cmd in ("register-device", "revoke-device"):
        from . import devices

        ssm = make_session(acfg, admin=True).client("ssm")
        prefix = acfg.get("device_parameter_prefix") or devices.PARAMETER_PREFIX
        if args.cmd == "revoke-device":
            devices.revoke(ssm, args.id, prefix=prefix)
            print(f"{args.id} の登録を消しました（もう送れません）")
            return 0
        token = devices.register(ssm, args.id, rotate=args.rotate, prefix=prefix)
        if args.token_file:
            Path(args.token_file).write_text(token, encoding="ascii")
            print(f"{args.id} を登録しました。トークンは {args.token_file} に書きました（画面には出していません）")
        else:
            print(f"{args.id} を登録しました。トークン（この 1 回だけ表示。ESP32 に書き込んだら、どこにも残さない）：\n{token}")
    return 0


# ------------------------------------------------------------------ AWS の設定
def aws_settings(cfg: dict) -> dict:
    """向き先の環境の aws の設定（default.yaml・environments・local.yaml を重ねたもの。config.py の with_environment）。"""
    return dict(cfg.get("aws") or {})


def make_session(acfg: dict, admin: bool = False):
    """admin=False ならローカルの処理用のプロファイル（公開用に書けないロール）。設定が無ければ管理者のプロファイル。"""
    import boto3

    profile = acfg.get("profile") if admin else (acfg.get("pipeline_profile") or acfg.get("profile"))
    return boto3.Session(profile_name=profile or None, region_name=acfg.get("region") or None)


def bucket_names(acfg: dict, session) -> dict[str, str]:
    """raw・work・public のバケット名。local.yaml に raw_bucket などがあればそれ、無ければ決まり（infra と同じ）から作る。"""
    names = {role: acfg.get(f"{role}_bucket") for role in ("raw", "work", "public")}
    if all(names.values()):
        return names
    account = session.client("sts").get_caller_identity()["Account"]
    return {role: names[role] or acfg["bucket_name"].format(role=role, account_id=account) for role in names}


def local_pipeline(cfg: dict, acfg: dict):
    from .flow import Pipeline, Places
    from .records import code_commit
    from .storage import Area, S3Store

    session = make_session(acfg)
    s3 = session.client("s3")
    names = bucket_names(acfg, session)
    places = Places(
        raw=Area(S3Store(s3, names["raw"]), acfg.get("raw_prefix", ""), "raw"),
        work=Area(S3Store(s3, names["work"]), acfg.get("work_prefix", ""), "work"),
        public=None,  # ローカルの処理は公開用に書かない
    )
    return Pipeline(cfg, places, where="local", commit=code_commit())


# ------------------------------------------------------------------ 表示
def _print_result(result: dict) -> None:
    print(f"処理 {result['run_id']}（{result['action']}）：{result['status']}、モデル {result['model_version']}")
    for ride in result["rides"]:
        detail = ride["error"] or f"{ride['kind']}、窓 {ride['n_windows']}、いつもと違う振動 {ride['n_anomalies']}"
        print(f"  {ride['ride_id']}: {detail}")
    if result["status"] == "succeeded":
        print(f"画面に出すときは：python -m ct125 publish --run {result['run_id']}")


def _invoke_publish(acfg: dict, run_id: str | None) -> int:
    client = make_session(acfg, admin=True).client("lambda")
    payload = {"action": "publish", **({"run_id": run_id} if run_id else {})}
    response = client.invoke(FunctionName=acfg["pipeline_function"], Payload=json.dumps(payload).encode("utf-8"))
    body = json.loads(response["Payload"].read().decode("utf-8") or "{}")
    if response.get("FunctionError"):
        print(f"公開に失敗しました：{body.get('errorMessage', body)}", file=sys.stderr)
        return 1
    print(f"公開しました：{body.get('n_rides')} 走行（入れ替え {body.get('copied')}、外した {body.get('removed')}）")
    return 0


def _upload_sd(cfg: dict, args) -> int:
    from .device_upload import UploadError, session_folders, upload_session

    ucfg = cfg.get("upload", {})
    device_id = args.device_id or ucfg.get("device_id")
    token_path = Path(args.token_file or ucfg.get("token_file", ""))
    if not token_path.is_absolute():
        token_path = Path(cfg["_root"]) / token_path
    if not device_id or not token_path.is_file():
        print(f"機器 ID とトークンのファイルが要ります（{token_path}）。作るとき：python -m ct125 register-device --id {device_id or 'pc01'} --token-file {token_path}", file=sys.stderr)
        return 2
    token = token_path.read_text(encoding="ascii").strip()
    base_url = args.base_url or ucfg.get("base_url")
    if not base_url:
        print("送り先の URL が要ります。config/local.yaml の upload.base_url（test は environments.test.upload.base_url）に書くか、--base-url で渡してください", file=sys.stderr)
        return 2
    folders = [folder for path in args.paths for folder in session_folders(Path(path))]
    if args.resume and len(folders) != 1:
        print("--resume はフォルダーを 1 つだけ渡すときに使います", file=sys.stderr)
        return 2
    failed = 0
    for folder in folders:
        try:
            result = upload_session(base_url, device_id, token, folder, resume_ride_id=args.resume)
        except UploadError as error:
            print(f"{folder.name}: 送れませんでした：{error}", file=sys.stderr)
            failed += 1
            continue
        if result.status == "already_uploaded":
            print(f"{folder.name}: 送り終えている走行です（{result.ride_id}）。新しくは作りません")
        elif result.status == "memo_added":
            print(f"{folder.name}: 送り終えている走行 {result.ride_id} に走行メモを足しました（{', '.join(result.sent)}、{result.completed}）。AWS 側で処理がもう一度動きます")
        else:
            print(f"{folder.name}: {result.ride_id} として送りました（{len(result.sent)} ファイル、{result.completed}）。AWS 側で処理が始まります")
    return 1 if failed else 0


def _evaluate(cfg: dict, acfg: dict, args) -> int:
    from . import evaluate

    mcfg = dict(cfg.get("model", {}))
    if args.method:
        mcfg["anomaly_method"] = args.method
    if args.quantile is not None:
        mcfg["anomaly_quantile"] = args.quantile
    cfg = {**cfg, "model": mcfg}
    if args.windows_dir:
        import pandas as pd

        windows = {path.stem.split("__")[0]: pd.read_parquet(path) for path in sorted(Path(args.windows_dir).glob("*.parquet"))}
        result = evaluate.leave_one_ride_out(windows, mcfg, cfg.get("stop_speed_kmh", 5.0), args.top)
    else:
        result = local_pipeline(cfg, acfg).evaluate(args.top)
    print(evaluate.format_evaluation(result))
    return 0


def _print_ledger(cfg: dict, acfg: dict) -> int:
    pipeline = local_pipeline(cfg, acfg)
    ledger = pipeline._read_ledger()  # noqa: SLF001  表示だけ
    print(f"{'走行':24} {'名前':18} {'元の名前':10} {'分類':10} {'消した':6} 公開中の結果")
    for ride_id, entry in ledger["rides"].items():
        print(f"{ride_id:24} {entry.get('name') or '':18} {entry['original_name'] or '':10} {entry['kind'] or '':10} {'はい' if entry['deleted'] else '':6} {entry['published_run'] or ''}")
    return 0
