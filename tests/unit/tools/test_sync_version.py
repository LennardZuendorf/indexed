"""Tests for tools/sync_version.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SYNC_VERSION_PATH = _REPO_ROOT / "tools" / "sync_version.py"


def _load_sync_version():
    spec = importlib.util.spec_from_file_location("sync_version", _SYNC_VERSION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_version"] = module
    spec.loader.exec_module(module)
    return module


sync_version = _load_sync_version()


@pytest.mark.parametrize(
    ("raw_tag", "expected"),
    [
        ("v1.2.3", "1.2.3"),
        ("1.2.3", "1.2.3"),
        ("main", None),
        ("vvv1.0.0", None),
        ("v1.0.0-beta", None),
    ],
)
def test_parse_version(raw_tag: str, expected: str | None) -> None:
    assert sync_version.parse_version(raw_tag) == expected


def test_sync_version_updates_pyproject(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "0.0.1"\n', encoding="utf-8")

    changed = sync_version.sync_version("v0.2.0", pyproject=pyproject)

    assert changed is True
    assert pyproject.read_text(encoding="utf-8") == 'version = "0.2.0"\n'


def test_sync_version_noop_when_already_current(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "1.0.0"\n', encoding="utf-8")

    changed = sync_version.sync_version("v1.0.0", pyproject=pyproject)

    assert changed is False
    assert pyproject.read_text(encoding="utf-8") == 'version = "1.0.0"\n'


def test_sync_version_skips_non_semver(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('version = "0.0.1"\n', encoding="utf-8")

    changed = sync_version.sync_version("main", pyproject=pyproject)

    assert changed is False
    assert pyproject.read_text(encoding="utf-8") == 'version = "0.0.1"\n'


def test_sync_version_exits_when_version_field_missing(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('name = "indexed-sh"\n', encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        sync_version.sync_version("v1.0.0", pyproject=pyproject)

    assert exc_info.value.code == 1
