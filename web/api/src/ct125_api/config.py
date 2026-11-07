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

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_bucket=_required("DATA_BUCKET"),
            data_prefix=os.environ.get("DATA_PREFIX", "app/v1/datasets/"),
            allow_local_user=_flag("ALLOW_LOCAL_USER"),
        )


def _required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません")
    return value


def _flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in TRUE_VALUES
