"""機器（ESP32 のロガー）と、その認証情報。"""

import re
from dataclasses import dataclass

from .exceptions import InvalidDeviceCredentialError

# 機器 ID：英小文字・数字・- の 1〜32 文字（例：d01）
DEVICE_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
# トークン：URL に使える文字だけ（python の secrets.token_urlsafe で作る）
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}")
SCHEME = "Device"


@dataclass(frozen=True)
class Device:
    """認証が済んだ機器。"""

    device_id: str


@dataclass(frozen=True)
class DeviceCredential:
    """機器が送ってきた認証情報（まだ確かめていない）。

    ヘッダーの形：Authorization: Device <機器ID>.<トークン>
    """

    device_id: str
    token: str

    @classmethod
    def parse(cls, authorization: str | None) -> "DeviceCredential":
        scheme, _, value = (authorization or "").partition(" ")
        if scheme != SCHEME:
            raise InvalidDeviceCredentialError("機器の認証情報がありません")
        device_id, _, token = value.strip().partition(".")
        if not DEVICE_ID_PATTERN.fullmatch(device_id) or not TOKEN_PATTERN.fullmatch(token):
            raise InvalidDeviceCredentialError("機器の認証情報の形が違います")
        return cls(device_id=device_id, token=token)
