"""データファイルの置き場所の約束（インターフェース）。

サービスはこの約束だけを知り、S3 かどうかは知らない。テストでは記憶上の偽物に差し替える。
"""

from typing import Protocol

from ..domain.data_file import DataFile, DataFileName
from ..domain.dataset import DatasetId


class DataFileRepository(Protocol):
    def read(self, dataset: DatasetId, name: DataFileName) -> DataFile:
        """ファイルを読む。無ければ DataFileNotFoundError。"""
        ...
