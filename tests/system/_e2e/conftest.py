"""Shared fixtures for e2e tests that exercise the full embed → index → search pipeline.

These tests require the default HuggingFace embedding model. The session fixture
below downloads it once if it isn't already cached. Set INDEXED_E2E_OFFLINE=1 (or
HF_HUB_OFFLINE=1) to skip the entire suite for genuinely offline runs. CI populates
the cache via a dedicated workflow step before pytest is invoked, so the fixture
is a no-op there.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Generator

import pytest

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session", autouse=True)
def ensure_embedding_model() -> None:
    """Download the default embedding model once per session if not already cached."""
    if (
        os.environ.get("INDEXED_E2E_OFFLINE") == "1"
        or os.environ.get("HF_HUB_OFFLINE") == "1"
    ):
        pytest.skip(
            "E2E disabled (INDEXED_E2E_OFFLINE=1 or HF_HUB_OFFLINE=1); "
            "the embedding model would need to be downloaded."
        )

    from core.v1.engine.indexes.embeddings.model_manager import (
        ensure_model,
        is_model_cached,
    )

    if not is_model_cached(EMBEDDING_MODEL):
        ensure_model(EMBEDDING_MODEL)


@pytest.fixture(scope="module")
def e2e_docs(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Provide a small markdown corpus, falling back to synthetic docs if repo files are missing."""
    docs_dir = tmp_path_factory.mktemp("e2e_docs")

    real_docs = [
        _REPO_ROOT / "README.md",
        _REPO_ROOT / "docs" / "index.md",
    ]
    copied = 0
    for src in real_docs:
        if src.exists():
            shutil.copy2(src, docs_dir / src.name)
            copied += 1

    if copied == 0:
        for i in range(3):
            (docs_dir / f"e2e-test-doc-{i}.md").write_text(
                f"# E2E Test Document {i}\n\n"
                f"This document tests the full indexing pipeline. "
                f"It contains content about semantic search, embeddings, and FAISS. "
                f"Document number {i} in the e2e test corpus.\n" * 5
            )

    return docs_dir


@pytest.fixture(scope="module")
def e2e_workspace(
    tmp_path_factory: pytest.TempPathFactory,
) -> Generator[Path, None, None]:
    """Provide an isolated workspace with `.indexed/` for local-mode storage.

    Seeds `config.toml` with explicit v2 sections so `ConfigService.bind()`
    instantiates the v2 specs (the bind loop skips specs whose payload is
    ``None`` or ``{}``, which would otherwise raise ``KeyError`` on every
    `provider.get(...)` call in the v2 path). Resets the ConfigService
    singleton so a stale workspace path from a previous module doesn't leak in.
    """
    from indexed_config import ConfigService

    workspace = tmp_path_factory.mktemp("e2e_workspace")
    indexed_dir = workspace / ".indexed"
    indexed_dir.mkdir()
    (indexed_dir / "config.toml").write_text(
        '[core.v2.embedding]\nmodel_name = "all-MiniLM-L6-v2"\n'
        "[core.v2.indexing]\nchunk_size = 512\n"
        '[core.v2.storage]\nvector_store = "faiss"\n'
        "[core.v2.search]\nmax_docs = 10\n",
        encoding="utf-8",
    )
    ConfigService.reset()
    try:
        yield workspace
    finally:
        ConfigService.reset()
