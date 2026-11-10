# -*- coding: utf-8 -*-
"""ESP32 の機器登録（C：機器から S3 へ直接送る）。

- トークンはここで作り、**ハッシュ（SHA-256 の 16 進）だけ**を SSM に置く：<prefix><機器ID>/token-sha256
  （prefix は本番 /ct125/devices/、test /ct125-test/devices/。config の aws.device_parameter_prefix）
- トークンそのものは呼んだ人に 1 回だけ渡す（ESP32 の NVS に書き込む）。サーバー側には残らない
- 確かめる側はデータ API の ct125_api/services/device_authenticator.py（同じハッシュの作り方）
"""
from __future__ import annotations

import hashlib
import re
import secrets

PARAMETER_PREFIX = "/ct125/devices/"  # 本番の場所（既定）
DEVICE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")


class DeviceAlreadyRegisteredError(RuntimeError):
    """登録済み。作り直すなら rotate=True。"""


def register(ssm_client, device_id: str, rotate: bool = False, prefix: str = PARAMETER_PREFIX) -> str:
    """新しいトークンを作り、そのハッシュを登録して、トークンを返す。"""
    _check_device_id(device_id)
    token = secrets.token_urlsafe(32)
    try:
        ssm_client.put_parameter(
            Name=parameter_name(device_id, prefix),
            Value=hash_token(token),
            Type="SecureString",
            Overwrite=rotate,
            Description=f"CT125 ロガー {device_id} の機器トークンのハッシュ",
        )
    except ssm_client.exceptions.ParameterAlreadyExists as error:
        raise DeviceAlreadyRegisteredError(f"{device_id} は登録済みです（作り直すなら --rotate）") from error
    return token


def revoke(ssm_client, device_id: str, prefix: str = PARAMETER_PREFIX) -> None:
    _check_device_id(device_id)
    ssm_client.delete_parameter(Name=parameter_name(device_id, prefix))


def parameter_name(device_id: str, prefix: str = PARAMETER_PREFIX) -> str:
    return f"{prefix}{device_id}/token-sha256"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _check_device_id(device_id: str) -> None:
    if not DEVICE_ID_PATTERN.fullmatch(device_id):
        raise ValueError(f"機器 ID は英小文字・数字・- の 1〜32 文字です：{device_id}")
