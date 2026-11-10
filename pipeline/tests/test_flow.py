# -*- coding: utf-8 -*-
"""処理の流れ（flow.py）を、記憶の上の置き場所（MemoryStore）で端から端まで確かめる。S3 には繋がない。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from ct125.config import load_config
from ct125.flow import LEDGER, Pipeline, Places, PublishNotAllowedError
from ct125.models import ModelFormatError, ModelLibraryMismatchError, ModelStore
from ct125.storage import Area, MemoryStore
from sd_sessions import put_ride

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"


def validator(relative: str) -> Draft202012Validator:
    resources = []
    for path in CONTRACTS.glob("*/*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    schema = json.loads((CONTRACTS / relative).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=Registry().with_resources(resources), format_checker=FormatChecker())


class Clock:
    """1 回呼ぶごとに 1 秒進む時計（run_id とモデルの版が重ならないように）。"""

    def __init__(self):
        self.now = datetime(2026, 11, 9, 3, 0, 0, tzinfo=timezone.utc)

    def __call__(self):
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def cfg():
    config = load_config()
    config["model"] = {**config["model"], "n_estimators": 50}  # テストを速くする
    return config


@pytest.fixture
def stores():
    raw, work, public = MemoryStore(), MemoryStore(), MemoryStore()
    put_ride(raw, "", "ride_20261109_010000", "idle", seed=1)
    put_ride(raw, "", "ride_20261109_011000", "ride", seed=2, memo="# 試走\n家の周り")
    put_ride(raw, "", "ride_20261109_012000", "desk", seed=3)
    return raw, work, public


def lambda_pipeline(cfg, stores, clock):
    raw, work, public = stores
    places = Places(Area(raw, "", "raw"), Area(work, "", "work"), Area(public, "datasets/shared/", "public"))
    return Pipeline(cfg, places, where="lambda", commit="abc1234", log=lambda _: None, clock=clock)


def local_pipeline(cfg, stores, clock):
    raw, work, _ = stores
    places = Places(Area(raw, "", "raw"), Area(work, "", "work"), None)
    return Pipeline(cfg, places, where="local", commit="abc1234", log=lambda _: None, clock=clock)


def read(store: MemoryStore, key: str):
    return json.loads(store.objects[key].decode("utf-8"))


def public_names(public: MemoryStore) -> set[str]:
    return {key.removeprefix("datasets/shared/") for key in public.keys("datasets/shared/")}


# ------------------------------------------------------------------ 学習し直し
def test_retrain_trains_only_on_idle_and_ride_and_publishes(cfg, stores):
    raw, work, public = stores
    result = lambda_pipeline(cfg, stores, Clock()).retrain(publish=True)

    assert result["status"] == "succeeded"
    kinds = {ride["ride_id"]: ride["kind"] for ride in result["rides"]}
    assert kinds == {"ride_20261109_010000": "idle", "ride_20261109_011000": "ride", "ride_20261109_012000": "desk"}

    version = result["model_version"]
    record = read(work, f"models/{version}/model.json")
    validator("records/model.schema.json").validate(record)
    assert [item["ride_id"] for item in record["train"]["rides"]] == ["ride_20261109_010000", "ride_20261109_011000"]
    assert record["excluded"] == [{"ride_id": "ride_20261109_012000", "reason": "desk"}]
    assert "## 気づいたこと" in work.objects[f"models/{version}/notes.md"].decode("utf-8")
    assert read(work, "models/current.json") == {"version": version}

    run = read(work, f"runs/{result['run_id']}/run.json")
    validator("records/run.schema.json").validate(run)
    assert run["where"] == "lambda" and run["commit"] == "abc1234" and run["action"] == "retrain"

    ledger = read(work, LEDGER)
    validator("records/ledger.schema.json").validate(ledger)
    assert all(entry["published_run"] == result["run_id"] for entry in ledger["rides"].values())
    assert ledger["rides"]["ride_20261109_010000"]["device_id"] == "d01"

    # 机上の走行は画面に出さない
    rides = read(public, "datasets/shared/rides.json")
    validator("app/rides.schema.json").validate(rides)
    assert [ride["id"] for ride in rides["rides"]] == ["ride_20261109_010000", "ride_20261109_011000"]
    assert rides["rides"][1]["memo"] == "# 試走\n家の周り"
    assert "ride_ride_20261109_012000.json" not in public_names(public)
    assert {"ride_ride_20261109_011000.json", "spec_ride_20261109_011000.png", "spec_ride_20261109_011000.json", "wave_ride_20261109_011000_000.json"} <= public_names(public)
    n_windows = rides["rides"][1]["n_windows"]
    waves = sorted(name for name in public_names(public) if name.startswith("wave_ride_20261109_011000"))
    assert waves == [f"wave_ride_20261109_011000_{k:03d}.json" for k in range((n_windows + 59) // 60)]  # 全部の窓を約 1 分ごとに


def test_retrain_without_usable_rides_fails_and_keeps_the_record(cfg):
    raw, work, public = MemoryStore(), MemoryStore(), MemoryStore()
    put_ride(raw, "", "ride_20261109_012000", "desk")
    with pytest.raises(ValueError, match="学習に使える走行がありません"):
        lambda_pipeline(cfg, (raw, work, public), Clock()).retrain(publish=True)
    runs = [key for key in work.keys("runs/") if key.endswith("run.json")]
    run = read(work, runs[0])
    assert run["status"] == "failed" and "学習に使える走行がありません" in run["error"]
    assert "models/current.json" not in work.objects


# ------------------------------------------------------------------ 新しい走行
def test_new_ride_is_scored_with_the_current_model_and_published(cfg, stores):
    raw, work, public = stores
    clock = Clock()
    trained = lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    put_ride(raw, "", "ride_20261109_020000", "ride_nogps", seed=4)

    result = lambda_pipeline(cfg, stores, clock).process(["ride_20261109_020000"], publish=True)

    assert result["status"] == "succeeded" and result["model_version"] == trained["model_version"]
    assert result["rides"][0]["kind"] == "ride_nogps"
    entry = read(work, LEDGER)["rides"]["ride_20261109_020000"]
    assert entry["kind"] == "ride_nogps" and entry["published_run"] == result["run_id"] and entry["local_session"] == "ride_013"
    assert "ride_20261109_020000" in [ride["id"] for ride in read(public, "datasets/shared/rides.json")["rides"]]
    validator("app/ride.schema.json").validate(read(public, "datasets/shared/ride_ride_20261109_020000.json"))


def test_failed_ride_is_recorded_and_others_are_published(cfg, stores):
    raw, work, public = stores
    clock = Clock()
    lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    put_ride(raw, "", "ride_20261109_030000", "ride", seed=5)
    raw.delete("ride_20261109_030000/gps.csv")
    put_ride(raw, "", "ride_20261109_031000", "idle", seed=6)

    result = lambda_pipeline(cfg, stores, clock).process(["ride_20261109_030000", "ride_20261109_031000"], publish=True)

    assert result["status"] == "failed"
    failed, ok = result["rides"]
    assert failed["status"] == "failed" and "gps.csv" in failed["error"]
    assert ok["status"] == "succeeded"
    run = read(work, f"runs/{result['run_id']}/run.json")
    validator("records/run.schema.json").validate(run)
    ledger = read(work, LEDGER)["rides"]
    assert ledger["ride_20261109_030000"]["published_run"] is None and ledger["ride_20261109_030000"]["runs"] == [result["run_id"]]
    assert ledger["ride_20261109_031000"]["published_run"] == result["run_id"]


# ------------------------------------------------------------------ ローカルの処理と公開
def test_local_run_does_not_change_the_screen_until_published(cfg, stores):
    raw, work, public = stores
    clock = Clock()
    trained = lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    before = dict(public.objects)

    local = local_pipeline(cfg, stores, clock).process(["ride_20261109_011000"], publish=False)

    assert read(work, f"runs/{local['run_id']}/run.json")["where"] == "local"
    assert public.objects == before                                   # 画面は変わらない
    entry = read(work, LEDGER)["rides"]["ride_20261109_011000"]
    assert entry["published_run"] == trained["run_id"] and entry["runs"][0] == local["run_id"]
    with pytest.raises(PublishNotAllowedError):
        local_pipeline(cfg, stores, clock).publish(local["run_id"])

    lambda_pipeline(cfg, stores, clock).publish(local["run_id"])       # Lambda に頼んで公開する
    assert read(work, LEDGER)["rides"]["ride_20261109_011000"]["published_run"] == local["run_id"]
    published = work.objects[f"runs/{local['run_id']}/rides/ride_20261109_011000/app/ride_ride_20261109_011000.json"]
    assert public.objects["datasets/shared/ride_ride_20261109_011000.json"] == published


def test_local_retrain_does_not_switch_the_model(cfg, stores):
    raw, work, public = stores
    clock = Clock()
    trained = lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    local = local_pipeline(cfg, stores, clock).retrain(publish=False)
    assert local["model_version"] != trained["model_version"]
    assert read(work, "models/current.json") == {"version": trained["model_version"]}
    lambda_pipeline(cfg, stores, clock).publish(local["run_id"])
    assert read(work, "models/current.json") == {"version": local["model_version"]}


def test_publishing_an_older_run_rolls_back(cfg, stores):
    raw, work, public = stores
    clock = Clock()
    first = lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    raw.put("ride_20261109_011000/notes.md", "書き直したメモ".encode("utf-8"), "text/markdown")
    second = lambda_pipeline(cfg, stores, clock).process(["ride_20261109_011000"], publish=True)
    memo = lambda: next(r["memo"] for r in read(public, "datasets/shared/rides.json")["rides"] if r["id"] == "ride_20261109_011000")
    assert memo() == "書き直したメモ"
    assert read(work, LEDGER)["rides"]["ride_20261109_011000"]["runs"] == [second["run_id"], first["run_id"]]

    lambda_pipeline(cfg, stores, clock).publish(first["run_id"])        # 前の結果に戻す
    assert memo() == "# 試走\n家の周り"


def test_republishing_removes_wave_files_that_are_no_longer_made(cfg, stores):
    raw, work, public = stores
    clock = Clock()
    lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    public.put("datasets/shared/wave_ride_20261109_011000.json", b"{}", "application/json")      # 1 走行 1 つだった頃の形
    public.put("datasets/shared/wave_ride_20261109_011000_999.json", b"{}", "application/json")  # 今は作られない分
    public.put("datasets/shared/wave_ride_20261109_0110001_000.json", b"{}", "application/json") # 名前の似た別の走行は消さない
    lambda_pipeline(cfg, stores, clock).process(["ride_20261109_011000"], publish=True)
    names = public_names(public)
    assert "wave_ride_20261109_011000.json" not in names
    assert "wave_ride_20261109_011000_999.json" not in names
    assert "wave_ride_20261109_011000_000.json" in names
    assert "wave_ride_20261109_0110001_000.json" in names


def test_deleted_ride_is_hidden_and_not_trained(cfg, stores):
    raw, work, public = stores
    clock = Clock()
    lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    ledger = read(work, LEDGER)
    ledger["rides"]["ride_20261109_010000"]["deleted"] = True              # データ API が台帳を書き換えたことにする
    work.put(LEDGER, json.dumps(ledger).encode("utf-8"), "application/json")

    lambda_pipeline(cfg, stores, clock).publish()
    assert [ride["id"] for ride in read(public, "datasets/shared/rides.json")["rides"]] == ["ride_20261109_011000"]
    assert not any("ride_20261109_010000" in name for name in public_names(public))
    assert raw.get("ride_20261109_010000/accel.csv") is not None          # 生データは残す

    result = lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    record = read(work, f"models/{result['model_version']}/model.json")
    assert {"ride_id": "ride_20261109_010000", "reason": "deleted"} in record["excluded"]


# ------------------------------------------------------------------ モデルの版
def test_model_trained_with_other_library_versions_is_refused(cfg, stores):
    raw, work, public = stores
    result = lambda_pipeline(cfg, stores, Clock()).retrain(publish=True)
    key = f"models/{result['model_version']}/model.json"
    record = read(work, key)
    record["libraries"]["scikit-learn"] = "0.0.1"
    work.put(key, json.dumps(record).encode("utf-8"), "application/json")
    with pytest.raises(ModelLibraryMismatchError, match="scikit-learn"):
        ModelStore(Area(work, "", "work")).load_current()


def test_model_is_saved_with_skops_and_scores_the_same_after_loading(cfg, stores):
    raw, work, public = stores
    result = lambda_pipeline(cfg, stores, Clock()).retrain(publish=True)
    version = result["model_version"]
    names = {key.rsplit("/", 1)[1] for key in work.objects if key.startswith(f"models/{version}/")}
    assert names == {"baseline.json", "isolation_forest.skops", "model.json", "notes.md"}
    assert "skops" in read(work, f"models/{version}/model.json")["libraries"]

    from ct125 import model
    loaded = ModelStore(Area(work, "", "work")).load(version)
    df = pd.DataFrame({c: np.linspace(-1, 1, 20) for c in model.IF_FEATURES})
    forest = model.load_forest(work.objects[f"models/{version}/isolation_forest.skops"])
    pd.testing.assert_frame_equal(model.apply_isolation_forest(df, loaded.forest), model.apply_isolation_forest(df, forest))


def test_old_model_saved_only_as_pickle_is_refused(cfg, stores):
    raw, work, public = stores
    result = lambda_pipeline(cfg, stores, Clock()).retrain(publish=True)
    version = result["model_version"]
    del work.objects[f"models/{version}/isolation_forest.skops"]
    work.put(f"models/{version}/isolation_forest.pkl", b"old pickle (not read)", "application/octet-stream")
    with pytest.raises(ModelFormatError, match="retrain"):
        ModelStore(Area(work, "", "work")).load_current()


# ------------------------------------------------------------------ モデルの切り替え
def test_use_model_rescores_every_ride_with_the_chosen_version(cfg, stores):
    raw, work, public = stores
    clock = Clock()
    first = lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    second = lambda_pipeline(cfg, stores, clock).retrain(publish=True)
    raw.put("_uploads/abc.json", b"{}", "application/json")              # 走行でないフォルダーは数えない
    assert read(work, "models/current.json") == {"version": second["model_version"]}

    result = lambda_pipeline(cfg, stores, clock).use_model(first["model_version"])

    assert read(work, "models/current.json") == {"version": first["model_version"]}
    assert result["action"] == "process" and result["model_version"] == first["model_version"]
    assert sorted(r["ride_id"] for r in result["rides"]) == ["ride_20261109_010000", "ride_20261109_011000", "ride_20261109_012000"]
    assert all(entry["published_run"] == result["run_id"] for entry in read(work, LEDGER)["rides"].values())
    with pytest.raises(PublishNotAllowedError):
        local_pipeline(cfg, stores, clock).use_model(first["model_version"])
