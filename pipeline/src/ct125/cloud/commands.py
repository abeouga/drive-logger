# -*- coding: utf-8 -*-
"""Lambda に届いたイベントを「何をするか」に読み替える。

- S3 のイベント：raw/<走行>/upload_complete.json が置かれた → その走行を処理する
- 手動：{"action": "process", "ride_ids": ["ride_010"]} → 指定の走行を処理する
- 手動：{"action": "retrain"} → 全走行で学習し直して、全走行を書き出し直す
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote_plus

from .settings import UPLOAD_COMPLETE_MARKER

# 走行 ID（contracts/common.json の ride_id）。サーバーが付ける ride_<日時> と、上げ直す前の ride_NNN
RIDE_ID_PATTERN = re.compile(r"ride_([0-9]{8}_[0-9]{6}(_[0-9]{1,2})?|[0-9]{3})")


@dataclass(frozen=True)
class ProcessRides:
    ride_ids: tuple[str, ...]


@dataclass(frozen=True)
class RetrainAll:
    pass


Command = ProcessRides | RetrainAll


def parse_command(event: dict, raw_prefix: str) -> Command:
    if "Records" in event:
        return ProcessRides(_ride_ids_from_s3_event(event, raw_prefix))
    action = event.get("action")
    if action == "retrain":
        return RetrainAll()
    if action == "process":
        return ProcessRides(tuple(_checked_ride_id(ride_id) for ride_id in event.get("ride_ids", [])))
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
    """raw/<走行>/upload_complete.json → <走行>。形が違えば None。"""
    if not key.startswith(raw_prefix) or not key.endswith("/" + UPLOAD_COMPLETE_MARKER):
        return None
    middle = key[len(raw_prefix):-len("/" + UPLOAD_COMPLETE_MARKER)]
    return middle if RIDE_ID_PATTERN.fullmatch(middle) else None


def _checked_ride_id(ride_id: str) -> str:
    if not RIDE_ID_PATTERN.fullmatch(ride_id):
        raise ValueError(f"走行 ID が不正です：{ride_id}")
    return ride_id
