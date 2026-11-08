# -*- coding: utf-8 -*-
"""Lambda の入口（コンテナの CMD：ct125.cloud.lambda_handler.handler）。

イベント → 命令（commands.py）→ 処理の流れ（ct125/flow.py）。部品の組み立てはここだけで行う。
処理に失敗した走行があれば、記録（run.json）を残したうえで例外にする（Lambda が 1 回だけやり直す）。
"""
from __future__ import annotations

import json

import boto3

from ..config import load_config
from ..flow import Pipeline, Places
from ..records import code_commit
from ..storage import Area, S3Store
from .commands import ProcessRides, Publish, RetrainAll, parse_command
from .settings import CloudSettings


class RunFailedError(RuntimeError):
    """処理に失敗した走行があった（記録は残してある）。"""


def handler(event: dict, context=None) -> dict:
    settings = CloudSettings.from_env()
    command = parse_command(event, settings.raw_prefix)
    pipeline = build_pipeline(settings)
    result = run(command, pipeline)
    print(json.dumps(result, ensure_ascii=False, default=str))
    if result.get("status") == "failed":
        raise RunFailedError(result.get("error") or "処理に失敗しました")
    return result


def run(command, pipeline: Pipeline) -> dict:
    if isinstance(command, RetrainAll):
        return pipeline.retrain(publish=True)
    if isinstance(command, ProcessRides):
        return pipeline.process(list(command.ride_ids), publish=True)
    if isinstance(command, Publish):
        return {"action": "publish", **pipeline.publish(command.run_id)}
    raise TypeError(f"知らない命令です：{command}")


def build_pipeline(settings: CloudSettings) -> Pipeline:
    s3 = boto3.client("s3")
    places = Places(
        raw=Area(S3Store(s3, settings.raw_bucket), settings.raw_prefix, "raw"),
        work=Area(S3Store(s3, settings.work_bucket), settings.work_prefix, "work"),
        public=Area(S3Store(s3, settings.public_bucket), settings.public_prefix, "public"),
    )
    return Pipeline(load_config(), places, where="lambda", commit=code_commit())
