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


# PC に依る値は local.yaml にだけ書く。試験では本物と違う見本の値を使う
LOCAL_YAML = """aws:
  profile: admin-profile
  pipeline_profile: prod-pipeline-profile
upload:
  base_url: https://app.example.test
environments:
  test:
    aws:
      profile: admin-profile
      pipeline_profile: test-pipeline-profile
    upload:
      base_url: https://app-test.example.test
"""
TEST_NAMED = ("bucket_name", "pipeline_function", "device_parameter_prefix")


def test_default_yaml_has_no_machine_values(root):
    # 送り先とプロファイルは default.yaml に書かない（local.yaml が無ければ空）
    cfg = load_config(root)
    acfg = cli.aws_settings(cfg)
    assert cfg["_env"] == "prod"
    assert acfg["profile"] is None and acfg["pipeline_profile"] is None
    assert cfg["upload"]["base_url"] is None
    test = load_config(root, env="test")
    assert test["upload"]["base_url"] is None
    assert cli.aws_settings(test).get("pipeline_profile") is None


def test_prod_takes_machine_values_from_local_yaml(root):
    _write_local(root, LOCAL_YAML)
    cfg = load_config(root)
    acfg = cli.aws_settings(cfg)
    assert acfg["profile"] == "admin-profile"
    assert acfg["pipeline_profile"] == "prod-pipeline-profile"
    assert cfg["upload"]["base_url"] == "https://app.example.test"


def test_test_env_points_every_place_to_test(root):
    _write_local(root, LOCAL_YAML)
    prod = load_config(root)
    test = load_config(root, env="test")
    pacfg, tacfg = cli.aws_settings(prod), cli.aws_settings(test)
    assert test["_env"] == "test" and tacfg["env"] == "test"
    # 名前の決まり（infra/environment.tf と同じ）で、どの場所も本番と別の test のものを指す
    for key in TEST_NAMED:
        assert tacfg[key] != pacfg[key] and "test" in tacfg[key]
    assert test["upload"]["token_file"] != prod["upload"]["token_file"]
    # プロファイルと送り先は local.yaml の environments.test から
    assert tacfg["pipeline_profile"] == "test-pipeline-profile"
    assert tacfg["profile"] == "admin-profile"
    assert test["upload"]["base_url"] == "https://app-test.example.test"


def test_upload_sd_needs_base_url(root, tmp_path, capsys):
    # 送り先が設定に無ければ、どこにも送らずに止まる
    (root / "config" / "pc01.token").write_text("x", encoding="ascii")
    assert cli.main(["--root", str(root), "upload-sd", str(tmp_path)]) == 2
    assert "upload.base_url" in capsys.readouterr().err


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
        "aws:\n  pipeline_profile: prod-pipeline-profile\n  raw_bucket: raw-bucket-123\n"
        "environments:\n  test:\n    aws:\n      region: region-x\n",
    )
    prod = cli.aws_settings(load_config(root))
    assert prod["pipeline_profile"] == "prod-pipeline-profile" and prod["raw_bucket"] == "raw-bucket-123"
    test = cli.aws_settings(load_config(root, env="test"))
    assert test.get("pipeline_profile") is None
    assert "raw_bucket" not in test
    assert test["region"] == "region-x"


def test_unknown_env_is_an_error(root):
    with pytest.raises(ValueError, match="staging"):
        load_config(root, env="staging")


def test_env_values_are_not_recorded_in_runs(root):
    from ct125.records import public_config

    recorded = public_config(load_config(root, env="test"))
    assert "environments" not in recorded and "aws" not in recorded and "local" not in recorded
