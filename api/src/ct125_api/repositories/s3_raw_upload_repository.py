"""S3 の raw/<走行>/ への受け付け・URL の発行・完了の合図。

raw/<走行>/upload_session.json   受け付けの記録（どの機器・どのファイル）
raw/<走行>/<ファイル>             機器が PUT 用 URL で直接置く
raw/<走行>/upload_complete.json  完了の合図（AWS 側の自動処理 ct125-ride-pipeline が動く）
raw/<走行>/upload_addition.json  送り終えた走行に走行メモを足す受け付け（#100）
_uploads/<印>.json               送り終えた走行の印（同じ SD の走行を 2 回受け付けないため。#14）
"""

import json
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from ..domain.raw_upload import MemoAddition, UploadSession

SESSION_FILE = "upload_session.json"
COMPLETE_MARKER = "upload_complete.json"
ADDITION_FILE = "upload_addition.json"
FINGERPRINT_FOLDER = "_uploads"  # 走行 ID の形でないので、処理（pipeline）は走行として数えない
NOT_FOUND_CODES = {"NoSuchKey", "404", "NotFound"}
ALREADY_EXISTS_CODES = {"PreconditionFailed", "ConditionalRequestConflict"}


def presigning_s3_client(region: str, **credentials):
    """機器に渡す URL を作るための S3 クライアント。

    - 署名は SigV4（古い SigV2 の URL は使わない）
    - リージョンのエンドポイント（s3.<region>.amazonaws.com）にする。グローバルのエンドポイントだと
      S3 がリダイレクトを返すことがあり、ESP32 の PUT（本文つき）はリダイレクトについていけない
    """
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=f"https://s3.{region}.amazonaws.com",
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
        **credentials,
    )


class S3RawUploadRepository:
    def __init__(self, s3_client, bucket: str, prefix: str) -> None:
        self._s3 = s3_client
        self._bucket = bucket
        self._prefix = prefix

    def create_session(self, session: UploadSession) -> bool:
        try:
            self._put_json(self._key(session.ride_id, SESSION_FILE), session.to_dict(), must_not_exist=True)
        except ClientError as error:
            if _code(error) in ALREADY_EXISTS_CODES:
                return False
            raise
        return True

    def find_session(self, ride_id: str) -> UploadSession | None:
        data = self._get_json(self._key(ride_id, SESSION_FILE))
        return UploadSession.from_dict(data) if data else None

    def is_complete(self, ride_id: str) -> bool:
        return self._head_size(self._key(ride_id, COMPLETE_MARKER)) is not None

    def upload_url(self, ride_id: str, file_name: str, expires_seconds: int) -> str:
        params = {"Bucket": self._bucket, "Key": self._key(ride_id, file_name)}
        return self._s3.generate_presigned_url("put_object", Params=params, ExpiresIn=expires_seconds)

    def uploaded_size(self, ride_id: str, file_name: str) -> int | None:
        return self._head_size(self._key(ride_id, file_name))

    def mark_complete(self, session: UploadSession) -> None:
        marker = {
            "ride_id": session.ride_id,
            "files": [file.name for file in session.files],
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "source": "device",
            "device_id": session.device_id,
            "local_session": session.local_session,
        }
        self._put_json(self._key(session.ride_id, COMPLETE_MARKER), marker)

    def save_addition(self, addition: MemoAddition) -> None:
        self._put_json(self._key(addition.ride_id, ADDITION_FILE), addition.to_dict())

    def find_addition(self, ride_id: str) -> MemoAddition | None:
        data = self._get_json(self._key(ride_id, ADDITION_FILE))
        return MemoAddition.from_dict(data) if data else None

    def mark_memo_added(self, ride_id: str, file_names: tuple[str, ...], when: str) -> None:
        key = self._key(ride_id, COMPLETE_MARKER)
        marker = self._get_json(key) or {"ride_id": ride_id, "files": [], "uploaded_at": when}
        marker["files"] = list(marker.get("files", [])) + [name for name in file_names if name not in marker.get("files", [])]
        marker["memo_added_at"] = when
        self._put_json(key, marker)

    def find_fingerprint(self, fingerprint: str) -> str | None:
        data = self._get_json(self._key(FINGERPRINT_FOLDER, f"{fingerprint}.json"))
        return data["ride_id"] if data else None

    def save_fingerprint(self, fingerprint: str, session: UploadSession) -> None:
        record = {
            "ride_id": session.ride_id,
            "device_id": session.device_id,
            "local_session": session.local_session,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        self._put_json(self._key(FINGERPRINT_FOLDER, f"{fingerprint}.json"), record)

    # ---------------------------------------------------------------- 内部
    def _key(self, ride_id: str, file_name: str) -> str:
        return f"{self._prefix}{ride_id}/{file_name}"

    def _head_size(self, key: str) -> int | None:
        try:
            response = self._s3.head_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if _code(error) in NOT_FOUND_CODES:
                return None
            raise
        return int(response["ContentLength"])

    def _get_json(self, key: str) -> dict | None:
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if _code(error) in NOT_FOUND_CODES:
                return None
            raise
        return json.loads(response["Body"].read().decode("utf-8"))

    def _put_json(self, key: str, data: dict, must_not_exist: bool = False) -> None:
        kwargs = {"Bucket": self._bucket, "Key": key, "Body": json.dumps(data).encode("utf-8"), "ContentType": "application/json"}
        if must_not_exist:
            kwargs["IfNoneMatch"] = "*"
        self._s3.put_object(**kwargs)


def _code(error: ClientError) -> str:
    return str(error.response.get("Error", {}).get("Code", ""))
