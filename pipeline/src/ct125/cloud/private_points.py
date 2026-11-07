# -*- coding: utf-8 -*-
"""マスクする地点（自宅など）を SSM パラメーターストアから読む。

ローカルでは config/local.yaml に書いている内容と同じ形（home と places）を、
SecureString の JSON として置く（`python -m ct125 sync-private-points` で上げる）。
読めなければ処理を止める：マスクせずに書き出して公開してしまうのを防ぐため。
"""
from __future__ import annotations

import json

from botocore.exceptions import ClientError


class PrivatePointsUnavailableError(RuntimeError):
    """マスクする地点が読めない（だから書き出してはいけない）。"""


def load_private_settings(ssm_client, parameter_name: str) -> dict:
    """config/local.yaml と同じ形の dict（{"home": {...}, "places": [...]}）。"""
    try:
        response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
    except ClientError as error:
        raise PrivatePointsUnavailableError(f"SSM パラメーター {parameter_name} を読めません") from error
    settings = json.loads(response["Parameter"]["Value"])
    if not _has_any_point(settings):
        raise PrivatePointsUnavailableError(f"SSM パラメーター {parameter_name} に地点がありません")
    return settings


def to_parameter_value(local_settings: dict) -> str:
    """config/local.yaml の中身から、座標だけを取り出した JSON（地点の名前は上げない）。"""
    home = local_settings.get("home")
    places = local_settings.get("places") or []
    value = {
        "home": _coordinates(home) if home else None,
        "places": [_coordinates(place) for place in places if "lat" in place and "lon" in place],
    }
    return json.dumps(value)


def _coordinates(point: dict) -> dict:
    return {"lat": float(point["lat"]), "lon": float(point["lon"])}


def _has_any_point(settings: dict) -> bool:
    return bool(settings.get("home")) or bool(settings.get("places"))
