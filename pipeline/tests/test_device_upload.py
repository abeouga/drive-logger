# -*- coding: utf-8 -*-
"""PC から SD の走行を送る道具（device_upload.py）。デバイス API の代わりに、手元で小さな HTTP サーバーを立てて確かめる。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ct125.device_upload import UploadError, session_folders, upload_session
from sd_sessions import session_files


class FakeDeviceApi(BaseHTTPRequestHandler):
    """POST /api/device/uploads・PUT /put/<name>・POST /api/device/uploads/<id>/complete だけを受ける。"""

    received: dict = {}
    duplicate = False
    memo_added = False

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if self.headers["Authorization"] != "Device pc01.secret":
            return self._json(401, {"detail": "unauthorized"})
        if self.path == "/api/device/uploads":
            FakeDeviceApi.received["start"] = body
            if FakeDeviceApi.duplicate:
                return self._json(200, {"ride_id": "ride_20261109_010000", "expires_in": 900, "uploads": [], "status": "already_uploaded"})
            host = f"http://127.0.0.1:{self.server.server_port}"
            if FakeDeviceApi.memo_added:
                uploads = [{"name": "notes.md", "url": f"{host}/put/notes.md"}]
                return self._json(200, {"ride_id": "ride_20261109_010000", "expires_in": 900, "uploads": uploads, "status": "memo_added"})
            uploads = [{"name": f["name"], "url": f"{host}/put/{f['name']}"} for f in body["files"]]
            return self._json(200, {"ride_id": "ride_20261109_020000", "expires_in": 900, "uploads": uploads, "status": "new"})
        if self.path.endswith("/complete"):
            status = "already_complete" if FakeDeviceApi.duplicate else "memo_added" if FakeDeviceApi.memo_added else "complete"
            return self._json(200, {"ride_id": self.path.split("/")[-2], "status": status})
        return self._json(404, {})

    def do_PUT(self):  # noqa: N802
        FakeDeviceApi.received.setdefault("put", {})[self.path.rsplit("/", 1)[-1]] = len(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.end_headers()

    def _json(self, status, body):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def api():
    FakeDeviceApi.received = {}
    FakeDeviceApi.duplicate = False
    FakeDeviceApi.memo_added = False
    server = HTTPServer(("127.0.0.1", 0), FakeDeviceApi)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _sd(tmp_path, name="ride_013", memo="# メモ"):
    folder = tmp_path / "sessions" / name
    folder.mkdir(parents=True)
    for file_name, data in session_files("idle", seconds=70, memo=memo).items():
        (folder / file_name).write_bytes(data)
    return folder


def test_sends_every_file_and_completes(api, tmp_path):
    folder = _sd(tmp_path)
    result = upload_session(api, "pc01", "secret", folder)
    assert result.ride_id == "ride_20261109_020000" and result.status == "new" and result.completed == "complete"
    start = FakeDeviceApi.received["start"]
    assert start["local_session"] == "ride_013"
    assert {f["name"] for f in start["files"]} == {"accel.csv", "gps.csv", "events.csv", "meta.json", "notes.md"}
    assert FakeDeviceApi.received["put"] == {f["name"]: f["size"] for f in start["files"]}


def test_already_uploaded_ride_sends_nothing(api, tmp_path):
    FakeDeviceApi.duplicate = True
    result = upload_session(api, "pc01", "secret", _sd(tmp_path))
    assert result.status == "already_uploaded" and result.sent == () and result.completed == "already_complete"
    assert "put" not in FakeDeviceApi.received


def test_memo_written_later_is_added_to_the_sent_ride(api, tmp_path):
    FakeDeviceApi.memo_added = True
    result = upload_session(api, "pc01", "secret", _sd(tmp_path))
    assert result.status == "memo_added" and result.sent == ("notes.md",) and result.completed == "memo_added"
    assert list(FakeDeviceApi.received["put"]) == ["notes.md"]
    assert "notes.md" in {f["name"] for f in FakeDeviceApi.received["start"]["files"]}


def test_rejected_token_is_an_error(api, tmp_path):
    with pytest.raises(UploadError, match="401"):
        upload_session(api, "pc01", "wrong", _sd(tmp_path))


def test_session_folders_accepts_a_ride_or_the_sessions_folder(tmp_path):
    first = _sd(tmp_path, "ride_013")
    second = _sd(tmp_path, "ride_014")
    (tmp_path / "sessions" / "empty").mkdir()
    assert session_folders(first) == [first]
    assert session_folders(tmp_path / "sessions") == [first, second]
