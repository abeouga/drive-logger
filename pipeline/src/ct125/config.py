# -*- coding: utf-8 -*-
"""設定の読み込み。既定値は config/default.yaml、自宅座標などは config/local.yaml（コミットしない）。"""
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


def private_points(cfg: dict) -> list[tuple[float, float]]:
    """マスクする地点（自宅など）の (lat, lon) の一覧。local.yaml の `home` と `places` から集める。

    local.yaml の形：
        home: {lat: 32.xxxx, lon: 130.xxxx}
        places:
          - {name: 歯医者, lat: ..., lon: ...}
    """
    local = cfg.get("local") or {}
    pts: list[tuple[float, float]] = []
    home = local.get("home")
    if home and "lat" in home and "lon" in home:
        pts.append((float(home["lat"]), float(home["lon"])))
    for p in local.get("places") or []:
        if "lat" in p and "lon" in p:
            pts.append((float(p["lat"]), float(p["lon"])))
    return pts
