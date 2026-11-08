"""データセット：ユーザーが見る走行データのまとまり（公開用のバケットの datasets/<id>/）。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetId:
    value: str


# 今は全員がこのデータセットを見る（ユーザーごとに分けるのは将来）
SHARED_DATASET = DatasetId("shared")
