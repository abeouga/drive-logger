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
from .repositories.work_repository import S3WorkRepository, WorkRepository
from .services.data_file_service import DataFileService
from .services.dataset_resolver import DatasetResolver, SharedDatasetResolver
from .services.pipeline_client import LambdaPipelineClient, PipelineClient
from .services.ride_service import RideService


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()


@lru_cache
def _s3_client():
    # Lambda の実行環境が使い回される間は、同じクライアントを使う（作り直しは遅い）
    return boto3.client("s3")


@lru_cache
def _lambda_client():
    return boto3.client("lambda")


def get_work_repository(settings: Settings = Depends(get_settings)) -> WorkRepository:
    return S3WorkRepository(_s3_client(), settings.work_bucket, settings.work_prefix)


def get_pipeline_client(settings: Settings = Depends(get_settings)) -> PipelineClient:
    return LambdaPipelineClient(_lambda_client(), settings.pipeline_function)


def get_ride_service(
    work: WorkRepository = Depends(get_work_repository),
    pipeline: PipelineClient = Depends(get_pipeline_client),
) -> RideService:
    return RideService(work, pipeline)


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
