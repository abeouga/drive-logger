"""デバイス API が、フォルダーをまたぐ約束（リポジトリの contracts/）と合っているかを確かめる。S3・SSM には繋がない。"""

import json
import os
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from ct125_api.config import DeviceSettings
from ct125_api.domain import device, raw_upload
from ct125_api.domain.raw_upload import UploadSession, parse_file_list
from ct125_api.repositories import s3_raw_upload_repository
from ct125_api.repositories.s3_raw_upload_repository import S3RawUploadRepository

from test_device_upload import FILES, NOW, TOKEN, device_client  # noqa: F401  （HTTP の組み立てを使い回す）

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


def load(relative: str) -> dict:
    return json.loads((CONTRACTS / relative).read_text(encoding="utf-8"))


def validator(relative: str) -> Draft202012Validator:
    resources = []
    for path in CONTRACTS.glob("*/*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Draft202012Validator(load(relative), registry=Registry().with_resources(resources), format_checker=FormatChecker())


# ------------------------------------------------------------------ 定数
def test_files_match_upload_contract():
    files = load("upload/upload.json")["files"]
    assert list(raw_upload.ALLOWED_FILES) == files["allowed"]
    assert list(raw_upload.REQUIRED_FILES) == files["required"]
    assert raw_upload.MAX_FILE_BYTES == files["max_bytes"]


def test_patterns_match_common():
    common = load("common.json")
    upload = load("upload/upload.json")
    assert "^" + raw_upload.RIDE_ID_PATTERN.pattern + "$" == common["ride_id"]["pattern"]
    assert "^" + raw_upload.LOCAL_SESSION_PATTERN.pattern + "$" == common["local_session"]["pattern"]
    assert "^" + device.DEVICE_ID_PATTERN.pattern + "$" == common["device_id"]["pattern"]
    assert "^" + device.TOKEN_PATTERN.pattern + "$" == upload["auth"]["token_pattern"]


def test_marker_names_and_url_seconds_match():
    upload = load("upload/upload.json")
    assert s3_raw_upload_repository.SESSION_FILE == upload["raw_files"]["session"]["name"]
    assert s3_raw_upload_repository.COMPLETE_MARKER == upload["raw_files"]["complete"]["name"]
    saved = {name: os.environ.pop(name, None) for name in ("RAW_BUCKET", "UPLOAD_URL_SECONDS")}
    try:
        os.environ["RAW_BUCKET"] = "bucket"
        assert DeviceSettings.from_env().upload_url_seconds == upload["url_seconds"]
    finally:
        for name, value in saved.items():
            os.environ.pop(name, None)
            if value is not None:
                os.environ[name] = value


def test_notes_md_and_old_memo_names_are_accepted():
    files = [("accel.csv", 10), ("gps.csv", 10), ("meta.json", 10), ("notes.md", 10), ("memo.txt", 10), ("readme.txt", 10)]
    assert [file.name for file in parse_file_list(files)] == [name for name, _ in files]


# ------------------------------------------------------------------ 要求と応答の JSON
def test_http_requests_and_responses_match_schemas(device_client):  # noqa: F811
    client, repository = device_client
    headers = {"Authorization": f"Device d01.{TOKEN}"}
    body = load("examples/upload/start_request.json")
    validator("upload/start_request.schema.json").validate(body)

    started = client.post("/api/device/uploads", json=body, headers=headers)
    assert started.status_code == 200
    validator("upload/start_response.schema.json").validate(started.json())

    ride_id = started.json()["ride_id"]
    repository.put(ride_id, [(f["name"], f["size"]) for f in body["files"]])
    done = client.post(f"/api/device/uploads/{ride_id}/complete", headers=headers)
    validator("upload/complete_response.schema.json").validate(done.json())
    again = client.post(f"/api/device/uploads/{ride_id}/complete", headers=headers)
    validator("upload/complete_response.schema.json").validate(again.json())


def test_session_and_marker_files_match_schemas():
    session = UploadSession("ride_20261108_153012", "d01", "ride_012", parse_file_list(FILES), NOW.isoformat())
    validator("upload/upload_session.schema.json").validate(session.to_dict())

    class FakeS3:
        def put_object(self, **kwargs):
            self.key = kwargs["Key"]
            self.body = json.loads(kwargs["Body"])

    s3 = FakeS3()
    S3RawUploadRepository(s3, "bucket", "raw/").mark_complete(session)
    assert s3.key == "raw/ride_20261108_153012/upload_complete.json"
    validator("upload/upload_complete.schema.json").validate(s3.body)


# ------------------------------------------------------------------ 走行の台帳（#16・#17）
def test_ledger_rules_match_common_and_records():
    from ct125_api.domain import ledger

    common = load("common.json")
    ledger_schema = load("records/ledger.schema.json")
    assert "^" + ledger.RIDE_ID_PATTERN.pattern + "$" == ledger_schema["properties"]["rides"]["propertyNames"]["pattern"]
    assert re.fullmatch(common["ride_id"]["pattern"], "ride_20261109_010000") and ledger.RIDE_ID_PATTERN.fullmatch("ride_20261109_010000")
    assert ledger.RIDE_ID_PATTERN.fullmatch("ride_004") and re.fullmatch(common["ride_id"]["legacy_pattern"], "ride_004")
    run_schema = load("records/run.schema.json")
    assert "^" + ledger.RUN_ID_PATTERN.pattern + "$" == run_schema["properties"]["run_id"]["pattern"]
    assert "^" + ledger.MODEL_VERSION_PATTERN.pattern + "$" == run_schema["properties"]["model_version"]["pattern"]
    assert list(ledger.HIDDEN_KINDS) == common["hidden_kinds"]["value"]
    assert ledger.ADMIN_GROUP == common["admin_group"]["value"]


def test_work_repository_writes_the_ledger_conditionally():
    import boto3
    from botocore.stub import ANY, Stubber

    from ct125_api.repositories.work_repository import LedgerWriteConflict, S3WorkRepository

    client = boto3.client("s3", region_name="ap-northeast-1", aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(client) as stubber:
        stubber.add_response("put_object", {}, {"Bucket": "w", "Key": "ledger/rides.json", "Body": ANY, "ContentType": ANY, "IfMatch": '"v1"'})
        stubber.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)
        stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
        repository = S3WorkRepository(client, "w")
        repository.write_ledger({"rides": {}}, '"v1"')
        try:
            repository.write_ledger({"rides": {}}, '"v1"')
            raise AssertionError("衝突になるはず")
        except LedgerWriteConflict:
            pass
        assert repository.read_ledger() == (None, None)
