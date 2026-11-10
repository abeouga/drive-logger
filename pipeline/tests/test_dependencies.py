# -*- coding: utf-8 -*-
"""ライブラリの版の固定：pyproject.toml と Lambda のコンテナ（deploy/lambda/requirements.txt）が同じ版か。

学習済みモデル（skops）は、学習したときと同じ版で読む必要がある（models.py が model.json と突き合わせる）。
"""
import re
import tomllib
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]


def _pins(lines):
    pins = {}
    for line in lines:
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([0-9][A-Za-z0-9_.]*)", line)
        assert match, f"版を == で固定していません：{line}"
        pins[match.group(1).lower()] = match.group(2)
    return pins


def test_pyproject_and_container_use_the_same_versions():
    project = tomllib.loads((PIPELINE / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    container = (PIPELINE / "deploy" / "lambda" / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert _pins(project["dependencies"]) == _pins(container)


def test_installed_versions_match_the_pins():
    from importlib.metadata import version

    project = tomllib.loads((PIPELINE / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    for name, pinned in _pins(project["dependencies"]).items():
        assert version(name) == pinned, name
