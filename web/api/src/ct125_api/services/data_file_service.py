"""データファイルを読む流れ：ファイル名を検査 → データセットを決める → 置き場所から読む。"""

from ..domain.data_file import DataFile, DataFileName
from ..domain.dataset import DatasetId
from ..domain.user import User
from ..repositories.data_file_repository import DataFileRepository
from .dataset_resolver import DatasetResolver


class DataFileService:
    def __init__(self, repository: DataFileRepository, resolver: DatasetResolver) -> None:
        self._repository = repository
        self._resolver = resolver

    def dataset_for(self, user: User) -> DatasetId:
        return self._resolver.resolve(user)

    def read_file(self, user: User, raw_file_name: str) -> DataFile:
        name = DataFileName.parse(raw_file_name)
        dataset = self.dataset_for(user)
        return self._repository.read(dataset, name)
