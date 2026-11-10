"""設定。値は環境変数から読む（Lambda では Terraform が設定する）。"""

import os
from dataclasses import dataclass

TRUE_VALUES = {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    # データを置いた S3 バケットと、データセットの親フォルダー
    data_bucket: str
    data_prefix: str
    # ローカル開発だけ true にする。ログインなしで「ローカルの開発者」として扱う。Lambda では必ず false
    allow_local_user: bool
    # 作業用のバケット（走行の台帳 ledger/・処理の記録 runs/・モデル models/）。台帳だけ書ける
    work_bucket: str = ""
    work_prefix: str = ""
    # 公開用を作り直す処理の Lambda（消す・戻す・切り替えの後に呼ぶ）
    pipeline_function: str = ""
    # 生データのバケットとフォルダー（<prefix><走行>/）。完全に削除（#82）のときだけ使う（消すだけで、読まない）
    raw_bucket: str = ""
    raw_prefix: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_bucket=_required("DATA_BUCKET"),
            data_prefix=os.environ.get("DATA_PREFIX", "datasets/"),
            allow_local_user=_flag("ALLOW_LOCAL_USER"),
            work_bucket=_required("WORK_BUCKET"),
            work_prefix=os.environ.get("WORK_PREFIX", ""),
            pipeline_function=_required("PIPELINE_FUNCTION"),
            raw_bucket=_required("RAW_BUCKET"),
            raw_prefix=os.environ.get("RAW_PREFIX", ""),
        )


@dataclass(frozen=True)
class DeviceSettings:
    """機器からのアップロード（デバイス API）の設定。画面用の Settings とは別の Lambda で使う。"""

    # 生データを置くバケットとフォルダー（raw/<走行>/）
    raw_bucket: str
    raw_prefix: str
    # 機器のトークンのハッシュを置いた SSM パラメーターの親（<prefix><機器ID>/token-sha256）
    device_token_parameter_prefix: str
    # 機器に渡す PUT 用 URL の有効期間（秒）
    upload_url_seconds: int

    @classmethod
    def from_env(cls) -> "DeviceSettings":
        return cls(
            raw_bucket=_required("RAW_BUCKET"),
            raw_prefix=os.environ.get("RAW_PREFIX", "raw/"),
            device_token_parameter_prefix=os.environ.get("DEVICE_TOKEN_PARAMETER_PREFIX", "/ct125/devices/"),
            upload_url_seconds=int(os.environ.get("UPLOAD_URL_SECONDS", "900")),
        )


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません")
    return value


def _flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in TRUE_VALUES
