# -*- coding: utf-8 -*-
"""PC から SD の走行を送る（`python -m ct125 upload-sd`）。ESP32 と同じ入口（デバイス API）を通し、走行 ID はサーバーが付ける。

手順（ESP32 の firmware も同じ。contracts/upload/upload.json）：
  1. POST /api/device/uploads                    送るファイルと大きさ → 走行 ID とファイルごとの PUT 用 URL
     同じ SD の走行を送り終えていれば status=already_uploaded（送るファイルは無い。#14）
  2. 各 URL に HTTP PUT                          ファイルを流しながら送る
  3. POST /api/device/uploads/<走行 ID>/complete 大きさを確かめ、AWS 側の処理が始まる
途中で切れたら、1 を「前回の走行 ID」付きで呼び直すと URL が出し直される（resume）。
標準ライブラリだけで動く。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

# 送るファイル（contracts/upload/upload.json の files.allowed。tests/test_contracts.py で突き合わせる）。無いファイルは飛ばす
SEND_FILES = ["accel.csv", "gps.csv", "events.csv", "status.csv", "meta.json", "notes.md", "memo.txt", "readme.txt"]


class UploadError(RuntimeError):
    """デバイス API が断った、または送れなかった。"""


@dataclass(frozen=True)
class UploadResult:
    local_session: str
    ride_id: str
    status: str            # new・resumed・already_uploaded
    sent: tuple[str, ...]  # 送ったファイル（already_uploaded なら空）
    completed: str         # complete（今回完了）・already_complete（前に完了済み）


def session_folders(path: Path) -> list[Path]:
    """SD の走行のフォルダー（accel.csv があるもの）。path が /sessions のような親フォルダーなら、その下を名前の順に。"""
    path = Path(path)
    if (path / "accel.csv").exists():
        return [path]
    return sorted(child for child in path.iterdir() if child.is_dir() and (child / "accel.csv").exists())


def upload_session(base_url: str, device_id: str, token: str, folder: Path, local_session: str | None = None, resume_ride_id: str | None = None) -> UploadResult:
    """1 走行分を送る。local_session は SD の上の走行のフォルダー名（省くとフォルダー名）。"""
    auth = f"Device {device_id}.{token}"
    files = [path for name in SEND_FILES if (path := folder / name).exists()]
    session = local_session or folder.name
    body = {"local_session": session, "files": [{"name": p.name, "size": p.stat().st_size} for p in files]}
    if resume_ride_id:
        body["ride_id"] = resume_ride_id
    ticket = _post_json(f"{base_url}/api/device/uploads", auth, body)
    urls = {upload["name"]: upload["url"] for upload in ticket["uploads"]}
    sent = []
    for path in files:
        if path.name in urls:
            _put_file(urls[path.name], path)
            sent.append(path.name)
    done = _post_json(f"{base_url}/api/device/uploads/{ticket['ride_id']}/complete", auth, {})
    return UploadResult(session, ticket["ride_id"], ticket.get("status", "new"), tuple(sent), done["status"])


def _put_file(url: str, path: Path) -> None:
    """ファイルを読みながら PUT する（全部をメモリに載せない。ESP32 も同じ）。"""
    with path.open("rb") as stream:
        request = urllib.request.Request(url, data=stream, method="PUT", headers={"Content-Length": str(path.stat().st_size)})
        with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310  デバイス API が出した https の URL だけ
            if response.status != 200:
                raise UploadError(f"{path.name} の PUT が失敗しました（HTTP {response.status}）")


def _post_json(url: str, auth: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST", headers={"Authorization": auth, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise UploadError(f"{url} が HTTP {error.code} を返しました：{detail}") from error
