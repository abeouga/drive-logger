"""デバイス API の部品の組み立て（画面用の dependencies.py とは分ける：別の Lambda・別の権限で動くため）。"""

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import boto3
from fastapi import Depends, Header

from .config import DeviceSettings
from .domain.device import Device, DeviceCredential
from .repositories.device_token_repository import DeviceTokenRepository
from .repositories.raw_upload_repository import RawUploadRepository
from .repositories.s3_raw_upload_repository import S3RawUploadRepository, presigning_s3_client
from .repositories.ssm_device_token_repository import SsmDeviceTokenRepository
from .services.device_authenticator import DeviceAuthenticator
from .services.raw_upload_service import RawUploadService

# 走行名は日本時間で付ける（夏時間がないので固定の +9 時間でよい。Lambda に時刻帯データが無くても動く）
JST = timezone(timedelta(hours=9), "JST")


@lru_cache
def get_device_settings() -> DeviceSettings:
    return DeviceSettings.from_env()


def _region() -> str:
    """署名する S3 のリージョン。Lambda では AWS_REGION（Lambda が入れる）、手元では使っているプロファイルのリージョン。"""
    region = os.environ.get("AWS_REGION") or boto3.session.Session().region_name
    if not region:
        raise RuntimeError("リージョンが分かりません。環境変数 AWS_REGION か、AWS のプロファイルの region を設定してください")
    return region


@lru_cache
def _s3_client():
    return presigning_s3_client(_region())


@lru_cache
def _ssm_client():
    return boto3.client("ssm")


def get_device_token_repository(settings: DeviceSettings = Depends(get_device_settings)) -> DeviceTokenRepository:
    return SsmDeviceTokenRepository(_ssm_client(), settings.device_token_parameter_prefix)


def get_raw_upload_repository(settings: DeviceSettings = Depends(get_device_settings)) -> RawUploadRepository:
    return S3RawUploadRepository(_s3_client(), settings.raw_bucket, settings.raw_prefix)


def get_clock():
    return lambda: datetime.now(JST)


def get_device(
    authorization: str | None = Header(default=None),
    tokens: DeviceTokenRepository = Depends(get_device_token_repository),
) -> Device:
    credential = DeviceCredential.parse(authorization)
    return DeviceAuthenticator(tokens).authenticate(credential)


def get_raw_upload_service(
    repository: RawUploadRepository = Depends(get_raw_upload_repository),
    settings: DeviceSettings = Depends(get_device_settings),
    clock=Depends(get_clock),
) -> RawUploadService:
    return RawUploadService(repository, clock, settings.upload_url_seconds)
