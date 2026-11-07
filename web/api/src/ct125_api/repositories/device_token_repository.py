"""機器のトークンの置き場所の約束。トークンそのものは置かず、SHA-256 のハッシュ（16 進）だけを持つ。"""

from typing import Protocol


class DeviceTokenRepository(Protocol):
    def token_hash(self, device_id: str) -> str | None:
        """登録されているトークンのハッシュ。登録されていなければ None。"""
        ...
