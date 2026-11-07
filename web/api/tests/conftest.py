"""テストの共通部品：S3 の代わりに記憶上の置き場所を使い、ログインは偽のユーザーにする。"""

import pytest
from fastapi.testclient import TestClient

from ct125_api.config import Settings
from ct125_api.dependencies import get_current_user, get_data_file_repository, get_settings
from ct125_api.domain.data_file import DataFile, DataFileName
from ct125_api.domain.dataset import DatasetId
from ct125_api.domain.exceptions import DataFileNotFoundError
from ct125_api.domain.user import User
from ct125_api.main import create_app

TEST_USER = User(user_id="user-1", username="guest", groups=())


class InMemoryDataFileRepository:
    """{(データセット, ファイル名): 中身} を持つだけの置き場所。"""

    def __init__(self, files: dict[tuple[str, str], bytes]) -> None:
        self._files = files

    def read(self, dataset: DatasetId, name: DataFileName) -> DataFile:
        content = self._files.get((dataset.value, name.value))
        if content is None:
            raise DataFileNotFoundError(f"{name.value} がありません")
        return DataFile(name=name, content=content)


@pytest.fixture
def repository() -> InMemoryDataFileRepository:
    return InMemoryDataFileRepository(
        {
            ("shared", "rides.json"): b'{"rides": []}',
            ("shared", "spec_ride_001.png"): b"\x89PNG fake",
        }
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(data_bucket="test-bucket", data_prefix="app/v1/datasets/", allow_local_user=False)


@pytest.fixture
def client(repository, settings) -> TestClient:
    """ログイン済み（TEST_USER）として呼べるクライアント。"""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_data_file_repository] = lambda: repository
    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    return TestClient(app)


@pytest.fixture
def anonymous_client(repository, settings) -> TestClient:
    """ログインしていないクライアント（claims なし、ローカルユーザーも無効）。"""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_data_file_repository] = lambda: repository
    return TestClient(app)
