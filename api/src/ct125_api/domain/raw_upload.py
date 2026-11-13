"""機器からの生データのアップロード：送るファイルの決まりと、受け付けの記録。

1 回の受け付け（UploadSession）は S3 の raw/<走行>/upload_session.json に置く。
完了したら raw/<走行>/upload_complete.json を置き、それを合図に AWS 側の自動処理が動く。
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from .exceptions import InvalidUploadRequestError

# 送信の約束（contracts/upload/upload.json・contracts/common.json）。合っているかは tests/test_contracts.py で確かめる
# 受け付けるファイル（ESP32 が SD の /sessions/ride_NNN/ に書くものと、走行メモ。memo.txt・readme.txt は走行メモの古い名前）
ALLOWED_FILES = ("accel.csv", "gps.csv", "events.csv", "status.csv", "meta.json", "notes.md", "memo.txt", "readme.txt")
# 走行メモ（PC で後から書く）。送り終えた走行にも、これだけは後から足せる（#100）
MEMO_FILES = ("notes.md", "memo.txt", "readme.txt")
# これが無いと処理できない
REQUIRED_FILES = ("accel.csv", "gps.csv", "meta.json")
# 1 ファイルの上限（1 時間で約 55MB。余裕を見て）
MAX_FILE_BYTES = 200 * 1024 * 1024

# サーバーが付ける走行名：ride_<年月日>_<時分秒>（重なったら _2, _3 …）
RIDE_ID_PATTERN = re.compile(r"ride_[0-9]{8}_[0-9]{6}(_[0-9]{1,2})?")
LOCAL_SESSION_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,32}")


@dataclass(frozen=True)
class RawFile:
    name: str
    size: int

    @classmethod
    def parse(cls, name: str, size: int) -> "RawFile":
        if name not in ALLOWED_FILES:
            raise InvalidUploadRequestError(f"送れないファイルです：{name}")
        if not 0 <= size <= MAX_FILE_BYTES:
            raise InvalidUploadRequestError(f"{name} の大きさが範囲外です（0〜{MAX_FILE_BYTES} バイト）")
        return cls(name=name, size=size)


def parse_file_list(files: list[tuple[str, int]]) -> tuple[RawFile, ...]:
    """送るファイルの一覧を確かめる：決まったファイルだけ・重複なし・必須のファイルがそろっている。"""
    parsed = tuple(RawFile.parse(name, size) for name, size in files)
    names = [file.name for file in parsed]
    if len(set(names)) != len(names):
        raise InvalidUploadRequestError("同じファイルが 2 回あります")
    missing = [name for name in REQUIRED_FILES if name not in names]
    if missing:
        raise InvalidUploadRequestError(f"必要なファイルがありません：{', '.join(missing)}")
    return parsed


def fingerprint(local_session: str, files: tuple["RawFile", ...]) -> str:
    """同じ SD の走行かどうかを見分ける印（#14）。SD のセッション名と、必須のファイルの大きさ（バイト）から作る。

    ESP32 から送っても PC から送っても、同じ SD の走行なら同じになる（送った機器は問わない）。
    記録の開始時刻は meta.json に無い（ESP32 は時計を持たない）ので、大きさで見分ける。違う記録で 3 つのファイルの
    大きさがすべて同じになることは、まず無い。走行メモ（notes.md など）は後から足すことがあるので入れない。
    """
    sizes = {file.name: file.size for file in files}
    text = "|".join([local_session] + [f"{name}:{sizes.get(name)}" for name in REQUIRED_FILES])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_ride_id(ride_id: str) -> str:
    if not RIDE_ID_PATTERN.fullmatch(ride_id):
        raise InvalidUploadRequestError(f"走行名の形が違います：{ride_id}")
    return ride_id


def check_local_session(local_session: str) -> str:
    if not LOCAL_SESSION_PATTERN.fullmatch(local_session):
        raise InvalidUploadRequestError(f"SD の走行名の形が違います：{local_session}")
    return local_session


def ride_id_candidates(now: datetime, attempts: int = 5) -> list[str]:
    """走行名の候補。1 つ目が使われていたら次を使う。"""
    base = f"ride_{now:%Y%m%d_%H%M%S}"
    return [base] + [f"{base}_{n}" for n in range(2, attempts + 1)]


def memo_changes(files: tuple[RawFile, ...], stored_size) -> tuple[RawFile, ...]:
    """送られてきた走行メモのうち、置き場所に無いもの・大きさが違うもの（stored_size(名前) → 大きさか None）。"""
    return tuple(file for file in files if file.name in MEMO_FILES and stored_size(file.name) != file.size)


@dataclass(frozen=True)
class UploadSession:
    """1 回の受け付け：どの機器の、SD のどの走行を、どのファイルで送るか。"""

    ride_id: str
    device_id: str
    local_session: str
    files: tuple[RawFile, ...]
    created_at: str

    def belongs_to(self, device_id: str) -> bool:
        return self.device_id == device_id

    def to_dict(self) -> dict:
        return {
            "ride_id": self.ride_id,
            "device_id": self.device_id,
            "local_session": self.local_session,
            "files": [{"name": f.name, "size": f.size} for f in self.files],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UploadSession":
        files = tuple(RawFile(name=f["name"], size=int(f["size"])) for f in data["files"])
        return cls(data["ride_id"], data["device_id"], data["local_session"], files, data["created_at"])


@dataclass(frozen=True)
class MemoAddition:
    """送り終えた走行に、後から走行メモを足す受け付け（#100）。applied_at が None ならまだ足し終えていない。"""

    ride_id: str
    device_id: str
    local_session: str
    files: tuple[RawFile, ...]
    created_at: str
    applied_at: str | None = None

    def belongs_to(self, device_id: str) -> bool:
        return self.device_id == device_id

    def is_pending(self) -> bool:
        return self.applied_at is None

    def applied(self, when: str) -> "MemoAddition":
        return MemoAddition(self.ride_id, self.device_id, self.local_session, self.files, self.created_at, when)

    def to_dict(self) -> dict:
        return {
            "ride_id": self.ride_id,
            "device_id": self.device_id,
            "local_session": self.local_session,
            "files": [{"name": f.name, "size": f.size} for f in self.files],
            "created_at": self.created_at,
            "applied_at": self.applied_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoAddition":
        files = tuple(RawFile(name=f["name"], size=int(f["size"])) for f in data["files"])
        return cls(data["ride_id"], data["device_id"], data["local_session"], files, data["created_at"], data.get("applied_at"))
