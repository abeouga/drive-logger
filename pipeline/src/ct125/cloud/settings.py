# -*- coding: utf-8 -*-
"""設定。Lambda では Terraform が環境変数を入れる（docs/data_flow_design.md 3.・4.）。"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CloudSettings:
    raw_bucket: str      # 生データ：<走行>/accel.csv など。<走行>/upload_complete.json が処理の合図
    raw_prefix: str
    work_bucket: str     # 作業用：runs/・models/・ledger/
    work_prefix: str
    public_bucket: str   # 公開用：画面が読む rides.json・ride_<id>.json など
    public_prefix: str

    @classmethod
    def from_env(cls) -> "CloudSettings":
        return cls(
            raw_bucket=_required("RAW_BUCKET"),
            raw_prefix=os.environ.get("RAW_PREFIX", ""),
            work_bucket=_required("WORK_BUCKET"),
            work_prefix=os.environ.get("WORK_PREFIX", ""),
            public_bucket=_required("PUBLIC_BUCKET"),
            public_prefix=os.environ.get("PUBLIC_PREFIX", "datasets/shared/"),
        )


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません")
    return value
