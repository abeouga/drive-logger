"""機器の認証：送られてきたトークンのハッシュが、登録されたハッシュと一致するかを確かめる。"""

import hashlib
import hmac

from ..domain.device import Device, DeviceCredential
from ..domain.exceptions import InvalidDeviceCredentialError
from ..repositories.device_token_repository import DeviceTokenRepository


class DeviceAuthenticator:
    def __init__(self, tokens: DeviceTokenRepository) -> None:
        self._tokens = tokens

    def authenticate(self, credential: DeviceCredential) -> Device:
        registered = self._tokens.token_hash(credential.device_id)
        if registered is None or not _same_hash(hash_token(credential.token), registered):
            # 「登録が無い」と「トークンが違う」を区別して返さない（機器 ID の当てずっぽうを防ぐ）
            raise InvalidDeviceCredentialError("機器の認証に失敗しました")
        return Device(device_id=credential.device_id)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _same_hash(a: str, b: str) -> bool:
    # 比べる時間が中身で変わらないようにする（推測を防ぐ）
    return hmac.compare_digest(a.encode("ascii"), b.strip().encode("ascii"))
