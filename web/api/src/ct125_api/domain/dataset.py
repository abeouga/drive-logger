"""データセット：ユーザーが見る走行データのまとまり（S3 の app/v1/datasets/<id>/）。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetId:
    value: str


# 今は全員がこのデータセットを見る（ユーザーごとに分けるのは将来）
SHARED_DATASET = DatasetId("shared")
