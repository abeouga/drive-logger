# -*- coding: utf-8 -*-
"""Lambda に届いたイベントを「何をするか」に読み替える。

- S3 のイベント：<走行>/upload_complete.json が置かれた → その走行を処理する
- 手動：{"action": "process", "ride_ids": ["ride_20261108_011304"]} → 指定の走行を処理する
- 手動：{"action": "retrain"} → 全走行で学習し直して、全走行を点数付けし直す
- 手動：{"action": "publish", "run_id": "..."} → その処理の結果を公開する（run_id を省くと、台帳のとおりに作り直すだけ）
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote_plus

from ..flow import UPLOAD_COMPLETE

# 走行 ID（contracts/common.json の ride_id）。サーバーが付ける ride_<日時> と、上げ直す前の ride_NNN
RIDE_ID_PATTERN = re.compile(r"ride_([0-9]{8}_[0-9]{6}(_[0-9]{1,2})?|[0-9]{3})")
# 処理の ID（contracts/records/run.schema.json）
RUN_ID_PATTERN = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}")


@dataclass(frozen=True)
class ProcessRides:
    ride_ids: tuple[str, ...]


@dataclass(frozen=True)
class RetrainAll:
    pass


@dataclass(frozen=True)
class Publish:
    run_id: str | None = None


Command = ProcessRides | RetrainAll | Publish


def parse_command(event: dict, raw_prefix: str) -> Command:
    if "Records" in event:
        return ProcessRides(_ride_ids_from_s3_event(event, raw_prefix))
    action = event.get("action")
    if action == "retrain":
        return RetrainAll()
    if action == "process":
        return ProcessRides(tuple(_checked(RIDE_ID_PATTERN, ride_id, "走行 ID") for ride_id in event.get("ride_ids", [])))
    if action == "publish":
        run_id = event.get("run_id")
        return Publish(_checked(RUN_ID_PATTERN, run_id, "処理の ID") if run_id else None)
    raise ValueError(f"知らないイベントです：{str(event)[:200]}")


def _ride_ids_from_s3_event(event: dict, raw_prefix: str) -> tuple[str, ...]:
    ride_ids = []
    for record in event["Records"]:
        key = unquote_plus(record["s3"]["object"]["key"])
        ride_id = ride_id_from_marker_key(key, raw_prefix)
        if ride_id and ride_id not in ride_ids:
            ride_ids.append(ride_id)
    return tuple(ride_ids)


def ride_id_from_marker_key(key: str, raw_prefix: str) -> str | None:
    """<接頭辞><走行>/upload_complete.json → <走行>。形が違えば None。"""
    if not key.startswith(raw_prefix) or not key.endswith("/" + UPLOAD_COMPLETE):
        return None
    middle = key[len(raw_prefix):-len("/" + UPLOAD_COMPLETE)]
    return middle if RIDE_ID_PATTERN.fullmatch(middle) else None


def _checked(pattern: re.Pattern, value: str, what: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{what}が不正です：{value}")
    return value
