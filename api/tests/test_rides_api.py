"""走行の台帳・処理の記録・モデルの API（#16・#17）。S3・Lambda には繋がない。応答は contracts/api/ の定義に当てる。"""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from ct125_api.dependencies import get_current_user, get_ride_service
from ct125_api.domain.user import User
from ct125_api.main import create_app
from ct125_api.repositories.work_repository import LedgerWriteConflict
from ct125_api.services.ride_service import RideService

CONTRACTS = Path(__file__).resolve().parents[2] / "contracts"
ADMIN = User(user_id="a", username="admin", groups=("admin",))
GUEST = User(user_id="g", username="guest", groups=())
NOW = datetime(2026, 11, 9, 5, 0, 0, tzinfo=timezone.utc)
RUN_1 = "20261109T020000Z-aaaaaa"
RUN_2 = "20261109T030000Z-bbbbbb"


def validator(relative: str) -> Draft202012Validator:
    resources = []
    for path in CONTRACTS.glob("*/*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema)))
    schema = json.loads((CONTRACTS / relative).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=Registry().with_resources(resources), format_checker=FormatChecker())


def _entry(ride_id, kind, published_run=RUN_2, runs=(RUN_2, RUN_1), deleted=False):
    return {
        "ride_id": ride_id, "original_name": None, "device_id": "d01", "local_session": "ride_013", "source": "device",
        "received_at": "2026-11-09T01:00:00Z", "kind": kind, "kind_metrics": None, "deleted": deleted,
        "deleted_at": None, "deleted_by": None, "published_run": published_run, "runs": list(runs),
    }


def _run(run_id, results, action="process", where="lambda"):
    return {
        "schema": "run/2", "run_id": run_id, "action": action, "where": where, "commit": "abc1234",
        "started_at": "2026-11-09T02:00:00Z", "finished_at": "2026-11-09T02:00:20Z",
        "status": "failed" if any(r["status"] == "failed" for r in results) else "succeeded", "error": None,
        "config": {}, "model_version": "20261109-020000", "rides": results,
    }


def _result(ride_id, kind="ride", error=None):
    return {"ride_id": ride_id, "status": "failed" if error else "succeeded", "kind": None if error else kind, "kind_metrics": None,
            "n_windows": None if error else 100, "n_anomalies": None if error else 0, "error": error}


def _summary(ride_id):
    example = json.loads((CONTRACTS / "examples" / "app" / "rides.json").read_text(encoding="utf-8"))["rides"][0]
    return {**example, "id": ride_id}


class FakeWork:
    def __init__(self):
        self.ledger = {"schema": "ledger/1", "updated_at": "2026-11-09T03:00:00Z", "rides": {
            "ride_20261109_010000": _entry("ride_20261109_010000", "ride"),
            "ride_20261109_011000": _entry("ride_20261109_011000", "desk"),
            "ride_20261109_012000": _entry("ride_20261109_012000", "idle", deleted=True),
            "ride_20261109_013000": _entry("ride_20261109_013000", None, published_run=None, runs=(RUN_2,)),
        }}
        self.version = 1
        self.conflicts = 0
        self.runs = {
            RUN_1: _run(RUN_1, [_result("ride_20261109_010000", "ride"), _result("ride_20261109_011000", "desk"), _result("ride_20261109_012000", "idle")], action="retrain", where="local"),
            RUN_2: _run(RUN_2, [_result("ride_20261109_010000", "ride"), _result("ride_20261109_011000", "desk"), _result("ride_20261109_012000", "idle"), _result("ride_20261109_013000", error="gps.csv がありません")]),
        }
        self.models = {"20261109-020000": {"created_at": "2026-11-09T02:00:00Z", "where": "lambda", "commit": "abc1234", "train": {"rides": [{"ride_id": "ride_20261109_010000", "kind": "ride", "n_windows": 80}], "n_windows": 80}}, "20261106": None}
        self.current = "20261109-020000"

    def read_ledger(self):
        return copy.deepcopy(self.ledger), f'"v{self.version}"'

    def write_ledger(self, ledger, etag):
        if self.conflicts:
            self.conflicts -= 1
            self.version += 1
            raise LedgerWriteConflict("ledger")
        assert etag == f'"v{self.version}"'
        self.ledger = ledger
        self.version += 1

    def read_run(self, run_id):
        return copy.deepcopy(self.runs.get(run_id))

    def read_summary(self, run_id, ride_id):
        return _summary(ride_id) if run_id in self.runs else None

    def current_model(self):
        return self.current

    def model_versions(self):
        return sorted(self.models, reverse=True)

    def read_model(self, version):
        return self.models.get(version)

    def read_notes(self, version):
        return "# モデル\n" if self.models.get(version) else None

    def model_exists(self, version):
        return version in self.models


class FakePipeline:
    def __init__(self):
        self.calls = []

    def publish(self):
        self.calls.append(("publish",))

    def use_model(self, version):
        self.calls.append(("use_model", version))


@pytest.fixture
def world():
    return FakeWork(), FakePipeline()


def client_for(world, user):
    work, pipeline = world
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_ride_service] = lambda: RideService(work, pipeline, now=lambda: NOW)
    return TestClient(app)


# ------------------------------------------------------------------ 一覧
def test_list_shows_only_rides_on_screen(world):
    response = client_for(world, GUEST).get("/api/rides")
    assert response.status_code == 200
    validator("api/rides.schema.json").validate(response.json())
    assert [ride["id"] for ride in response.json()["rides"]] == ["ride_20261109_010000"]   # 机上・消した・未処理は出さない
    assert response.json()["rides"][0]["summary"]["id"] == "ride_20261109_010000"


def test_admin_can_include_deleted_and_hidden(world):
    response = client_for(world, ADMIN).get("/api/rides", params={"include_deleted": "true"})
    validator("api/rides.schema.json").validate(response.json())
    assert len(response.json()["rides"]) == 4
    assert client_for(world, GUEST).get("/api/rides", params={"include_deleted": "true"}).status_code == 403


# ------------------------------------------------------------------ 消す・戻す
def test_admin_deletes_and_restores(world):
    work, pipeline = world
    client = client_for(world, ADMIN)
    deleted = client.delete("/api/rides/ride_20261109_010000")
    assert deleted.status_code == 200 and deleted.json()["deleted"] is True
    entry = work.ledger["rides"]["ride_20261109_010000"]
    assert entry["deleted_by"] == "admin" and entry["deleted_at"] == "2026-11-09T05:00:00Z"
    assert pipeline.calls == [("publish",)]
    assert client.get("/api/rides").json()["rides"] == []

    restored = client.post("/api/rides/ride_20261109_010000/restore")
    assert restored.json()["deleted"] is False and work.ledger["rides"]["ride_20261109_010000"]["deleted_at"] is None
    assert pipeline.calls == [("publish",), ("publish",)]


def test_guest_cannot_change_anything(world):
    work, pipeline = world
    client = client_for(world, GUEST)
    assert client.delete("/api/rides/ride_20261109_010000").status_code == 403
    assert client.post("/api/rides/ride_20261109_010000/restore").status_code == 403
    assert client.put("/api/rides/ride_20261109_010000/published-run", json={"run_id": RUN_1}).status_code == 403
    assert client.put("/api/models/current", json={"version": "20261106"}).status_code == 403
    assert pipeline.calls == [] and work.ledger["rides"]["ride_20261109_010000"]["deleted"] is False


def test_unknown_ride_is_404_and_bad_id_is_400(world):
    client = client_for(world, ADMIN)
    assert client.delete("/api/rides/ride_20261109_235959").status_code == 404
    assert client.delete("/api/rides/..%2Fx").status_code in (400, 404)
    assert client.delete("/api/rides/x").status_code == 400


def test_ledger_conflict_is_retried_then_409(world):
    work, pipeline = world
    work.conflicts = 1
    assert client_for(world, ADMIN).delete("/api/rides/ride_20261109_010000").status_code == 200   # 1 回目の衝突は読み直してやり直す
    work.conflicts = 5
    assert client_for(world, ADMIN).post("/api/rides/ride_20261109_010000/restore").status_code == 409


# ------------------------------------------------------------------ 処理の記録と、前の結果に戻す
def test_runs_are_listed_newest_first_with_the_published_one(world):
    response = client_for(world, GUEST).get("/api/rides/ride_20261109_010000/runs")
    validator("api/runs.schema.json").validate(response.json())
    runs = response.json()["runs"]
    assert [run["run_id"] for run in runs] == [RUN_2, RUN_1]
    assert [run["published"] for run in runs] == [True, False]
    assert runs[1]["where"] == "local" and runs[1]["action"] == "retrain"


def test_hidden_ride_runs_are_only_for_admin(world):
    assert client_for(world, GUEST).get("/api/rides/ride_20261109_012000/runs").status_code == 404
    response = client_for(world, ADMIN).get("/api/rides/ride_20261109_013000/runs")
    assert response.json()["runs"][0]["status"] == "failed" and "gps.csv" in response.json()["runs"][0]["error"]


def test_admin_rolls_back_to_an_older_run(world):
    work, pipeline = world
    response = client_for(world, ADMIN).put("/api/rides/ride_20261109_010000/published-run", json={"run_id": RUN_1})
    assert response.status_code == 200 and response.json()["published_run"] == RUN_1
    assert work.ledger["rides"]["ride_20261109_010000"]["published_run"] == RUN_1
    assert pipeline.calls == [("publish",)]


def test_failed_or_unknown_run_cannot_be_published(world):
    client = client_for(world, ADMIN)
    assert client.put("/api/rides/ride_20261109_013000/published-run", json={"run_id": RUN_2}).status_code == 409
    assert client.put("/api/rides/ride_20261109_013000/published-run", json={"run_id": RUN_1}).status_code == 404
    assert client.put("/api/rides/ride_20261109_010000/published-run", json={"run_id": "bad"}).status_code == 400


# ------------------------------------------------------------------ モデル
def test_models_are_listed_with_records(world):
    response = client_for(world, GUEST).get("/api/models")
    validator("api/models.schema.json").validate(response.json())
    body = response.json()
    assert body["current"] == "20261109-020000"
    assert [(m["version"], m["has_record"], m["n_rides"]) for m in body["models"]] == [("20261109-020000", True, 1), ("20261106", False, None)]
    assert client_for(world, GUEST).get("/api/models/20261109-020000/notes").text == "# モデル\n"
    assert client_for(world, GUEST).get("/api/models/20261106").status_code == 404


def test_admin_switches_the_model(world):
    work, pipeline = world
    response = client_for(world, ADMIN).put("/api/models/current", json={"version": "20261106"})
    assert response.status_code == 202 and response.json() == {"status": "accepted", "version": "20261106"}
    assert pipeline.calls == [("use_model", "20261106")]
    assert client_for(world, ADMIN).put("/api/models/current", json={"version": "20991231-000000"}).status_code == 404
