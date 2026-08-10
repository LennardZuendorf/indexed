"""Tests for unified CLI/MCP runtime context resolution."""

from indexed.cli.composition import CliContext, resolve_collections_context
from indexed.config import get_config, get_global_root, get_local_root, reload


def test_resolve_collections_context_global_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    ctx = resolve_collections_context(mode_override=None, workspace=tmp_path)

    assert isinstance(ctx, CliContext)
    assert ctx.mode == "global"
    expected = get_global_root() / "data" / "collections"
    assert ctx.collections_path == expected
    assert ctx.caches_path == get_global_root() / "data" / "caches"
    assert ctx.connector_registry
    assert ctx.config_service is get_config()


def test_resolve_collections_context_local_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    local_root = get_local_root(tmp_path)
    (local_root / "data" / "collections").mkdir(parents=True)

    ctx = resolve_collections_context(mode_override="local", workspace=tmp_path)

    assert ctx.mode == "local"
    assert ctx.collections_path == local_root / "data" / "collections"
    assert ctx.caches_path == local_root / "data" / "caches"


def test_local_override_resets_singleton(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    global_ctx = resolve_collections_context(workspace=tmp_path)
    local_ctx = resolve_collections_context(mode_override="local", workspace=tmp_path)

    assert global_ctx.collections_path != local_ctx.collections_path
    assert local_ctx.mode == "local"


def test_resolve_collections_context_restores_registered_specs(tmp_path, monkeypatch):
    """Regression (foundation/6d root-cause fix): resolve_collections_context
    forces a fresh ConfigService (via ``reload()``) whenever a non-None
    ``mode_override`` is passed — this used to silently drop every spec a
    prior ``register_app_config`` call had registered, so a configured
    ``core.v1.embedding.batch_size`` was invisible to
    ``FaissIndexer._resolve_embedding_batch_size()`` on the very path
    create/update/search/MCP all use in ``--local`` mode. The value must be
    written to disk (not ``set_overlay``) so it survives the singleton swap
    the way a real ``config set`` does; only the registry wipe is under test.
    """
    from indexed.cli.composition import register_app_config
    from indexed.core.v1.config_models import CoreV1EmbeddingConfig
    from indexed.core.v1.engine.indexes.indexers.faiss_indexer import (
        _resolve_embedding_batch_size,
    )

    monkeypatch.chdir(tmp_path)
    local_root = get_local_root(tmp_path)
    (local_root / "data" / "collections").mkdir(parents=True)

    try:
        # Mirrors app.py's callback: register specs once, then persist a
        # distinctive value the way `config set` does (disk, not overlay).
        svc = get_config(workspace=tmp_path, mode_override="local")
        register_app_config(svc)
        svc.set("core.v1.embedding.batch_size", 77)
        assert svc.bind().get(CoreV1EmbeddingConfig).batch_size == 77

        # This is what create/update/search/inspect/remove/MCP all do next.
        resolve_collections_context(mode_override="local", workspace=tmp_path)

        assert _resolve_embedding_batch_size() == 77, (
            "a registered core.v1.embedding.batch_size must survive the "
            "mode_override singleton reset in resolve_collections_context"
        )
    finally:
        reload()
