"""Tests for unified CLI/MCP runtime context resolution."""

from pathlib import Path

from indexed.config import get_config, get_global_root, reload
from indexed.cli.composition import CliContext, resolve_collections_context


def test_resolve_collections_context_uses_the_one_global_store(tmp_path, monkeypatch):
    """workspace-profile/1 R1: paths always anchor to ~/.indexed/data."""
    monkeypatch.chdir(tmp_path)

    ctx = resolve_collections_context(workspace=tmp_path)

    assert isinstance(ctx, CliContext)
    assert ctx.collections_path == get_global_root() / "data" / "collections"
    assert ctx.caches_path == get_global_root() / "data" / "caches"
    assert ctx.connector_registry
    assert ctx.config_service is get_config()


def test_a_local_dot_indexed_directory_does_not_move_the_store(tmp_path, monkeypatch):
    """workspace-profile/1 R1: ./.indexed/data is never used again."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".indexed" / "data" / "collections").mkdir(parents=True)

    ctx = resolve_collections_context(workspace=tmp_path)

    assert ctx.collections_path == get_global_root() / "data" / "collections"
    assert not str(ctx.collections_path).startswith(str(tmp_path) + "/.indexed")


def test_context_has_no_storage_mode(tmp_path, monkeypatch):
    """workspace-profile/1 R1: CliContext no longer carries a storage mode."""
    monkeypatch.chdir(tmp_path)

    assert not hasattr(resolve_collections_context(workspace=tmp_path), "mode")


def test_resolve_collections_context_keeps_registered_specs(tmp_path, monkeypatch):
    """Regression (foundation/6d): a configured spec value must survive the
    call every command makes next.

    ``resolve_collections_context`` used to ``reload()`` the singleton for a
    non-None ``mode_override``, silently dropping every spec a prior
    ``register_app_config`` had registered — so a configured
    ``core.v1.embedding.batch_size`` became invisible to
    ``FaissIndexer._resolve_embedding_batch_size()``. The override is gone, but
    the invariant it broke still has to hold. The value is written to disk (not
    ``set_overlay``) so it behaves the way a real ``config set`` does.
    """
    from indexed.core.v1.config_models import CoreV1EmbeddingConfig
    from indexed.core.v1.engine.indexes.indexers.faiss_indexer import (
        _resolve_embedding_batch_size,
    )
    from indexed.cli.composition import register_app_config

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(tmp_path)

    try:
        reload()
        # Mirrors app.py's callback: register specs once, then persist a
        # distinctive value the way `config set` does (disk, not overlay).
        svc = get_config(workspace=tmp_path)
        register_app_config(svc)
        svc.set("core.v1.embedding.batch_size", 77)
        assert svc.bind().get(CoreV1EmbeddingConfig).batch_size == 77

        # This is what create/update/search/inspect/remove/MCP all do next.
        resolve_collections_context(workspace=tmp_path)

        assert _resolve_embedding_batch_size() == 77
    finally:
        reload()
