# -*- coding: utf-8 -*-
"""保存の口。処理の流れ（flow.py）は、S3 の細かい API をここ越しにだけ使う。

- Store：1 つのバケット（S3Store）か、テスト用の記憶の上の置き場所（MemoryStore）
- Area ：Store の中の 1 つの場所（バケット＋接頭辞）。生データ（raw）・作業用（work）・公開用（public）の 3 つを使う
  どのバケット・接頭辞を使うかは設定で決まる（docs/data_flow_design.md 3.・4.）

JSON は条件付きで書ける（読んだときの印 = ETag が変わっていなければ書く）。台帳のように、
ほかの処理が同時に書くかもしれないファイルに使う。
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from botocore.exceptions import ClientError

NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}
CONFLICT_CODES = {"PreconditionFailed", "ConditionalRequestConflict"}
CONTENT_TYPES = {
    ".parquet": "application/vnd.apache.parquet",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
}


class WriteConflictError(Exception):
    """書こうとした間に、ほかの処理が同じファイルを書き換えた（または、あるはずのないファイルがあった）。"""


def content_type_of(key: str) -> str:
    suffix = PurePosixPath(key).suffix.lower()
    return CONTENT_TYPES.get(suffix) or mimetypes.guess_type(key)[0] or "application/octet-stream"


class Store(Protocol):
    def get(self, key: str) -> tuple[bytes, str] | None: ...  # (中身, ETag)。無ければ None
    def put(self, key: str, data: bytes, content_type: str, if_match: str | None = None, if_none_match: bool = False) -> None: ...
    def delete(self, key: str) -> None: ...
    def keys(self, prefix: str) -> list[str]: ...
    def folders(self, prefix: str) -> list[str]: ...


# ------------------------------------------------------------------ S3
class S3Store:
    def __init__(self, s3_client, bucket: str) -> None:
        self._s3 = s3_client
        self.bucket = bucket

    def get(self, key: str) -> tuple[bytes, str] | None:
        try:
            response = self._s3.get_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if _code(error) in NOT_FOUND_CODES:
                return None
            raise
        return response["Body"].read(), response["ETag"]

    def put(self, key: str, data: bytes, content_type: str, if_match: str | None = None, if_none_match: bool = False) -> None:
        kwargs = {"Bucket": self.bucket, "Key": key, "Body": data, "ContentType": content_type}
        if if_match:
            kwargs["IfMatch"] = if_match
        if if_none_match:
            kwargs["IfNoneMatch"] = "*"
        try:
            self._s3.put_object(**kwargs)
        except ClientError as error:
            if _code(error) in CONFLICT_CODES:
                raise WriteConflictError(key) from error
            raise

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self.bucket, Key=key)

    def keys(self, prefix: str) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        found = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            found.extend(item["Key"] for item in page.get("Contents", []))
        return sorted(found)

    def folders(self, prefix: str) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        names = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix, Delimiter="/"):
            names.extend(entry["Prefix"][len(prefix):].rstrip("/") for entry in page.get("CommonPrefixes", []))
        return sorted(names)


# ------------------------------------------------------------------ 記憶の上（テスト用）
class MemoryStore:
    """S3 と同じふるまい（ETag・条件付きの書き込み・フォルダーの一覧）をする、記憶の上の置き場所。"""

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects: dict[str, bytes] = dict(objects or {})
        self.content_types: dict[str, str] = {}

    def get(self, key: str) -> tuple[bytes, str] | None:
        if key not in self.objects:
            return None
        data = self.objects[key]
        return data, _etag(data)

    def put(self, key: str, data: bytes, content_type: str, if_match: str | None = None, if_none_match: bool = False) -> None:
        current = self.objects.get(key)
        if if_none_match and current is not None:
            raise WriteConflictError(key)
        if if_match and (current is None or _etag(current) != if_match):
            raise WriteConflictError(key)
        self.objects[key] = bytes(data)
        self.content_types[key] = content_type

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)
        self.content_types.pop(key, None)

    def keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self.objects if key.startswith(prefix))

    def folders(self, prefix: str) -> list[str]:
        names = {key[len(prefix):].split("/", 1)[0] for key in self.keys(prefix) if "/" in key[len(prefix):]}
        return sorted(names)


# ------------------------------------------------------------------ 場所（バケット＋接頭辞）
@dataclass(frozen=True)
class Area:
    """Store の中の 1 つの場所。キーは接頭辞からの相対で渡す。"""

    store: Store
    prefix: str = ""
    name: str = ""

    def key(self, relative: str) -> str:
        return f"{self.prefix}{relative}"

    def get(self, relative: str) -> bytes | None:
        found = self.store.get(self.key(relative))
        return found[0] if found else None

    def put(self, relative: str, data: bytes, content_type: str | None = None) -> None:
        self.store.put(self.key(relative), data, content_type or content_type_of(relative))

    def delete(self, relative: str) -> None:
        self.store.delete(self.key(relative))

    def exists(self, relative: str) -> bool:
        return self.store.get(self.key(relative)) is not None

    def keys(self, relative_prefix: str = "") -> list[str]:
        """relative_prefix の下のファイル（接頭辞からの相対のキー）。"""
        return [key[len(self.prefix):] for key in self.store.keys(self.key(relative_prefix))]

    def folders(self, relative_prefix: str = "") -> list[str]:
        return self.store.folders(self.key(relative_prefix))

    # ---------------------------------------------------------------- JSON
    def read_json(self, relative: str) -> dict | None:
        data = self.get(relative)
        return json.loads(data.decode("utf-8")) if data is not None else None

    def write_json(self, relative: str, document: dict) -> None:
        self.put(relative, dump_json(document), "application/json; charset=utf-8")

    def read_json_tagged(self, relative: str) -> tuple[dict | None, str | None]:
        found = self.store.get(self.key(relative))
        if not found:
            return None, None
        return json.loads(found[0].decode("utf-8")), found[1]

    def write_json_if(self, relative: str, document: dict, etag: str | None) -> None:
        """読んだときの ETag のままなら書く（etag=None なら、まだ無いときだけ書く）。変わっていたら WriteConflictError。"""
        self.store.put(self.key(relative), dump_json(document), "application/json; charset=utf-8", if_match=etag, if_none_match=etag is None)


def dump_json(document) -> bytes:
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _etag(data: bytes) -> str:
    return '"' + hashlib.md5(data, usedforsecurity=False).hexdigest() + '"'


def _code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))
