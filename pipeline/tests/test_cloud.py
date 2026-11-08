# -*- coding: utf-8 -*-
"""Lambda の入口（ct125/cloud/）・保存の口（storage.py）・学習と推論の分割のテスト。S3 には繋がない。"""
import io as stdio
import json

import boto3
import numpy as np
import pandas as pd
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

from ct125 import model
from ct125.cloud.commands import ProcessRides, Publish, RetrainAll, UseModel, parse_command, ride_id_from_marker_key
from ct125.cloud.settings import CloudSettings
from ct125.storage import Area, MemoryStore, S3Store, WriteConflictError


# ------------------------------------------------------------------ イベント → 命令
def _s3_event(*keys):
    return {"Records": [{"s3": {"object": {"key": key}}} for key in keys]}


def test_marker_upload_becomes_process_command():
    assert parse_command(_s3_event("ride_20261108_011304/upload_complete.json"), "") == ProcessRides(("ride_20261108_011304",))
    assert parse_command(_s3_event("raw/ride_010/upload_complete.json"), "raw/") == ProcessRides(("ride_010",))


def test_same_ride_twice_is_processed_once_and_other_keys_are_ignored():
    event = _s3_event("ride_010/upload_complete.json", "ride_010/upload_complete.json", "ride_011/accel.csv")
    assert parse_command(event, "") == ProcessRides(("ride_010",))


@pytest.mark.parametrize("key", ["upload_complete.json", "a/b/upload_complete.json", "processed/ride_010/upload_complete.json", "ride 1/upload_complete.json"])
def test_unexpected_marker_keys_are_ignored(key):
    assert ride_id_from_marker_key(key, "") is None


def test_manual_commands():
    assert parse_command({"action": "retrain"}, "") == RetrainAll()
    assert parse_command({"action": "process", "ride_ids": ["ride_004"]}, "") == ProcessRides(("ride_004",))
    assert parse_command({"action": "publish"}, "") == Publish(None)
    assert parse_command({"action": "publish", "run_id": "20261109T031500Z-3f9a1c"}, "") == Publish("20261109T031500Z-3f9a1c")
    assert parse_command({"action": "use_model", "version": "20261109-031500"}, "") == UseModel("20261109-031500")
    for bad in ({"action": "process", "ride_ids": ["../x"]}, {"action": "delete"}, {"action": "publish", "run_id": "../x"}, {"action": "use_model"}, {"action": "use_model", "version": "x"}):
        with pytest.raises(ValueError):
            parse_command(bad, "")


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("RAW_BUCKET", "r")
    monkeypatch.setenv("WORK_BUCKET", "w")
    monkeypatch.setenv("PUBLIC_BUCKET", "p")
    settings = CloudSettings.from_env()
    assert (settings.raw_prefix, settings.work_prefix, settings.public_prefix) == ("", "", "datasets/shared/")
    monkeypatch.delenv("WORK_BUCKET")
    with pytest.raises(RuntimeError, match="WORK_BUCKET"):
        CloudSettings.from_env()


# ------------------------------------------------------------------ 保存の口
def _stubbed_s3():
    client = boto3.client("s3", region_name="ap-northeast-1", aws_access_key_id="x", aws_secret_access_key="x")
    return client, Stubber(client)


def test_s3_put_sends_if_match_and_maps_412_to_conflict():
    client, stubber = _stubbed_s3()
    stubber.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412,
                             expected_params={"Bucket": "bucket", "Key": "ledger/rides.json", "Body": b"{}", "ContentType": "application/json", "IfMatch": '"v1"'})
    with stubber:
        with pytest.raises(WriteConflictError):
            S3Store(client, "bucket").put("ledger/rides.json", b"{}", "application/json", if_match='"v1"')


def test_s3_get_returns_none_when_missing_and_body_with_etag():
    client, stubber = _stubbed_s3()
    stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    body = json.dumps({"rides": {}}).encode()
    stubber.add_response("get_object", {"Body": StreamingBody(stdio.BytesIO(body), len(body)), "ETag": '"abc"'})
    with stubber:
        store = S3Store(client, "bucket")
        assert store.get("ledger/rides.json") is None
        assert store.get("ledger/rides.json") == (body, '"abc"')


def test_memory_store_behaves_like_s3_conditional_writes():
    area = Area(MemoryStore(), "w/")
    area.write_json_if("ledger.json", {"v": 1}, None)                # 無いときだけ書く
    with pytest.raises(WriteConflictError):
        area.write_json_if("ledger.json", {"v": 2}, None)            # もうある
    document, etag = area.read_json_tagged("ledger.json")
    area.write_json_if("ledger.json", {"v": 2}, etag)                # 読んだときのまま
    with pytest.raises(WriteConflictError):
        area.write_json_if("ledger.json", {"v": 3}, etag)            # 間に書き換わった
    assert area.read_json("ledger.json") == {"v": 2}
    assert area.store.keys("w/") == ["w/ledger.json"]


def test_area_lists_relative_keys_and_folders():
    area = Area(MemoryStore({"raw/ride_001/accel.csv": b"", "raw/ride_001/gps.csv": b"", "raw/ride_002/accel.csv": b"", "other/x": b""}), "raw/")
    assert area.folders() == ["ride_001", "ride_002"]
    assert area.keys("ride_001/") == ["ride_001/accel.csv", "ride_001/gps.csv"]


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


# ------------------------------------------------------------------ コンテナに入れるライブラリ
def test_lambda_entry_does_not_need_plotting_libraries():
    """Lambda のコンテナには folium・plotly を入れない（deploy/lambda/requirements.txt）。入口がそれらを読まないこと。"""
    import importlib
    import sys

    for name in ("ct125.export", "ct125.spectro", "ct125.flow", "ct125.cloud.lambda_handler"):
        importlib.import_module(name)
    assert "folium" not in sys.modules and "plotly" not in sys.modules


# ------------------------------------------------------------------ ローカルの CLI の設定
def test_cli_bucket_names_follow_the_rule_or_local_settings():
    from ct125 import cli

    class FakeSession:
        def client(self, name):
            assert name == "sts"
            return type("Sts", (), {"get_caller_identity": lambda self: {"Account": "123456789012"}})()

    acfg = {"bucket_name": "ct125-logger-{role}-{account_id}"}
    assert cli.bucket_names(acfg, FakeSession()) == {role: f"ct125-logger-{role}-123456789012" for role in ("raw", "work", "public")}
    given = {**acfg, "raw_bucket": "r", "work_bucket": "w", "public_bucket": "p"}
    assert cli.bucket_names(given, None) == {"raw": "r", "work": "w", "public": "p"}


def test_cli_local_pipeline_cannot_publish(monkeypatch):
    from ct125 import cli
    from ct125.config import load_config
    from ct125.flow import PublishNotAllowedError

    class FakeSession:
        def client(self, name):
            return boto3.client(name, region_name="ap-northeast-1", aws_access_key_id="x", aws_secret_access_key="x")

    monkeypatch.setattr(cli, "make_session", lambda acfg, admin=False: FakeSession())
    acfg = {**cli.aws_settings(load_config()), "raw_bucket": "r", "work_bucket": "w", "public_bucket": "p"}
    pipeline = cli.local_pipeline(load_config(), acfg)
    with pytest.raises(PublishNotAllowedError):
        pipeline.publish()
