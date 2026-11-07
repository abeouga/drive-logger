# -*- coding: utf-8 -*-
"""ESP32 のふりをして、1 走行分を S3 に送る（C：機器から S3 へ直接送る）。

ファームウェアと同じ手順を踏む「お手本」。サーバー側を作ったときの確認と、ファームウェアを書くときの見本に使う。
標準ライブラリだけで動く。

    python tools/device_upload_simulator.py data/raw/ride_004 --device-id d01 --token-file d01.token

手順（ESP32 も同じ）：
  1. POST /api/device/uploads            送るファイルと大きさ → 走行名とファイルごとの PUT 用 URL
  2. 各 URL に HTTP PUT                  ファイルを流しながら送る（Content-Length を付ける）
  3. POST /api/device/uploads/<走行名>/complete  サーバーが大きさを確かめ、AWS 側の自動処理が始まる
途中で切れたら、1 を「前回の走行名」付きで呼び直すと URL が出し直される（--resume）。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

SEND_FILES = ["accel.csv", "gps.csv", "events.csv", "status.csv", "meta.json", "memo.txt"]
DEFAULT_BASE_URL = "https://drive.herdio-system.com"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ride_dir = Path(args.ride_dir)
    token = Path(args.token_file).read_text(encoding="ascii").strip()
    auth = f"Device {args.device_id}.{token}"
    files = [path for name in SEND_FILES if (path := ride_dir / name).exists()]

    ticket = start_upload(args.base_url, auth, ride_dir.name, files, args.resume)
    print(f"受け付け：{ticket['ride_id']}（URL の期限 {ticket['expires_in']} 秒）")
    urls = {upload["name"]: upload["url"] for upload in ticket["uploads"]}
    for path in files:
        put_file(urls[path.name], path)
        print(f"  送信：{path.name}（{path.stat().st_size / 1024:.0f} KB）")
    result = complete_upload(args.base_url, auth, ticket["ride_id"])
    print(f"完了：{result['ride_id']}（{result['status']}）。AWS 側で処理が始まります")
    return 0


def start_upload(base_url: str, auth: str, local_session: str, files: list[Path], resume_ride_id: str | None) -> dict:
    body = {"local_session": local_session, "files": [{"name": p.name, "size": p.stat().st_size} for p in files]}
    if resume_ride_id:
        body["ride_id"] = resume_ride_id
    return _post_json(f"{base_url}/api/device/uploads", auth, body)


def put_file(url: str, path: Path) -> None:
    """ファイルを読みながら PUT する（全部をメモリに載せない。ESP32 も同じ）。"""
    with path.open("rb") as stream:
        request = urllib.request.Request(url, data=stream, method="PUT", headers={"Content-Length": str(path.stat().st_size)})
        with urllib.request.urlopen(request, timeout=300) as response:
            if response.status != 200:
                raise RuntimeError(f"{path.name} の PUT が失敗しました（HTTP {response.status}）")


def complete_upload(base_url: str, auth: str, ride_id: str) -> dict:
    return _post_json(f"{base_url}/api/device/uploads/{ride_id}/complete", auth, {})


def _post_json(url: str, auth: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={"Authorization": auth, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise SystemExit(f"{url} が HTTP {error.code} を返しました：{detail}") from error


def _parse_args(argv):
    parser = argparse.ArgumentParser(description="ESP32 のふりをして 1 走行分を S3 に送る")
    parser.add_argument("ride_dir", help="SD の走行フォルダー（accel.csv などがある所）")
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--token-file", required=True, help="register-device --token-file で作ったファイル")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--resume", default=None, metavar="RIDE_ID", help="途中で切れたとき：前回の走行名")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
