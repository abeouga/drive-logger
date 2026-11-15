# -*- coding: utf-8 -*-
"""古い名前（ride_NNN）で生データのバケットに直接置かれた走行を、デバイス API から上げ直す（#15）。

1. 生データのバケットの ride_NNN/ を一時フォルダーに落とし、PC の機器（pc01）としてデバイス API から送る
   → サーバーが新しい走行 ID（ride_<日時>）を付け、処理の Lambda が処理して公開する
2. 新しい走行の生データが、元とバイト単位で同じか確かめる（ファイルごとの MD5）
3. 処理が終わるのを待ち、台帳の新しい走行に元の名前（original_name）を残し、古い ride_NNN を台帳から外す
4. 生データのバケットの古い ride_NNN/ を消す（新しい走行に同じ中身がある。バケットは古い版を 30 日残す）
5. 処理の Lambda に学習し直しを頼む（新しい走行 ID で学習し、公開し直す）

使い方（pipeline/ で。管理者のプロファイル（config/local.yaml の aws.profile）と、PC の機器のトークン config/pc01.token が要る）：
    .venv/Scripts/python.exe tools/reupload_legacy.py           何をするかを表示するだけ
    .venv/Scripts/python.exe tools/reupload_legacy.py --run     実行する
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ct125.cli import aws_settings, bucket_names, make_session  # noqa: E402
from ct125.config import load_config  # noqa: E402
from ct125.device_upload import SEND_FILES, upload_session  # noqa: E402
from ct125.storage import Area, S3Store, WriteConflictError  # noqa: E402

LEGACY = re.compile(r"ride_[0-9]{3}")
LEDGER = "ledger/rides.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run", action="store_true", help="実行する（付けなければ表示するだけ）")
    parser.add_argument("--wait-seconds", type=int, default=600, help="処理の Lambda を待つ長さ")
    args = parser.parse_args(argv)

    cfg = load_config()
    acfg = aws_settings(cfg)
    session = make_session(acfg, admin=True)
    s3 = session.client("s3")
    names = bucket_names(acfg, session)
    raw = Area(S3Store(s3, names["raw"]), acfg.get("raw_prefix", ""), "raw")
    work = Area(S3Store(s3, names["work"]), acfg.get("work_prefix", ""), "work")
    ucfg = cfg["upload"]
    if not ucfg.get("base_url"):
        print("送り先の URL が要ります（config/local.yaml の upload.base_url）", file=sys.stderr)
        return 2
    token =(ROOT / ucfg["token_file"]).read_text(encoding="ascii").strip()

    legacy = [name for name in raw.folders() if LEGACY.fullmatch(name)]
    print(f"上げ直す走行：{', '.join(legacy) or 'なし'}（送り先 {ucfg['base_url']}、機器 {ucfg['device_id']}）")
    if not args.run or not legacy:
        return 0

    mapping: dict[str, str] = {}
    for old in legacy:
        with tempfile.TemporaryDirectory(prefix="ct125-reupload-") as tmp:
            folder = Path(tmp) / old
            folder.mkdir()
            for relative in raw.keys(f"{old}/"):
                name = relative.split("/", 1)[1]
                if name in SEND_FILES:
                    (folder / name).write_bytes(raw.get(relative))
            result = upload_session(ucfg["base_url"], ucfg["device_id"], token, folder, local_session=old)
            _check_same(s3, names["raw"], raw, old, result.ride_id, folder)
        mapping[old] = result.ride_id
        print(f"{old} → {result.ride_id}（{result.status}、{len(result.sent)} ファイル、中身は元と同じ）")

    _wait_for_processing(work, mapping, args.wait_seconds)
    _update_ledger(work, mapping)
    for old in mapping:
        for relative in raw.keys(f"{old}/"):
            raw.delete(relative)
        print(f"生データのバケットの {old}/ を消しました（新しい走行 {mapping[old]} に同じ中身がある）")

    function = acfg["pipeline_function"]
    session.client("lambda").invoke(FunctionName=function, InvocationType="Event", Payload=json.dumps({"action": "retrain"}).encode("utf-8"))
    print(f"{function} に学習し直しを頼みました（新しい走行 ID で学習し、公開し直す。数分かかる）")
    print(json.dumps(mapping, ensure_ascii=False, indent=1))
    return 0


def _check_same(s3, bucket: str, raw: Area, old: str, new: str, folder: Path) -> None:
    """新しい走行の生データが、送ったファイル（＝元の生データ）とバイト単位で同じか。PUT は 1 回で送るので ETag は MD5。"""
    for path in sorted(folder.iterdir()):
        md5 = hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest()
        etag = s3.head_object(Bucket=bucket, Key=raw.key(f"{new}/{path.name}"))["ETag"].strip('"')
        if etag != md5:
            raise SystemExit(f"{new}/{path.name} が元（{old}/{path.name}）と違います。止めます")


def _wait_for_processing(work: Area, mapping: dict[str, str], wait_seconds: int) -> None:
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        ledger = work.read_json(LEDGER) or {"rides": {}}
        waiting = [new for new in mapping.values() if not (ledger["rides"].get(new) or {}).get("published_run")]
        if not waiting:
            print("処理の Lambda が新しい走行をすべて処理しました")
            return
        print(f"処理を待っています：{len(waiting)} 走行")
        time.sleep(10)
    raise SystemExit("処理の Lambda が時間内に終わりませんでした（Lambda のログを確かめる）。台帳と古い生データはそのまま")


def _update_ledger(work: Area, mapping: dict[str, str]) -> None:
    for _ in range(5):
        ledger, etag = work.read_json_tagged(LEDGER)
        for old, new in mapping.items():
            ledger["rides"][new]["original_name"] = old
            ledger["rides"].pop(old, None)
        try:
            work.write_json_if(LEDGER, ledger, etag)
            print(f"台帳：新しい走行に元の名前を残し、古い {len(mapping)} 走行を外しました")
            return
        except WriteConflictError:
            time.sleep(2)
    raise SystemExit("台帳を書けませんでした（ほかの処理が書き換え続けている）")


if __name__ == "__main__":
    sys.exit(main())
