# -*- coding: utf-8 -*-
"""S3 とのやりとり。処理の流れ（ride_pipeline.py）は、S3 の細かい API をここ越しにだけ使う。"""
from __future__ import annotations

import json
from pathlib import Path

from botocore.exceptions import ClientError

from ..aws import content_type_of

PRECONDITION_FAILED = "PreconditionFailed"
NOT_FOUND_CODES = {"NoSuchKey", "404"}


class WriteConflictError(Exception):
    """書こうとした間に、ほかの処理が同じファイルを書き換えた。"""


class S3Store:
    def __init__(self, s3_client, bucket: str) -> None:
        self._s3 = s3_client
        self._bucket = bucket

    # ---------------------------------------------------------------- 一覧・ダウンロード
    def list_folders(self, prefix: str) -> list[str]:
        """prefix の直下のフォルダー名（例：raw/ → ["ride_001", ...]）。"""
        paginator = self._s3.get_paginator("list_objects_v2")
        names = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix, Delimiter="/"):
            for entry in page.get("CommonPrefixes", []):
                names.append(entry["Prefix"][len(prefix):].rstrip("/"))
        return sorted(names)

    def download_folder(self, prefix: str, dest: Path) -> list[Path]:
        """prefix の下のファイルをすべて dest に落とす（サブフォルダーは作らない）。"""
        dest.mkdir(parents=True, exist_ok=True)
        files = []
        for key in self._keys_under(prefix):
            name = key[len(prefix):]
            if not name or "/" in name:
                continue
            path = dest / name
            self._s3.download_file(self._bucket, key, str(path))
            files.append(path)
        return files

    def download_file(self, key: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._s3.download_file(self._bucket, key, str(dest))
        return dest

    # ---------------------------------------------------------------- アップロード
    def upload_file(self, path: Path, key: str) -> None:
        self._s3.upload_file(str(path), self._bucket, key, ExtraArgs={"ContentType": content_type_of(path)})

    def upload_files(self, paths: list[Path], prefix: str) -> list[str]:
        keys = []
        for path in paths:
            key = f"{prefix}{path.name}"
            self.upload_file(path, key)
            keys.append(key)
        return keys

    # ---------------------------------------------------------------- JSON（条件付きの書き込み）
    def read_json(self, key: str) -> tuple[dict | None, str | None]:
        """(中身, ETag)。無ければ (None, None)。"""
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if _error_code(error) in NOT_FOUND_CODES:
                return None, None
            raise
        document = json.loads(response["Body"].read().decode("utf-8"))
        return document, response["ETag"]

    def write_json(self, key: str, document: dict, expected_etag: str | None = None, must_not_exist: bool = False) -> None:
        """JSON を書く。expected_etag を渡すと「読んだときから変わっていなければ」だけ書く（変わっていたら WriteConflictError）。"""
        body = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        kwargs = {"Bucket": self._bucket, "Key": key, "Body": body, "ContentType": "application/json; charset=utf-8"}
        if expected_etag:
            kwargs["IfMatch"] = expected_etag
        if must_not_exist:
            kwargs["IfNoneMatch"] = "*"
        try:
            self._s3.put_object(**kwargs)
        except ClientError as error:
            if _error_code(error) in {PRECONDITION_FAILED, "ConditionalRequestConflict"}:
                raise WriteConflictError(key) from error
            raise

    # ---------------------------------------------------------------- 内部
    def _keys_under(self, prefix: str) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return keys


def _error_code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))
