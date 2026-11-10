# -*- coding: utf-8 -*-
"""学習済みモデルの置き場所（作業用の場所の models/）。

models/<版>/baseline.json・isolation_forest.skops・model.json・notes.md
models/current.json   今使う版（{"version": "20261109-031500"}）

学習し直したら、新しい版を置いてから current.json を書き換えるので、途中で失敗しても前の版が使われ続ける。
Isolation Forest は skops で保存し、信頼する型を決め打ちで読む（読み込んでもコードが動かない。#23）。
pickle（isolation_forest.pkl）しかない古い版は読まずに止める。学習し直して（retrain）、新しい版に切り替える。
読むときは model.json のライブラリの版と今の版を突き合わせ、違えば止める（版がずれると読めない・スコアが変わることがある）。
model.json の無い古い版（作り直しの前に作ったもの）は、突き合わせずに読む。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sklearn.ensemble import IsolationForest

from .model import LEGACY_FOREST_INFO, dump_forest, load_forest
from .records import library_mismatches, library_versions
from .storage import Area, dump_json

PREFIX = "models/"
CURRENT = "current.json"
FOREST = "isolation_forest.skops"
LEGACY_FOREST = "isolation_forest.pkl"  # #23 より前の形式。読まない


class ModelNotFoundError(RuntimeError):
    """使うモデルの版が決まっていない、またはファイルが無い。"""


class ModelLibraryMismatchError(RuntimeError):
    """学習したときと、今のライブラリの版が違う。"""


class ModelFormatError(RuntimeError):
    """読まない形式（pickle）でしか保存されていない古い版。"""


@dataclass(frozen=True)
class TrainedModel:
    version: str
    baseline: dict
    forest: IsolationForest
    record: dict | None  # model.json（古い版では None）

    @property
    def forest_info(self) -> dict:
        """Isolation Forest の特徴量・分位点の割合・しきい値（model.json の forest）。速度を足す前の版は LEGACY_FOREST_INFO。"""
        return (self.record or {}).get("forest") or LEGACY_FOREST_INFO


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
        forest_bytes = self._work.get(f"{PREFIX}{version}/{FOREST}")
        if forest_bytes is None and self._work.exists(f"{PREFIX}{version}/{LEGACY_FOREST}"):
            raise ModelFormatError(f"モデル {version} は古い形式（pickle の {LEGACY_FOREST}）で保存されていて、読みません（#23）。学習し直して（retrain）、新しい版を使ってください")
        if baseline is None or forest_bytes is None:
            raise ModelNotFoundError(f"モデル {version} のファイルがありません")
        record = self._work.read_json(f"{PREFIX}{version}/model.json")
        if record is not None:
            mismatches = library_mismatches(record["libraries"], library_versions())
            if mismatches:
                raise ModelLibraryMismatchError(f"モデル {version} は違う版のライブラリで学習しています：{', '.join(mismatches)}。学習し直してください（retrain）")
        forest = load_forest(forest_bytes)
        trained = TrainedModel(version, baseline, forest, record)
        if forest.n_features_in_ != len(trained.forest_info["features"]):
            raise ModelFormatError(f"モデル {version} の Isolation Forest は特徴量が {forest.n_features_in_} 個で、記録（model.json の forest）の {len(trained.forest_info['features'])} 個と合いません")
        return trained

    def load_current(self) -> TrainedModel:
        return self.load(self.current_version())

    def save(self, version: str, baseline: dict, forest: IsolationForest, record: dict, notes: str) -> None:
        self._work.put(f"{PREFIX}{version}/baseline.json", json.dumps(baseline, ensure_ascii=False, indent=1).encode("utf-8"))
        self._work.put(f"{PREFIX}{version}/{FOREST}", dump_forest(forest), "application/octet-stream")
        self._work.put(f"{PREFIX}{version}/model.json", dump_json(record))
        self._work.put(f"{PREFIX}{version}/notes.md", notes.encode("utf-8"))

    def set_current(self, version: str) -> None:
        if not self._work.exists(f"{PREFIX}{version}/baseline.json"):
            raise ModelNotFoundError(f"モデル {version} がありません")
        self._work.write_json(PREFIX + CURRENT, {"version": version})

    def versions(self) -> list[str]:
        return self._work.folders(PREFIX)
