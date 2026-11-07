# -*- coding: utf-8 -*-
"""学習済みモデルの置き場所。

S3 の models/<版>/baseline.json・isolation_forest.pkl に置き、
「今使う版」は models/current.json（{"version": "20261106"}）が指す。
学習し直したら新しい版を上げてから current.json を書き換えるので、途中で失敗しても前の版が使われ続ける。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sklearn.ensemble import IsolationForest

from .. import model as modelmod
from .s3_store import S3Store

CURRENT_POINTER = "current.json"
BASELINE_FILE = "baseline.json"
FOREST_FILE = "isolation_forest.pkl"


@dataclass(frozen=True)
class TrainedModels:
    version: str
    baseline: dict
    forest: IsolationForest


class ModelRegistry:
    def __init__(self, store: S3Store, prefix: str) -> None:
        self._store = store
        self._prefix = prefix

    def load_current(self, work_dir: Path) -> TrainedModels:
        version = self.current_version()
        folder = work_dir / version
        baseline_path = self._store.download_file(self._key(version, BASELINE_FILE), folder / BASELINE_FILE)
        forest_path = self._store.download_file(self._key(version, FOREST_FILE), folder / FOREST_FILE)
        return TrainedModels(version, modelmod.load_baseline(baseline_path), modelmod.load_model(forest_path))

    def current_version(self) -> str:
        pointer, _ = self._store.read_json(f"{self._prefix}{CURRENT_POINTER}")
        if not pointer or not pointer.get("version"):
            raise RuntimeError(f"s3://…/{self._prefix}{CURRENT_POINTER} がありません（使うモデルの版が決まっていない）")
        return str(pointer["version"])

    def publish(self, version_dir: Path) -> str:
        """version_dir（models/<版>/）を上げてから、current.json をその版に向ける。"""
        version = version_dir.name
        for name in (BASELINE_FILE, FOREST_FILE):
            self._store.upload_file(version_dir / name, self._key(version, name))
        self._store.write_json(f"{self._prefix}{CURRENT_POINTER}", {"version": version})
        return version

    def _key(self, version: str, name: str) -> str:
        return f"{self._prefix}{version}/{name}"
