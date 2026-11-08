# -*- coding: utf-8 -*-
"""設定。Lambda では Terraform が環境変数を入れる。"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..aws import UPLOAD_COMPLETE_MARKER  # 生データを上げ終わった印（ローカルの upload が最後に置く）


@dataclass(frozen=True)
class CloudSettings:
    bucket: str
    raw_prefix: str              # 生データ：raw/<走行>/accel.csv など
    processed_prefix: str        # 中間データ：processed/<走行>/windows.parquet・scored.parquet
    models_prefix: str           # モデル：models/<版>/、models/current.json
    app_prefix: str              # 画面用データ：app/v1/datasets/shared/
    work_dir: str                # 作業フォルダー（Lambda では /tmp の下）

    @classmethod
    def from_env(cls) -> "CloudSettings":
        return cls(
            bucket=_required("DATA_BUCKET"),
            raw_prefix=os.environ.get("RAW_PREFIX", "raw/"),
            processed_prefix=os.environ.get("PROCESSED_PREFIX", "processed/"),
            models_prefix=os.environ.get("MODELS_PREFIX", "models/"),
            app_prefix=os.environ.get("APP_PREFIX", "app/v1/datasets/shared/"),
            work_dir=os.environ.get("WORK_DIR", "/tmp/ct125"),
        )


__all__ = ["CloudSettings", "UPLOAD_COMPLETE_MARKER"]


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません")
    return value
