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


def _entry(ride_id, kind, published_run=RUN_2, runs=(RUN_2, RUN_1), deleted=False, name="2026/11/09の走行"):
    return {
        "ride_id": ride_id, "name": name, "original_name": None, "device_id": "d01", "local_session": "ride_013", "source": "device",
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
            "ride_20261109_011000": _entry("ride_20261109_011000", "desk", name="2026/11/09の走行(1)"),
            "ride_20261109_012000": _entry("ride_20261109_012000", "idle", deleted=True, name=None),  # 名前を付ける前の台帳（処理の Lambda が次に書くときに付く）
            "ride_20261109_013000": _entry("ride_20261109_013000", None, published_run=None, runs=(RUN_2,), name="2026/11/09の走行(2)"),
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


class FakeFiles:
    """生データ（raw）と処理の結果（work の runs/<run>/rides/<ride>/）の置き場所。消した順を calls に残す。"""

    def __init__(self, calls, work):
        self.calls = calls
        self.work = work
        self.fail_on = None
        self.raw = {f"{ride_id}/{name}" for ride_id in work.ledger["rides"] for name in ("accel.csv", "gps.csv", "meta.json", "upload_complete.json")}
        self.results = {
            f"runs/{run_id}/rides/{ride_id}/{name}"
            for ride_id, entry in work.ledger["rides"].items()
            for run_id in entry["runs"]
            for name in ("windows.parquet", "summary.json", "app/ride_x.json")
        }

    def delete_results(self, run_id, ride_id):
        assert ride_id not in self.work.ledger["rides"]   # 台帳から除いた後に消す
        if self.fail_on == "results":
            raise RuntimeError("AccessDenied")
        return self._delete(self.results, f"runs/{run_id}/rides/{ride_id}/", ("delete_results", run_id))

    def delete_raw(self, ride_id):
        if self.fail_on == "raw":
            raise RuntimeError("AccessDenied")
        return self._delete(self.raw, f"{ride_id}/", ("delete_raw", ride_id))

    def _delete(self, keys, prefix, call):
        self.calls.append(call)
        doomed = {key for key in keys if key.startswith(prefix)}
        keys -= doomed
        return len(doomed)


def client_for(world, user, files=None):
    work, pipeline = world
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_ride_service] = lambda: RideService(work, pipeline, files, now=lambda: NOW)
    return TestClient(app)


# ------------------------------------------------------------------ 一覧
def test_list_shows_only_rides_on_screen(world):
    response = client_for(world, GUEST).get("/api/rides")
    assert response.status_code == 200
    validator("api/rides.schema.json").validate(response.json())
    assert [ride["id"] for ride in response.json()["rides"]] == ["ride_20261109_010000"]   # 机上・消した・未処理は出さない
    assert response.json()["rides"][0]["summary"]["id"] == "ride_20261109_010000"
    assert response.json()["rides"][0]["name"] == response.json()["rides"][0]["summary"]["name"] == "2026/11/09の走行"   # 名前は台帳から


def test_admin_can_include_deleted_and_hidden(world):
    response = client_for(world, ADMIN).get("/api/rides", params={"include_deleted": "true"})
    validator("api/rides.schema.json").validate(response.json())
    assert len(response.json()["rides"]) == 4
    unnamed = next(ride for ride in response.json()["rides"] if ride["id"] == "ride_20261109_012000")
    assert unnamed["name"] is None and unnamed["summary"]["name"] == "ride_20261109_012000"   # 名前が付く前は、要約の名前を走行 ID にする
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
    assert work.ledger["rides"]["ride_20261109_010000"]["name"] == "2026/11/09の走行"   # 消す・戻すで名前は変えない
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


# ------------------------------------------------------------------ 完全に削除（#82）
TRASHED = "ride_20261109_012000"   # ゴミ箱に入っている走行


@pytest.fixture
def files(world):
    work, pipeline = world
    return FakeFiles(pipeline.calls, work)


def purge(client, ride_id, confirm=None):
    return client.post(f"/api/rides/{ride_id}/purge", json={"confirm_ride_id": ride_id if confirm is None else confirm})


def test_admin_purges_a_ride_in_the_trash(world, files, caplog):
    work, pipeline = world
    runs_before = copy.deepcopy(work.runs)
    with caplog.at_level("INFO", logger="ct125_api.purge"):
        response = purge(client_for(world, ADMIN, files), TRASHED)
    assert response.status_code == 200
    validator("api/purge.schema.json").validate(response.json())
    assert response.json() == {"ride_id": TRASHED, "purged": True, "removed": {"raw_files": 4, "result_files": 6, "runs": [RUN_2, RUN_1]}}
    # 台帳から 1 件だけ除き、公開し直しを頼んでから、処理の結果 → 生データの順に消す
    assert TRASHED not in work.ledger["rides"] and len(work.ledger["rides"]) == 3
    assert work.ledger["updated_at"] == "2026-11-09T05:00:00Z"
    assert pipeline.calls == [("publish",), ("delete_results", RUN_2), ("delete_results", RUN_1), ("delete_raw", TRASHED)]
    assert not any(key.startswith(f"{TRASHED}/") for key in files.raw)
    assert not any(f"/rides/{TRASHED}/" in key for key in files.results)
    # ほかの走行のファイルは残る。処理の記録（run.json）は書き換えない（消した走行の ID が残る）
    assert len(files.raw) == 12 and len(files.results) == 15
    assert work.runs == runs_before
    # 誰がいつ消したかをログに残す
    assert any(TRASHED in r.getMessage() and "admin" in r.getMessage() and "2026-11-09T05:00:00Z" in r.getMessage() for r in caplog.records)


def test_guest_cannot_purge(world, files):
    work, pipeline = world
    assert purge(client_for(world, GUEST, files), TRASHED).status_code == 403
    assert TRASHED in work.ledger["rides"] and pipeline.calls == []


def test_ride_not_in_the_trash_cannot_be_purged(world, files):
    work, pipeline = world
    response = purge(client_for(world, ADMIN, files), "ride_20261109_010000")
    assert response.status_code == 409 and "ゴミ箱" in response.json()["detail"]
    assert "ride_20261109_010000" in work.ledger["rides"] and pipeline.calls == []


def test_purge_needs_the_ride_name_typed(world, files):
    work, pipeline = world
    client = client_for(world, ADMIN, files)
    assert purge(client, TRASHED, confirm="ride_20261109_010000").status_code == 400
    assert purge(client, TRASHED, confirm="").status_code == 400
    assert client.post(f"/api/rides/{TRASHED}/purge", json={}).status_code == 422
    assert TRASHED in work.ledger["rides"] and pipeline.calls == []
    assert purge(client, "ride_20261109_235959").status_code == 404
    assert purge(client, "x").status_code == 400


def test_purge_stopped_midway_is_reported(world, files):
    work, pipeline = world
    files.fail_on = "raw"
    response = purge(client_for(world, ADMIN, files), TRASHED)
    assert response.status_code == 500 and "生データ" in response.json()["detail"]
    # 台帳と画面からは除いてある（消えかけの走行は画面に出ない）
    assert TRASHED not in work.ledger["rides"] and pipeline.calls[0] == ("publish",)


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
