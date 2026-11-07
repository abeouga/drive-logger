# -*- coding: utf-8 -*-
"""AWS 上の処理（ct125/cloud/）と、学習・推論の分割のテスト。S3・SSM には繋がない。"""
import io as stdio
import json

import boto3
import numpy as np
import pandas as pd
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from ct125 import model
from ct125.cloud.commands import ProcessRides, RetrainAll, parse_command, ride_id_from_marker_key
from ct125.cloud.private_points import PrivatePointsUnavailableError, load_private_settings, to_parameter_value
from ct125.cloud.rides_index import save_summary, upsert_summary
from ct125.cloud.s3_store import S3Store, WriteConflictError


# ------------------------------------------------------------------ イベント → 命令
def _s3_event(*keys):
    return {"Records": [{"s3": {"object": {"key": key}}} for key in keys]}


def test_marker_upload_becomes_process_command():
    command = parse_command(_s3_event("raw/ride_010/upload_complete.json"), "raw/")
    assert command == ProcessRides(("ride_010",))


def test_same_ride_twice_is_processed_once_and_other_keys_are_ignored():
    event = _s3_event("raw/ride_010/upload_complete.json", "raw/ride_010/upload_complete.json", "raw/ride_011/accel.csv")
    assert parse_command(event, "raw/") == ProcessRides(("ride_010",))


@pytest.mark.parametrize(
    "key",
    ["raw/upload_complete.json", "raw/a/b/upload_complete.json", "processed/ride_010/upload_complete.json", "raw/ride 1/upload_complete.json"],
)
def test_unexpected_marker_keys_are_ignored(key):
    assert ride_id_from_marker_key(key, "raw/") is None


def test_manual_commands():
    assert parse_command({"action": "retrain"}, "raw/") == RetrainAll()
    assert parse_command({"action": "process", "ride_ids": ["ride_004"]}, "raw/") == ProcessRides(("ride_004",))
    with pytest.raises(ValueError):
        parse_command({"action": "process", "ride_ids": ["../x"]}, "raw/")
    with pytest.raises(ValueError):
        parse_command({"action": "delete"}, "raw/")


# ------------------------------------------------------------------ rides.json の差し替え
def test_upsert_adds_and_replaces_in_id_order():
    doc = {"rides": [{"id": "ride_002", "v": 1}, {"id": "ride_001", "v": 1}]}
    added = upsert_summary(doc, {"id": "ride_003", "v": 1})
    assert [r["id"] for r in added["rides"]] == ["ride_001", "ride_002", "ride_003"]
    replaced = upsert_summary(added, {"id": "ride_002", "v": 2})
    assert [r["v"] for r in replaced["rides"]] == [1, 2, 1]
    assert doc["rides"][0]["v"] == 1  # 元は変えない
    assert upsert_summary(None, {"id": "ride_001"})["rides"] == [{"id": "ride_001"}]


class _ConflictOnceStore:
    """1 回目の書き込みだけ「ほかの処理が先に書いた」ことにする置き場所。"""

    def __init__(self):
        self.document = {"rides": [{"id": "ride_001"}]}
        self.etag = '"v1"'
        self.writes = 0

    def read_json(self, key):
        return self.document, self.etag

    def write_json(self, key, document, expected_etag=None, must_not_exist=False):
        self.writes += 1
        if self.writes == 1:
            self.document = {"rides": [{"id": "ride_001"}, {"id": "ride_002"}]}  # 割り込み
            self.etag = '"v2"'
            raise WriteConflictError(key)
        assert expected_etag == '"v2"'
        self.document = document


def test_save_summary_retries_after_conflict_and_keeps_other_writer():
    store = _ConflictOnceStore()
    saved = save_summary(store, "app/rides.json", {"id": "ride_003"})
    assert [r["id"] for r in saved["rides"]] == ["ride_001", "ride_002", "ride_003"]
    assert store.writes == 2


def _stubbed_s3():
    client = boto3.client("s3", region_name="ap-northeast-1", aws_access_key_id="x", aws_secret_access_key="x")
    return client, Stubber(client)


def test_write_json_sends_if_match_and_maps_412_to_conflict():
    client, stubber = _stubbed_s3()
    stubber.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)
    with stubber:
        with pytest.raises(WriteConflictError):
            S3Store(client, "bucket").write_json("app/rides.json", {"rides": []}, expected_etag='"v1"')


def test_read_json_returns_none_when_missing():
    client, stubber = _stubbed_s3()
    stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    with stubber:
        assert S3Store(client, "bucket").read_json("app/rides.json") == (None, None)


def test_read_json_returns_document_and_etag():
    client, stubber = _stubbed_s3()
    body = json.dumps({"rides": []}).encode()
    stubber.add_response("get_object", {"Body": StreamingBody(stdio.BytesIO(body), len(body)), "ETag": '"abc"'})
    with stubber:
        assert S3Store(client, "bucket").read_json("app/rides.json") == ({"rides": []}, '"abc"')


# ------------------------------------------------------------------ マスクする地点
def test_parameter_value_keeps_only_coordinates():
    local = {"home": {"lat": 32.1, "lon": 130.2}, "places": [{"name": "歯医者", "lat": 32.3, "lon": 130.4}, {"name": "座標なし"}]}
    value = json.loads(to_parameter_value(local))
    assert value == {"home": {"lat": 32.1, "lon": 130.2}, "places": [{"lat": 32.3, "lon": 130.4}]}
    assert "歯医者" not in to_parameter_value(local)


def test_missing_parameter_stops_processing():
    ssm = boto3.client("ssm", region_name="ap-northeast-1", aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(ssm) as stubber:
        stubber.add_client_error("get_parameter", service_error_code="ParameterNotFound", http_status_code=400)
        with pytest.raises(PrivatePointsUnavailableError):
            load_private_settings(ssm, "/ct125/private-points")


def test_empty_parameter_stops_processing():
    ssm = boto3.client("ssm", region_name="ap-northeast-1", aws_access_key_id="x", aws_secret_access_key="x")
    with Stubber(ssm) as stubber:
        stubber.add_response("get_parameter", {"Parameter": {"Value": json.dumps({"home": None, "places": []})}})
        with pytest.raises(PrivatePointsUnavailableError):
            load_private_settings(ssm, "/ct125/private-points")


# ------------------------------------------------------------------ 学習と推論の分割
def _feature_windows(n=400, seed=0):
    rng = np.random.default_rng(seed)
    speed = rng.uniform(0, 40, n)
    frame = pd.DataFrame({"speed_kmh": speed, "has_gps": True, "is_edge": False, "is_clipped": False})
    for name in model.IF_FEATURES:
        frame[name] = rng.normal(0, 1, n)
    frame["log_rms"] = -2 + speed / 20 + rng.normal(0, 0.1, n)
    return frame


def test_apply_models_matches_score_windows():
    windows = _feature_windows()
    mcfg = {"contamination": 0.05, "n_estimators": 50, "random_state": 0}
    scored, _, _ = model.score_windows(windows, mcfg)
    baseline, forest = model.fit_models(windows, mcfg)
    applied = model.apply_models(windows, baseline, forest, mcfg)
    pd.testing.assert_frame_equal(scored, applied)


def test_apply_models_on_a_single_new_ride():
    train = _feature_windows(seed=0)
    new_ride = _feature_windows(n=50, seed=1)
    mcfg = {"contamination": 0.05, "n_estimators": 50, "random_state": 0}
    baseline, forest = model.fit_models(train, mcfg)
    scored = model.apply_models(new_ride, baseline, forest, mcfg)
    assert len(scored) == 50
    assert scored["score_if"].notna().all()
    assert {"z_speed", "is_anomaly_z", "is_stopped", "is_anomaly_if"} <= set(scored.columns)
