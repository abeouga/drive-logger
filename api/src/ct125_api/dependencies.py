"""部品の組み立て（依存性の注入）。

ルーターは「何が欲しいか」を Depends(...) で書くだけで、どう作るかはここに集める。
テストでは app.dependency_overrides で、ここの関数を偽物に差し替える。
"""

from functools import lru_cache

import boto3
from fastapi import Depends, Request

from .auth.current_user import read_user
from .config import Settings
from .domain.user import User
from .repositories.data_file_repository import DataFileRepository
from .repositories.s3_data_file_repository import S3DataFileRepository
from .services.data_file_service import DataFileService
from .services.dataset_resolver import DatasetResolver, SharedDatasetResolver


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


@lru_cache
def _s3_client():
    # Lambda の実行環境が使い回される間は、同じクライアントを使う（作り直しは遅い）
    return boto3.client("s3")


def get_data_file_repository(settings: Settings = Depends(get_settings)) -> DataFileRepository:
    return S3DataFileRepository(_s3_client(), settings.data_bucket, settings.data_prefix)


def get_dataset_resolver() -> DatasetResolver:
    return SharedDatasetResolver()


def get_data_file_service(
    repository: DataFileRepository = Depends(get_data_file_repository),
    resolver: DatasetResolver = Depends(get_dataset_resolver),
) -> DataFileService:
    return DataFileService(repository, resolver)


def get_current_user(request: Request, settings: Settings = Depends(get_settings)) -> User:
    return read_user(request, settings.allow_local_user)
