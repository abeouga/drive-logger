"""走行の台帳（作業用のバケットの ledger/rides.json）を書き換える決まり。ファイルは読み書きしない。

形は contracts/records/ledger.schema.json。台帳を書くのは処理（pipeline）とこのデータ API だけ。
「消す」は画面と学習から外すだけで、生データと処理の結果は残す（docs/data_flow_design.md 7.）。
"""

import copy
import re
from datetime import datetime, timezone

from .exceptions import InvalidRequestError, RideNotFoundError, RunNotFoundError, RunNotPublishableError

# contracts/common.json・contracts/records/ と同じ（tests/test_contracts.py で突き合わせる）
RIDE_ID_PATTERN = re.compile(r"ride_([0-9]{8}_[0-9]{6}(_[0-9]{1,2})?|[0-9]{3})")
RUN_ID_PATTERN = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}")
MODEL_VERSION_PATTERN = re.compile(r"[0-9]{8}(-[0-9]{6})?")
HIDDEN_KINDS = ("desk",)  # 画面に出さない分類（机上の試験）
ADMIN_GROUP = "admin"


def check_ride_id(ride_id: str) -> str:
    if not RIDE_ID_PATTERN.fullmatch(ride_id):
        raise InvalidRequestError(f"走行 ID の形が違います：{ride_id}")
    return ride_id


def check_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id or ""):
        raise InvalidRequestError(f"処理の ID の形が違います：{run_id}")
    return run_id


def check_model_version(version: str) -> str:
    if not MODEL_VERSION_PATTERN.fullmatch(version or ""):
        raise InvalidRequestError(f"モデルの版の形が違います：{version}")
    return version


def shown_on_screen(entry: dict) -> bool:
    """画面に出すか（消していない・机上でない・公開中の結果がある）。pipeline の公開の決まりと同じ。"""
    return not entry["deleted"] and entry["kind"] is not None and entry["kind"] not in HIDDEN_KINDS and entry["published_run"] is not None


def entry_of(ledger: dict, ride_id: str) -> dict:
    entry = ledger["rides"].get(ride_id)
    if entry is None:
        raise RideNotFoundError(f"{ride_id} は台帳にありません")
    return entry


def mark_deleted(ledger: dict, ride_id: str, username: str, now: datetime) -> dict:
    """消した印を付けた新しい台帳（元は変えない）。もう消してあれば、そのまま。"""
    updated = copy.deepcopy(ledger)
    entry = entry_of(updated, ride_id)
    if not entry["deleted"]:
        entry.update(deleted=True, deleted_at=_iso(now), deleted_by=username)
    updated["updated_at"] = _iso(now)
    return updated


def restore(ledger: dict, ride_id: str, now: datetime) -> dict:
    updated = copy.deepcopy(ledger)
    entry_of(updated, ride_id).update(deleted=False, deleted_at=None, deleted_by=None)
    updated["updated_at"] = _iso(now)
    return updated


def point_to_run(ledger: dict, ride_id: str, run: dict | None, now: datetime) -> dict:
    """この走行の「公開中の結果」を run にした新しい台帳。run はその処理の run.json。"""
    updated = copy.deepcopy(ledger)
    entry = entry_of(updated, ride_id)
    if run is None or run["run_id"] not in entry["runs"]:
        raise RunNotFoundError(f"{ride_id} の処理の記録に {run['run_id'] if run else '指定の処理'} はありません")
    result = next((r for r in run["rides"] if r["ride_id"] == ride_id), None)
    if result is None or result["status"] != "succeeded":
        raise RunNotPublishableError(f"処理 {run['run_id']} では {ride_id} が失敗しているので、公開できません")
    entry.update(published_run=run["run_id"], kind=result["kind"], kind_metrics=result["kind_metrics"])
    updated["updated_at"] = _iso(now)
    return updated


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
