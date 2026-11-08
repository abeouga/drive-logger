# -*- coding: utf-8 -*-
"""AWS 上での処理の流れ。ローカルの CLI と同じ関数（processing・model・export）を、作業フォルダーの上で順に呼ぶ。

process_rides：新しい走行 → 前処理 → 今の版のモデルで点数付け（推論） → 書き出し → アップロード → 一覧に追加
retrain_all  ：全走行 → 前処理 → 学習 → 点数付け → 書き出し → アップロード → モデルの版を切り替え
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from .. import export as exportmod
from .. import io
from ..model import apply_models
from ..processing import process_ride, score_all
from .model_registry import ModelRegistry, TrainedModels
from .rides_index import save_summary
from .s3_store import S3Store
from .settings import CloudSettings
from .workspace import Workspace

PROCESSED_FILES = ["windows.parquet", "scored.parquet"]


class RidePipeline:
    def __init__(self, cfg: dict, settings: CloudSettings, store: S3Store, models: ModelRegistry) -> None:
        self._cfg = cfg  # config/default.yaml
        self._settings = settings
        self._store = store
        self._models = models

    # ================================================================ 新しい走行（推論だけ）
    def process_rides(self, ride_ids: tuple[str, ...]) -> list[dict]:
        return [self._process_one(ride_id) for ride_id in ride_ids]

    def _process_one(self, ride_id: str) -> dict:
        workspace = Workspace.fresh(self._settings.work_dir)
        self._download_raw(ride_id, workspace)
        windows = process_ride(ride_id, self._cfg, workspace.raw_dir, workspace.interim_dir, workspace.processed_dir)
        trained = self._models.load_current(workspace.models_dir)
        self._score_with(trained, ride_id, windows, workspace)
        summary = exportmod.export_ride(ride_id, workspace.processed_dir, workspace.interim_dir, workspace.app_dir, self._memo(ride_id, workspace))
        self._upload_ride_outputs(ride_id, workspace)
        save_summary(self._store, self._rides_key, summary)
        return {"ride_id": ride_id, "model_version": trained.version, "n_windows": summary["n_windows"], "n_highlights": summary["n_highlights"]}

    def _score_with(self, trained: TrainedModels, ride_id: str, windows: pd.DataFrame, workspace: Workspace) -> None:
        scored = apply_models(windows, trained.baseline, trained.forest, self._cfg.get("model", {}), self._cfg.get("stop_speed_kmh", 5.0))
        scored.to_parquet(workspace.processed_dir / ride_id / "scored.parquet", index=False)

    # ================================================================ 学習し直し（全走行）
    def retrain_all(self) -> dict:
        workspace = Workspace.fresh(self._settings.work_dir)
        ride_ids = self._store.list_folders(self._settings.raw_prefix)
        for ride_id in ride_ids:
            self._download_raw(ride_id, workspace)
            process_ride(ride_id, self._cfg, workspace.raw_dir, workspace.interim_dir, workspace.processed_dir)
        version_dir = score_all(self._cfg, workspace.processed_dir, workspace.models_dir, version=_new_version())
        memos = {ride_id: self._memo(ride_id, workspace) for ride_id in ride_ids}
        summaries = exportmod.export_all(workspace.processed_dir, workspace.app_dir, memos, interim_dir=workspace.interim_dir)
        for ride_id in ride_ids:
            self._upload_ride_outputs(ride_id, workspace)
        self._store.upload_file(workspace.app_dir / "rides.json", self._rides_key)
        version = self._models.publish(version_dir)  # 書き出しが全部済んでから、使う版を切り替える
        return {"model_version": version, "ride_ids": ride_ids, "n_rides": len(summaries)}

    # ================================================================ 共通
    @property
    def _rides_key(self) -> str:
        return f"{self._settings.app_prefix}rides.json"

    def _download_raw(self, ride_id: str, workspace: Workspace) -> None:
        files = self._store.download_folder(f"{self._settings.raw_prefix}{ride_id}/", workspace.raw_dir / ride_id)
        if not (workspace.raw_dir / ride_id / "accel.csv").exists():
            raise FileNotFoundError(f"{ride_id} の accel.csv が S3 にありません（{len(files)} ファイル）")

    def _memo(self, ride_id: str, workspace: Workspace) -> str:
        return io.read_memo(workspace.raw_dir / ride_id)

    def _upload_ride_outputs(self, ride_id: str, workspace: Workspace) -> None:
        processed = [workspace.processed_dir / ride_id / name for name in PROCESSED_FILES]
        self._store.upload_files(processed, f"{self._settings.processed_prefix}{ride_id}/")
        app_files = [workspace.app_dir / name for name in exportmod.ride_output_files(ride_id)]
        self._store.upload_files([path for path in app_files if path.exists()], self._settings.app_prefix)


def _new_version() -> str:
    """モデルの版の名前（UTC の日時。例：20261108-031500）。"""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
