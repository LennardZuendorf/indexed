"""Shared paths for the retrieval-eval tests."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL_DIR = REPO_ROOT / "eval"


@pytest.fixture(scope="session")
def eval_dir() -> Path:
    return EVAL_DIR


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT
