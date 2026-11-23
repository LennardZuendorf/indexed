"""Tests for unified CLI/MCP runtime context resolution."""

import pytest

from indexed.config import (
    get_caches_path,
    get_collections_path,
    get_config,
    get_global_root,
    get_local_root,
    reload,
)
from indexed.config.collections_registry import CollectionRegistry, WorkspacePointers
from indexed.config.workspace_selection import WorkspaceSelectionError
from indexed.cli.composition import CliContext, resolve_collections_context


def _register(name: str, *, engine: str = "1"):
    """Register one collection in the global store and give it a manifest."""
    registry = CollectionRegistry()
    collection_dir = get_collections_path(get_global_root()) / name
    collection_dir.mkdir(parents=True, exist_ok=True)
    (collection_dir / "manifest.json").write_text("{}", encoding="utf-8")
    return registry.add(name=name, engine=engine, path=name, workspace="test-workspace")


def _write_definition(workspace, entries, *, version: int = 1):
    lines = [f"version = {version}", "", "[collections]", "use = ["]
    lines.extend(f'  "{entry}",' for entry in entries)
    lines.append("]")
    path = workspace / "indexed.toml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


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
    # R4: no definition means no scope and no notice.
    assert ctx.selection is None
    assert ctx.warnings == ()


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
    from indexed.core.v1.config_models import CoreV1EmbeddingConfig
    from indexed.core.v1.engine.indexes.indexers.faiss_indexer import (
        _resolve_embedding_batch_size,
    )
    from indexed.cli.composition import register_app_config

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


# --- workspace definition (#344) ---------------------------------------------


def test_definition_selects_the_global_store_from_local_mode(tmp_path, monkeypatch):
    """R1/R2: a definition pins the global store, even under --local."""
    monkeypatch.chdir(tmp_path)
    record = _register("indexed-docs")
    definition = _write_definition(tmp_path, [record.id])

    ctx = resolve_collections_context(mode_override="local", workspace=tmp_path)

    assert ctx.collections_path == get_collections_path(get_global_root())
    assert ctx.caches_path == get_caches_path(get_global_root())
    assert ctx.selection is not None
    assert ctx.selection.path == definition
    assert ctx.selection.names == ("indexed-docs",)
    # --local was explicit, so ignoring it must never be silent.
    assert len(ctx.warnings) == 1
    assert "--local is ignored" in ctx.warnings[0]


def test_definition_accepts_a_collection_name(tmp_path, monkeypatch):
    """The file stays hand-authorable: a name resolves like its id."""
    monkeypatch.chdir(tmp_path)
    _register("indexed-docs")
    _write_definition(tmp_path, ["indexed-docs"])

    ctx = resolve_collections_context(workspace=tmp_path)

    assert ctx.selection is not None
    assert ctx.selection.names == ("indexed-docs",)
    # No --local, so nothing was overridden: no notice at all.
    assert ctx.warnings == ()


def test_definition_beats_the_legacy_pointer(tmp_path, monkeypatch):
    """Precedence 1 > 2: the definition wins and the pointer is not consulted."""
    monkeypatch.chdir(tmp_path)
    record = _register("indexed-docs")
    legacy_root = tmp_path / "legacy-store"
    legacy_root.mkdir()
    WorkspacePointers(tmp_path).link("indexed-docs", record.id, legacy_root)
    _write_definition(tmp_path, [record.id])

    ctx = resolve_collections_context(workspace=tmp_path)

    assert ctx.collections_path == get_collections_path(get_global_root())
    assert ctx.warnings == ()


def test_legacy_pointer_still_routes_and_warns(tmp_path, monkeypatch):
    """Precedence 2: an already-migrated workspace keeps working, loudly."""
    monkeypatch.chdir(tmp_path)
    record = _register("indexed-docs")
    legacy_root = get_collections_path(get_global_root())
    WorkspacePointers(tmp_path).link("indexed-docs", record.id, legacy_root)

    ctx = resolve_collections_context(workspace=tmp_path)

    assert ctx.collections_path == legacy_root
    assert ctx.selection is None
    assert len(ctx.warnings) == 1
    assert "deprecated" in ctx.warnings[0]
    assert "indexed.toml" in ctx.warnings[0]


def test_definition_fails_closed_on_an_unresolvable_entry(tmp_path, monkeypatch):
    """R3: the resolver never degrades to a wider or narrower scope."""
    monkeypatch.chdir(tmp_path)
    _write_definition(tmp_path, ["0" * 32])

    with pytest.raises(WorkspaceSelectionError) as excinfo:
        resolve_collections_context(workspace=tmp_path)

    assert str(tmp_path / "indexed.toml") in str(excinfo.value)
    assert "0" * 32 in str(excinfo.value)
