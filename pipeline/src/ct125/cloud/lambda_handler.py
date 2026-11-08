# -*- coding: utf-8 -*-
"""Lambda の入口（コンテナの CMD：ct125.cloud.lambda_handler.handler）。

イベント → 命令（commands.py）→ 処理（ride_pipeline.py）。部品の組み立てはここだけで行う。
"""
from __future__ import annotations

import json

import boto3

from ..config import load_config
from .commands import ProcessRides, RetrainAll, parse_command
from .model_registry import ModelRegistry
from .ride_pipeline import RidePipeline
from .s3_store import S3Store
from .settings import CloudSettings


def handler(event: dict, context=None) -> dict:
    settings = CloudSettings.from_env()
    command = parse_command(event, settings.raw_prefix)
    pipeline = build_pipeline(settings)
    result = run(command, pipeline)
    print(json.dumps(result, ensure_ascii=False))
    return result


def run(command, pipeline: RidePipeline) -> dict:
    if isinstance(command, RetrainAll):
        return {"action": "retrain", **pipeline.retrain_all()}
    if isinstance(command, ProcessRides):
        return {"action": "process", "rides": pipeline.process_rides(command.ride_ids)}
    raise TypeError(f"知らない命令です：{command}")


def build_pipeline(settings: CloudSettings) -> RidePipeline:
    store = S3Store(boto3.client("s3"), settings.bucket)
    cfg = load_config()
    models = ModelRegistry(store, settings.models_prefix)
    return RidePipeline(cfg, settings, store, models)
