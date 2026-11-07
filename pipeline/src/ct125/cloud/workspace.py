# -*- coding: utf-8 -*-
"""作業フォルダー。ローカルの CLI と同じ置き方（raw / interim / processed / models / app）にして、既存の関数をそのまま使う。

Lambda は /tmp を次の呼び出しでも使い回すので、毎回空にしてから使う。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    root: Path

    @classmethod
    def fresh(cls, root: str | Path) -> "Workspace":
        path = Path(root)
        if path.exists():
            shutil.rmtree(path)
        workspace = cls(path)
        for folder in (workspace.raw_dir, workspace.interim_dir, workspace.processed_dir, workspace.models_dir, workspace.app_dir):
            folder.mkdir(parents=True)
        return workspace

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def interim_dir(self) -> Path:
        return self.root / "interim"

    @property
    def processed_dir(self) -> Path:
        return self.root / "processed"

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def app_dir(self) -> Path:
        return self.root / "app"
