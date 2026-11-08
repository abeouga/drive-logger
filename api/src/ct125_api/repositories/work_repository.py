"""作業用のバケットを読む（走行の台帳・処理の記録・モデル）。書けるのは台帳だけ。

置き場所は docs/data_flow_design.md 4.：
  ledger/rides.json                          走行の台帳（条件付きで書く）
  runs/<run_id>/run.json                     処理の記録
  runs/<run_id>/rides/<ride_id>/summary.json 一覧用の要約
  models/<版>/model.json・notes.md            モデルの記録
  models/current.json                        今使う版
"""

import json
from typing import Protocol

from botocore.exceptions import ClientError

LEDGER_KEY = "ledger/rides.json"
NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}
CONFLICT_CODES = {"PreconditionFailed", "ConditionalRequestConflict"}


class LedgerWriteConflict(Exception):
    """読んだ後に、ほかの処理が台帳を書き換えた。"""


class WorkRepository(Protocol):
    def read_ledger(self) -> tuple[dict | None, str | None]: ...
    def write_ledger(self, ledger: dict, etag: str | None) -> None: ...
    def read_run(self, run_id: str) -> dict | None: ...
    def read_summary(self, run_id: str, ride_id: str) -> dict | None: ...
    def current_model(self) -> str | None: ...
    def model_versions(self) -> list[str]: ...
    def read_model(self, version: str) -> dict | None: ...
    def read_notes(self, version: str) -> str | None: ...
    def model_exists(self, version: str) -> bool: ...


class S3WorkRepository:
    def __init__(self, s3_client, bucket: str, prefix: str = "") -> None:
        self._s3 = s3_client
        self._bucket = bucket
        self._prefix = prefix

    # ---------------------------------------------------------------- 台帳
    def read_ledger(self) -> tuple[dict | None, str | None]:
        found = self._get(LEDGER_KEY)
        if found is None:
            return None, None
        body, etag = found
        return json.loads(body.decode("utf-8")), etag

    def write_ledger(self, ledger: dict, etag: str | None) -> None:
        kwargs = {
            "Bucket": self._bucket,
            "Key": self._key(LEDGER_KEY),
            "Body": json.dumps(ledger, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            "ContentType": "application/json; charset=utf-8",
        }
        if etag:
            kwargs["IfMatch"] = etag
        else:
            kwargs["IfNoneMatch"] = "*"
        try:
            self._s3.put_object(**kwargs)
        except ClientError as error:
            if _code(error) in CONFLICT_CODES:
                raise LedgerWriteConflict(LEDGER_KEY) from error
            raise

    # ---------------------------------------------------------------- 処理の記録
    def read_run(self, run_id: str) -> dict | None:
        return self._json(f"runs/{run_id}/run.json")

    def read_summary(self, run_id: str, ride_id: str) -> dict | None:
        return self._json(f"runs/{run_id}/rides/{ride_id}/summary.json")

    # ---------------------------------------------------------------- モデル
    def current_model(self) -> str | None:
        pointer = self._json("models/current.json")
        return str(pointer["version"]) if pointer and pointer.get("version") else None

    def model_versions(self) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        prefix = self._key("models/")
        versions = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix, Delimiter="/"):
            versions.extend(entry["Prefix"][len(prefix):].rstrip("/") for entry in page.get("CommonPrefixes", []))
        return sorted(versions, reverse=True)

    def read_model(self, version: str) -> dict | None:
        return self._json(f"models/{version}/model.json")

    def read_notes(self, version: str) -> str | None:
        found = self._get(f"models/{version}/notes.md")
        return found[0].decode("utf-8") if found else None

    def model_exists(self, version: str) -> bool:
        return self._get(f"models/{version}/baseline.json") is not None

    # ---------------------------------------------------------------- 内部
    def _key(self, relative: str) -> str:
        return f"{self._prefix}{relative}"

    def _get(self, relative: str) -> tuple[bytes, str] | None:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=self._key(relative))
        except ClientError as error:
            if _code(error) in NOT_FOUND_CODES:
                return None
            raise
        return response["Body"].read(), response["ETag"]

    def _json(self, relative: str) -> dict | None:
        found = self._get(relative)
        return json.loads(found[0].decode("utf-8")) if found else None


def _code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))
