"""ユーザーが見るデータセットを決める。

ユーザーごとにデータを分けるときは、ここだけを差し替える
（例：Cognito のグループが admin なら DatasetId("admin") を返す）。
画面・API の URL・S3 の置き方は変えずに済む。
"""

from typing import Protocol

from ..domain.dataset import SHARED_DATASET, DatasetId
from ..domain.user import User


class DatasetResolver(Protocol):
    def resolve(self, user: User) -> DatasetId: ...


class SharedDatasetResolver:
    """今の決まり：全員が共通のデータセット（shared）を見る。"""

    def resolve(self, user: User) -> DatasetId:
        return SHARED_DATASET
