# -*- coding: utf-8 -*-
"""設定の読み込み。既定値は config/default.yaml、PC ごとの値（AWS のバケット名など）は config/local.yaml（コミットしない）。"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(root: Path | str = ROOT) -> dict:
    """default.yaml を読み、local.yaml があれば `local` キーに入れて返す。"""
    root = Path(root)
    cfg = yaml.safe_load((root / "config" / "default.yaml").read_text(encoding="utf-8")) or {}
    local_path = root / "config" / "local.yaml"
    cfg["local"] = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {} if local_path.exists() else {}
    cfg["_root"] = str(root)
    return cfg
