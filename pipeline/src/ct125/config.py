# -*- coding: utf-8 -*-
"""設定の読み込み。既定値は config/default.yaml、PC ごとの値（AWS のバケット名など）は config/local.yaml（コミットしない）。

向き先の環境（本番 prod・test）は、引数の env → 環境変数 CT125_ENV → local.yaml の aws.env → default.yaml の aws.env の順に決める。
aws と upload は次の順に重ねる（後ろほど優先）：
  prod ：default.yaml → local.yaml
  test ：default.yaml → default.yaml の environments.test → local.yaml の environments.test
test のときに local.yaml の aws・upload を重ねないのは、本番用に書いたバケット名やプロファイルで test を動かさないため。
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROD = "prod"
ENV_VARIABLE = "CT125_ENV"
SECTIONS = ("aws", "upload")


def load_config(root: Path | str = ROOT, env: str | None = None) -> dict:
    """default.yaml を読み、local.yaml があれば `local` キーに入れ、向き先の環境の値を aws・upload に重ねて返す。"""
    root = Path(root)
    cfg = yaml.safe_load((root / "config" / "default.yaml").read_text(encoding="utf-8")) or {}
    local_path = root / "config" / "local.yaml"
    cfg["local"] = yaml.safe_load(local_path.read_text(encoding="utf-8")) or {} if local_path.exists() else {}
    cfg["_root"] = str(root)
    return with_environment(cfg, env)


def with_environment(cfg: dict, env: str | None = None) -> dict:
    """向き先の環境を決め、aws・upload を重ねた設定を返す（cfg["_env"] に環境の名前）。"""
    local = cfg.get("local") or {}
    name = env or os.environ.get(ENV_VARIABLE) or (local.get("aws") or {}).get("env") or (cfg.get("aws") or {}).get("env") or PROD
    environments = cfg.get("environments") or {}
    if name != PROD and name not in environments:
        known = ", ".join([PROD, *environments])
        raise ValueError(f"環境 {name} は config/default.yaml の environments にありません（使えるのは {known}）")

    layers = [cfg] if name == PROD else [cfg, environments[name], (local.get("environments") or {}).get(name) or {}]
    if name == PROD:
        layers.append(local)
    merged = dict(cfg)
    for section in SECTIONS:
        merged[section] = {}
        for layer in layers:
            merged[section].update(layer.get(section) or {})
    merged["aws"]["env"] = name
    merged["_env"] = name
    return merged
