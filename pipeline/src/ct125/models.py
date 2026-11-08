# -*- coding: utf-8 -*-
"""学習済みモデルの置き場所（作業用の場所の models/）。

models/<版>/baseline.json・isolation_forest.pkl・model.json・notes.md
models/current.json   今使う版（{"version": "20261109-031500"}）

学習し直したら、新しい版を置いてから current.json を書き換えるので、途中で失敗しても前の版が使われ続ける。
読むときは model.json のライブラリの版と今の版を突き合わせ、違えば止める（pickle は版がずれると壊れることがある）。
model.json の無い古い版（作り直しの前に作ったもの）は、突き合わせずに読む。
"""
from __future__ import annotations

import io as stdio
import json
import pickle
from dataclasses import dataclass

from sklearn.ensemble import IsolationForest

from .records import library_mismatches, library_versions
from .storage import Area, dump_json

PREFIX = "models/"
CURRENT = "current.json"


class ModelNotFoundError(RuntimeError):
    """使うモデルの版が決まっていない、またはファイルが無い。"""


class ModelLibraryMismatchError(RuntimeError):
    """学習したときと、今のライブラリの版が違う。"""


@dataclass(frozen=True)
class TrainedModel:
    version: str
    baseline: dict
    forest: IsolationForest
    record: dict | None  # model.json（古い版では None）


class ModelStore:
    def __init__(self, work: Area) -> None:
        self._work = work

    def current_version(self) -> str:
        pointer = self._work.read_json(PREFIX + CURRENT)
        if not pointer or not pointer.get("version"):
            raise ModelNotFoundError(f"{self._work.key(PREFIX + CURRENT)} がありません（使うモデルの版が決まっていない）")
        return str(pointer["version"])

    def load(self, version: str) -> TrainedModel:
        baseline = self._work.read_json(f"{PREFIX}{version}/baseline.json")
        forest_bytes = self._work.get(f"{PREFIX}{version}/isolation_forest.pkl")
        if baseline is None or forest_bytes is None:
            raise ModelNotFoundError(f"モデル {version} のファイルがありません")
        record = self._work.read_json(f"{PREFIX}{version}/model.json")
        if record is not None:
            mismatches = library_mismatches(record["libraries"], library_versions())
            if mismatches:
                raise ModelLibraryMismatchError(f"モデル {version} は違う版のライブラリで学習しています：{', '.join(mismatches)}。学習し直してください（retrain）")
        forest = pickle.load(stdio.BytesIO(forest_bytes))  # noqa: S301  自分の作業用の場所に置いたモデルだけを読む（#23）
        return TrainedModel(version, baseline, forest, record)

    def load_current(self) -> TrainedModel:
        return self.load(self.current_version())

    def save(self, version: str, baseline: dict, forest: IsolationForest, record: dict, notes: str) -> None:
        self._work.put(f"{PREFIX}{version}/baseline.json", json.dumps(baseline, ensure_ascii=False, indent=1).encode("utf-8"))
        self._work.put(f"{PREFIX}{version}/isolation_forest.pkl", pickle.dumps(forest), "application/octet-stream")
        self._work.put(f"{PREFIX}{version}/model.json", dump_json(record))
        self._work.put(f"{PREFIX}{version}/notes.md", notes.encode("utf-8"))

    def set_current(self, version: str) -> None:
        if not self._work.exists(f"{PREFIX}{version}/baseline.json"):
            raise ModelNotFoundError(f"モデル {version} がありません")
        self._work.write_json(PREFIX + CURRENT, {"version": version})

    def versions(self) -> list[str]:
        return self._work.folders(PREFIX)
