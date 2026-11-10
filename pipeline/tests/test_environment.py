# -*- coding: utf-8 -*-
"""向き先の環境（本番 prod・test）の切り替え（ct125/config.py の with_environment）のテスト。AWS には繋がない。"""
import shutil
from pathlib import Path

import pytest

from ct125 import cli
from ct125.config import ROOT, load_config


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.delenv("CT125_ENV", raising=False)
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "default.yaml", tmp_path / "config" / "default.yaml")
    return tmp_path


def _write_local(root: Path, text: str) -> None:
    (root / "config" / "local.yaml").write_text(text, encoding="utf-8")


def test_default_is_prod_with_current_names(root):
    cfg = load_config(root)
    acfg = cli.aws_settings(cfg)
    assert cfg["_env"] == "prod"
    assert acfg["bucket_name"] == "ct125-logger-{role}-{account_id}"
    assert acfg["pipeline_function"] == "ct125-ride-pipeline"
    assert acfg["device_parameter_prefix"] == "/ct125/devices/"
    assert cfg["upload"]["base_url"] == "https://drive.herdio-system.com"


def test_test_env_points_every_place_to_test(root):
    cfg = load_config(root, env="test")
    acfg = cli.aws_settings(cfg)
    assert cfg["_env"] == "test" and acfg["env"] == "test"
    assert acfg["bucket_name"] == "ct125-logger-test-{role}-{account_id}"
    assert acfg["pipeline_function"] == "ct125-test-ride-pipeline"
    assert acfg["pipeline_profile"] == "ct125-test-local-pipeline"
    assert acfg["device_parameter_prefix"] == "/ct125-test/devices/"
    assert cfg["upload"]["base_url"] == "https://drive-test.herdio-system.com"
    assert cfg["upload"]["token_file"] == "config/pc01.test.token"
    # 管理者のプロファイルとリージョンは本番と同じ（同じ AWS のプロジェクト）
    assert acfg["profile"] == "ct125-logger"


def test_env_variable_and_local_yaml_choose_the_env(root, monkeypatch):
    _write_local(root, "aws:\n  env: test\n")
    assert load_config(root)["_env"] == "test"
    monkeypatch.setenv("CT125_ENV", "prod")
    assert load_config(root)["_env"] == "prod"
    # 引数がいちばん強い
    assert load_config(root, env="test")["_env"] == "test"


def test_local_aws_values_are_not_used_for_test(root):
    # 本番用に local.yaml に書いたバケット名やプロファイルで、test を動かさない
    _write_local(
        root,
        "aws:\n  pipeline_profile: ct125-local-pipeline\n  raw_bucket: ct125-logger-raw-123\n"
        "environments:\n  test:\n    aws:\n      region: ap-northeast-1\n",
    )
    prod = cli.aws_settings(load_config(root))
    assert prod["pipeline_profile"] == "ct125-local-pipeline" and prod["raw_bucket"] == "ct125-logger-raw-123"
    test = cli.aws_settings(load_config(root, env="test"))
    assert test["pipeline_profile"] == "ct125-test-local-pipeline"
    assert "raw_bucket" not in test
    assert test["region"] == "ap-northeast-1"


def test_unknown_env_is_an_error(root):
    with pytest.raises(ValueError, match="staging"):
        load_config(root, env="staging")


def test_env_values_are_not_recorded_in_runs(root):
    from ct125.records import public_config

    recorded = public_config(load_config(root, env="test"))
    assert "environments" not in recorded and "aws" not in recorded and "local" not in recorded
