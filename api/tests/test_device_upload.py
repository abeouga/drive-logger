"""機器からのアップロード（デバイス API）のテスト。S3・SSM には繋がない。"""

from datetime import datetime, timedelta, timezone

import boto3
import pytest
from botocore.stub import Stubber
from fastapi.testclient import TestClient

from ct125_api.config import DeviceSettings
from ct125_api.device_dependencies import get_clock, get_device_settings, get_device_token_repository, get_raw_upload_repository
from ct125_api.device_main import create_device_app
from ct125_api.domain.device import Device, DeviceCredential
from ct125_api.domain.exceptions import (
    InvalidDeviceCredentialError,
    InvalidUploadRequestError,
    UploadConflictError,
    UploadNotFoundError,
)
from ct125_api.domain.raw_upload import UploadSession
from ct125_api.repositories.s3_raw_upload_repository import S3RawUploadRepository, presigning_s3_client
from ct125_api.services.device_authenticator import DeviceAuthenticator, hash_token
from ct125_api.services.raw_upload_service import RawUploadService

JST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 8, 15, 30, 12, tzinfo=JST)
TOKEN = "t" * 43
FILES = [("accel.csv", 1000), ("gps.csv", 200), ("meta.json", 50)]
D01 = Device("d01")


# ------------------------------------------------------------------ 偽物の置き場所
class FakeTokens:
    def __init__(self, hashes):
        self._hashes = hashes

    def token_hash(self, device_id):
        return self._hashes.get(device_id)


class FakeRawUploads:
    def __init__(self):
        self.sessions: dict[str, UploadSession] = {}
        self.objects: dict[tuple[str, str], int] = {}
        self.completed: set[str] = set()
        self.fingerprints: dict[str, str] = {}

    def create_session(self, session):
        if session.ride_id in self.sessions:
            return False
        self.sessions[session.ride_id] = session
        return True

    def find_session(self, ride_id):
        return self.sessions.get(ride_id)

    def is_complete(self, ride_id):
        return ride_id in self.completed

    def upload_url(self, ride_id, file_name, expires_seconds):
        return f"https://s3.example/raw/{ride_id}/{file_name}?expires={expires_seconds}"

    def uploaded_size(self, ride_id, file_name):
        return self.objects.get((ride_id, file_name))

    def mark_complete(self, session):
        self.completed.add(session.ride_id)

    def put(self, ride_id, files):
        for name, size in files:
            self.objects[(ride_id, name)] = size

    def find_fingerprint(self, fingerprint):
        return self.fingerprints.get(fingerprint)

    def save_fingerprint(self, fingerprint, session):
        self.fingerprints[fingerprint] = session.ride_id


def _service(repository):
    return RawUploadService(repository, lambda: NOW, 900)


# ------------------------------------------------------------------ 認証
def test_parse_credential():
    credential = DeviceCredential.parse(f"Device d01.{TOKEN}")
    assert credential == DeviceCredential("d01", TOKEN)


@pytest.mark.parametrize("header", [None, "", f"Bearer d01.{TOKEN}", "Device d01", f"Device D01.{TOKEN}", "Device d01.short"])
def test_rejects_malformed_credentials(header):
    with pytest.raises(InvalidDeviceCredentialError):
        DeviceCredential.parse(header)


def test_authenticates_only_matching_token():
    authenticator = DeviceAuthenticator(FakeTokens({"d01": hash_token(TOKEN)}))
    assert authenticator.authenticate(DeviceCredential("d01", TOKEN)) == D01
    with pytest.raises(InvalidDeviceCredentialError):
        authenticator.authenticate(DeviceCredential("d01", "x" * 43))
    with pytest.raises(InvalidDeviceCredentialError):
        authenticator.authenticate(DeviceCredential("d99", TOKEN))  # 登録の無い機器


# ------------------------------------------------------------------ 受け付け
def test_start_names_the_ride_and_returns_one_url_per_file():
    repository = FakeRawUploads()
    ticket = _service(repository).start(D01, "ride_012", FILES)
    assert ticket.ride_id == "ride_20261108_153012"
    assert sorted(ticket.urls) == ["accel.csv", "gps.csv", "meta.json"]
    assert repository.sessions[ticket.ride_id].local_session == "ride_012"


def test_same_second_gets_a_suffix():
    repository = FakeRawUploads()
    first = _service(repository).start(D01, "ride_012", FILES)
    second = _service(repository).start(D01, "ride_013", FILES)
    assert (first.ride_id, second.ride_id) == ("ride_20261108_153012", "ride_20261108_153012_2")


@pytest.mark.parametrize(
    "files",
    [
        [("accel.csv", 1), ("gps.csv", 1)],                                   # meta.json が無い
        FILES + [("secret.txt", 1)],                                           # 決まりにないファイル
        FILES + [("accel.csv", 1)],                                            # 重複
        [("accel.csv", 300 * 1024 * 1024), ("gps.csv", 1), ("meta.json", 1)],  # 大きすぎる
    ],
)
def test_rejects_bad_file_lists(files):
    with pytest.raises(InvalidUploadRequestError):
        _service(FakeRawUploads()).start(D01, "ride_012", files)


def test_resume_reissues_urls_for_the_same_ride():
    repository = FakeRawUploads()
    ride_id = _service(repository).start(D01, "ride_012", FILES).ride_id
    again = _service(repository).start(D01, "ride_012", [], ride_id=ride_id)
    assert again.ride_id == ride_id and len(again.urls) == 3


def test_other_device_cannot_resume_or_complete():
    repository = FakeRawUploads()
    ride_id = _service(repository).start(D01, "ride_012", FILES).ride_id
    with pytest.raises(UploadNotFoundError):
        _service(repository).start(Device("d02"), "ride_012", [], ride_id=ride_id)
    with pytest.raises(UploadNotFoundError):
        _service(repository).complete(Device("d02"), ride_id)


# ------------------------------------------------------------------ 完了
def test_complete_checks_sizes_then_marks():
    repository = FakeRawUploads()
    service = _service(repository)
    ride_id = service.start(D01, "ride_012", FILES).ride_id
    repository.put(ride_id, [("accel.csv", 999), ("gps.csv", 200), ("meta.json", 50)])  # accel が途中まで
    with pytest.raises(UploadConflictError):
        service.complete(D01, ride_id)
    assert ride_id not in repository.completed

    repository.put(ride_id, FILES)
    assert service.complete(D01, ride_id) is True
    assert ride_id in repository.completed
    assert service.complete(D01, ride_id) is False  # やり直しても困らない


def test_cannot_resume_after_complete():
    repository = FakeRawUploads()
    service = _service(repository)
    ride_id = service.start(D01, "ride_012", FILES).ride_id
    repository.put(ride_id, FILES)
    service.complete(D01, ride_id)
    with pytest.raises(UploadConflictError):
        service.start(D01, "ride_012", [], ride_id=ride_id)


# ------------------------------------------------------------------ S3 の実装
def _s3():
    return boto3.client("s3", region_name="ap-northeast-1", aws_access_key_id="AKIAEXAMPLE", aws_secret_access_key="x")


def test_upload_url_is_sigv4_regional_scoped_and_expires():
    client = presigning_s3_client("ap-northeast-1", aws_access_key_id="AKIAEXAMPLE", aws_secret_access_key="x")
    url = S3RawUploadRepository(client, "bucket", "raw/").upload_url("ride_20261108_153012", "accel.csv", 900)
    assert url.startswith("https://bucket.s3.ap-northeast-1.amazonaws.com/raw/ride_20261108_153012/accel.csv?")
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Expires=900" in url


def test_create_session_returns_false_when_name_is_taken():
    client = _s3()
    with Stubber(client) as stubber:
        stubber.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)
        session = UploadSession("ride_20261108_153012", "d01", "ride_012", (), NOW.isoformat())
        assert S3RawUploadRepository(client, "bucket", "raw/").create_session(session) is False


# ------------------------------------------------------------------ HTTP
@pytest.fixture
def device_client():
    repository = FakeRawUploads()
    app = create_device_app()
    app.dependency_overrides[get_device_settings] = lambda: DeviceSettings("bucket", "raw/", "/ct125/devices/", 900)
    app.dependency_overrides[get_device_token_repository] = lambda: FakeTokens({"d01": hash_token(TOKEN)})
    app.dependency_overrides[get_raw_upload_repository] = lambda: repository
    app.dependency_overrides[get_clock] = lambda: (lambda: NOW)
    return TestClient(app), repository


def test_http_flow(device_client):
    client, repository = device_client
    headers = {"Authorization": f"Device d01.{TOKEN}"}
    body = {"local_session": "ride_012", "files": [{"name": n, "size": s} for n, s in FILES]}

    started = client.post("/api/device/uploads", json=body, headers=headers)
    assert started.status_code == 200
    ride_id = started.json()["ride_id"]
    assert [u["name"] for u in started.json()["uploads"]] == ["accel.csv", "gps.csv", "meta.json"]

    assert client.post(f"/api/device/uploads/{ride_id}/complete", headers=headers).status_code == 409  # まだ置いていない
    repository.put(ride_id, FILES)
    done = client.post(f"/api/device/uploads/{ride_id}/complete", headers=headers)
    assert done.json() == {"ride_id": ride_id, "status": "complete"}


def test_http_rejects_missing_or_wrong_token(device_client):
    client, _ = device_client
    body = {"local_session": "ride_012", "files": [{"name": n, "size": s} for n, s in FILES]}
    assert client.post("/api/device/uploads", json=body).status_code == 401
    wrong = {"Authorization": f"Device d01.{'x' * 43}"}
    assert client.post("/api/device/uploads", json=body, headers=wrong).status_code == 401


# ------------------------------------------------------------------ 同じ SD の走行（#14）
def test_same_sd_ride_is_not_uploaded_twice_even_from_another_device():
    repository = FakeRawUploads()
    service = _service(repository)
    first = service.start(D01, "ride_013", FILES)
    assert first.status == "new"
    repository.put(first.ride_id, FILES)
    assert service.complete(D01, first.ride_id) is True

    again = service.start(Device("pc01"), "ride_013", FILES + [("notes.md", 20)])   # PC から、メモを足して送り直した
    assert again.status == "already_uploaded" and again.ride_id == first.ride_id and again.urls == {}


def test_different_recording_or_unfinished_upload_is_a_new_ride():
    repository = FakeRawUploads()
    service = _service(repository)
    first = service.start(D01, "ride_013", FILES)
    # 送り終えていない走行は、同じ印でも新しく受け付ける（ほかの機器の途中の受け付けは使い回さない）
    assert service.start(Device("pc01"), "ride_013", FILES).ride_id != first.ride_id
    repository.put(first.ride_id, FILES)
    service.complete(D01, first.ride_id)
    other = service.start(D01, "ride_013", [("accel.csv", 1001), ("gps.csv", 200), ("meta.json", 50)])   # 大きさが違う＝別の記録
    assert other.status == "new" and other.ride_id != first.ride_id
    assert service.start(D01, "ride_014", FILES).status == "new"   # セッション名が違う


def test_complete_again_saves_the_mark_for_old_uploads():
    repository = FakeRawUploads()
    service = _service(repository)
    ticket = service.start(D01, "ride_013", FILES)
    repository.put(ticket.ride_id, FILES)
    repository.completed.add(ticket.ride_id)        # 印を付ける前に完了していた走行
    assert service.complete(D01, ticket.ride_id) is False
    assert list(repository.fingerprints.values()) == [ticket.ride_id]


def test_http_returns_status_and_empty_uploads_for_a_duplicate(device_client):
    client, repository = device_client
    headers = {"Authorization": f"Device d01.{TOKEN}"}
    body = {"local_session": "ride_012", "files": [{"name": n, "size": s} for n, s in FILES]}
    first = client.post("/api/device/uploads", json=body, headers=headers).json()
    assert first["status"] == "new"
    repository.put(first["ride_id"], FILES)
    client.post(f"/api/device/uploads/{first['ride_id']}/complete", headers=headers)
    again = client.post("/api/device/uploads", json=body, headers=headers).json()
    assert again["status"] == "already_uploaded" and again["uploads"] == [] and again["ride_id"] == first["ride_id"]
    # 機器はそのまま完了を報告し、「前に完了済み」を受け取って送り終えた印を付ける（firmware は変えなくてよい）
    assert client.post(f"/api/device/uploads/{again['ride_id']}/complete", headers=headers).json()["status"] == "already_complete"
