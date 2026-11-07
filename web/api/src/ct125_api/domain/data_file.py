"""データファイル：rides.json・ride_<id>.json・spec_<id>.png など、画面が読むファイル。

形は D:/ct125-app/docs/data_contract.md のとおり。
"""

import re
from dataclasses import dataclass

from .exceptions import InvalidFileNameError

# 使ってよい拡張子と、そのときの Content-Type
MEDIA_TYPES = {
    ".json": "application/json",
    ".png": "image/png",
}

# 英数字・_ . - だけ。先頭は英数字か _（.. や隠しファイル、フォルダーの指定を防ぐ）
SAFE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")

MAX_NAME_LENGTH = 100


@dataclass(frozen=True)
class DataFileName:
    """検査済みのファイル名。作れた時点で安全であることが保証される。"""

    value: str

    @classmethod
    def parse(cls, raw: str) -> "DataFileName":
        if not _has_allowed_length(raw):
            raise InvalidFileNameError(f"ファイル名が長すぎるか空です（{MAX_NAME_LENGTH} 文字まで）")
        if not _has_safe_characters(raw):
            raise InvalidFileNameError("ファイル名に使えない文字が含まれています")
        if _extension_of(raw) not in MEDIA_TYPES:
            raise InvalidFileNameError("使えるのは .json と .png だけです")
        return cls(raw)

    @property
    def media_type(self) -> str:
        return MEDIA_TYPES[_extension_of(self.value)]


@dataclass(frozen=True)
class DataFile:
    """読み出したファイルの中身。"""

    name: DataFileName
    content: bytes

    @property
    def media_type(self) -> str:
        return self.name.media_type


def _has_allowed_length(raw: str) -> bool:
    return 0 < len(raw) <= MAX_NAME_LENGTH


def _has_safe_characters(raw: str) -> bool:
    return SAFE_NAME_PATTERN.fullmatch(raw) is not None


def _extension_of(name: str) -> str:
    dot = name.rfind(".")
    if dot < 0:
        return ""
    return name[dot:].lower()
