"""Shared paths for the retrieval-eval tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL_DIR = REPO_ROOT / "eval"

# Capture the intended cache before the session fixture redirects HOME.
EVAL_MODEL_CACHE = (
    Path(
        os.environ.get("HF_HUB_CACHE")
        or Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
        / "hub"
    )
    .expanduser()
    .resolve()
)


@pytest.fixture(autouse=True)
def isolate_git_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep Git hook repository selectors out of temporary eval repositories."""
    for name in (
        "GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG GIT_CONFIG_PARAMETERS "
        "GIT_CONFIG_COUNT GIT_OBJECT_DIRECTORY GIT_DIR GIT_WORK_TREE "
        "GIT_IMPLICIT_WORK_TREE GIT_GRAFT_FILE GIT_INDEX_FILE "
        "GIT_NO_REPLACE_OBJECTS GIT_REPLACE_REF_BASE GIT_PREFIX "
        "GIT_SHALLOW_FILE GIT_COMMON_DIR"
    ).split():
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def eval_dir() -> Path:
    return EVAL_DIR


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def eval_model_cache(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use one explicit, offline cache for both availability and model loading."""
    monkeypatch.setenv("HF_HUB_CACHE", str(EVAL_MODEL_CACHE))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    return EVAL_MODEL_CACHE
