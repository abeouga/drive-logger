"""走行のファイルを消す（完全に削除。#82）。消せるのは、その走行の生データと処理の結果だけ。

置き場所は docs/data_flow_design.md 4.：
  raw  バケット  <ride_id>/ 以下のすべて（CSV・meta.json・受け付けの記録・完了の合図）
  work バケット  runs/<run_id>/rides/<ride_id>/ 以下（特徴量・点数・要約・画面用のファイル）
run.json（runs/<run_id>/run.json）とモデル（models/）は記録なので消さない。
バケットはバージョニングが有効なので、消すと「消した印」が付き、古い版は 30 日で消える（infra の noncurrent_version_days）。
"""

from typing import Protocol

DELETE_BATCH = 1000  # DeleteObjects に 1 回で渡せる数の上限


class RideFilesDeleteError(Exception):
    """S3 が一部のファイルを消せなかった。"""


class RideFilesRepository(Protocol):
    def delete_results(self, run_id: str, ride_id: str) -> int: ...
    def delete_raw(self, ride_id: str) -> int: ...


class S3RideFilesRepository:
    def __init__(self, s3_client, raw_bucket: str, raw_prefix: str, work_bucket: str, work_prefix: str) -> None:
        self._s3 = s3_client
        self._raw = (raw_bucket, raw_prefix)
        self._work = (work_bucket, work_prefix)

    def delete_results(self, run_id: str, ride_id: str) -> int:
        """処理 run_id の、この走行の結果を消す。消したファイルの数を返す。"""
        bucket, prefix = self._work
        return self._delete_prefix(bucket, f"{prefix}runs/{run_id}/rides/{ride_id}/")

    def delete_raw(self, ride_id: str) -> int:
        """この走行の生データ（フォルダーごと）を消す。消したファイルの数を返す。"""
        bucket, prefix = self._raw
        return self._delete_prefix(bucket, f"{prefix}{ride_id}/")

    def _delete_prefix(self, bucket: str, prefix: str) -> int:
        # 末尾が / の決まった prefix だけを消す（ride_001 で ride_0010 を消さないため）
        if not prefix.endswith("/"):
            raise ValueError(f"消す範囲は / で終わるフォルダーにしてください：{prefix}")
        paginator = self._s3.get_paginator("list_objects_v2")
        keys = [item["Key"] for page in paginator.paginate(Bucket=bucket, Prefix=prefix) for item in page.get("Contents", [])]
        for start in range(0, len(keys), DELETE_BATCH):
            batch = keys[start:start + DELETE_BATCH]
            response = self._s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True})
            errors = response.get("Errors", [])
            if errors:
                first = errors[0]
                raise RideFilesDeleteError(f"s3://{bucket}/{first.get('Key')} を消せませんでした（{first.get('Code')}）。ほか {len(errors) - 1} 件")
        return len(keys)
