"""Unit tests for the version-dispatching facade ``indexed.core.engine``.

Covers plan.md scenarios: surface parity with v1, unmarked collections routing
to v1 for every op, and an explicit ``--engine v2`` selector raising
``EngineMismatchError`` before any I/O (v2 not yet implemented).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_collection(base: Path, name: str, payload: dict | None = None) -> Path:
    coll = base / name
    coll.mkdir(parents=True, exist_ok=True)
    body = {"collectionName": name, "numberOfDocuments": 1}
    if payload:
        body.update(payload)
    (coll / "manifest.json").write_text(json.dumps(body), encoding="utf-8")
    return coll


# --- surface parity ----------------------------------------------------------


def test_facade_all_matches_v1_exports() -> None:
    import indexed.core.engine as facade
    import indexed.core.v1.engine as v1

    assert set(facade.__all__) == set(v1._EXPORTS)


def test_facade_dir_matches_v1_exports() -> None:
    import indexed.core.engine as facade
    import indexed.core.v1.engine as v1

    assert set(dir(facade)) == set(v1._EXPORTS)


def test_shared_types_are_reexported_from_v1() -> None:
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    for name in (
        "SourceConfig",
        "CollectionStatus",
        "CollectionInfo",
        "PhasedProgressCallback",
        "SearchService",
        "InspectService",
    ):
        assert getattr(facade, name) is getattr(v1_services, name)


def test_routed_callables_exist() -> None:
    import indexed.core.engine as facade

    for name in (
        "create",
        "update",
        "clear",
        "collection_exists",
        "search",
        "status",
        "inspect",
    ):
        assert callable(getattr(facade, name))


# --- default path routes to v1 unchanged (engine=None) -----------------------


def test_clear_without_engine_routes_to_v1(monkeypatch, tmp_path: Path) -> None:
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    calls = []
    monkeypatch.setattr(
        v1_services,
        "clear",
        lambda names, collections_path=None: calls.append((names, collections_path)),
    )

    facade.clear(["c"], collections_path=str(tmp_path))

    assert calls == [(["c"], str(tmp_path))]


def test_status_without_engine_routes_to_v1(monkeypatch, tmp_path: Path) -> None:
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    sentinel = object()
    monkeypatch.setattr(
        v1_services,
        "status",
        lambda collection_names=None, **kw: sentinel,
    )

    result = facade.status(["c"], collections_path=str(tmp_path))

    assert result is sentinel


def test_collection_exists_without_engine_does_not_detect(tmp_path: Path) -> None:
    """A create-gate existence check on a non-existent collection must return
    False, never raise — engine=None must not trigger detection I/O."""
    import indexed.core.engine as facade

    assert facade.collection_exists("nope", collections_path=str(tmp_path)) is False


def test_create_without_engine_routes_to_v1(monkeypatch, tmp_path: Path) -> None:
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    captured = {}

    def fake_create(configs, **kwargs):
        captured["configs"] = configs
        captured["kwargs"] = kwargs

    monkeypatch.setattr(v1_services, "create", fake_create)

    facade.create(
        ["cfg"],
        connector_factory=lambda c: None,
        collections_path=str(tmp_path),
    )

    assert captured["configs"] == ["cfg"]
    assert "engine" not in captured["kwargs"]


# --- explicit engine="1" confirms and routes to v1 ---------------------------


def test_status_engine_one_on_unmarked_collection_routes_to_v1(
    monkeypatch, tmp_path: Path
) -> None:
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    _make_collection(tmp_path, "legacy")
    sentinel = object()
    monkeypatch.setattr(v1_services, "status", lambda *a, **kw: sentinel)

    result = facade.status(["legacy"], collections_path=str(tmp_path), engine="1")

    assert result is sentinel


# --- explicit engine="2" on a v1 collection raises mismatch ------------------


def test_clear_engine_two_on_unmarked_raises_mismatch(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.errors import EngineMismatchError

    _make_collection(tmp_path, "legacy")

    with pytest.raises(EngineMismatchError) as excinfo:
        facade.clear(["legacy"], collections_path=str(tmp_path), engine="2")

    message = str(excinfo.value)
    assert "legacy" in message
    assert "v1 collection" in message
    assert "--engine v1" in message
    assert "indexed index migrate legacy" in message


def test_status_engine_two_on_unmarked_raises_mismatch(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.errors import EngineMismatchError

    _make_collection(tmp_path, "legacy")

    with pytest.raises(EngineMismatchError):
        facade.status(["legacy"], collections_path=str(tmp_path), engine="2")


def test_inspect_engine_two_on_unmarked_raises_mismatch(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.errors import EngineMismatchError

    _make_collection(tmp_path, "legacy")

    with pytest.raises(EngineMismatchError):
        facade.inspect(["legacy"], collections_path=str(tmp_path), engine="2")


def test_search_engine_two_on_unmarked_raises_mismatch(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.errors import EngineMismatchError

    _make_collection(tmp_path, "legacy")
    cfg = facade.SourceConfig(name="legacy", type="localFiles", base_url_or_path="")

    with pytest.raises(EngineMismatchError):
        facade.search("q", configs=[cfg], collections_path=str(tmp_path), engine="2")


def test_update_engine_two_on_unmarked_raises_mismatch(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.errors import EngineMismatchError

    _make_collection(tmp_path, "legacy")
    cfg = facade.SourceConfig(name="legacy", type="localFiles", base_url_or_path="")

    with pytest.raises(EngineMismatchError):
        facade.update(
            [cfg],
            collections_path=str(tmp_path),
            manifest_factory=lambda m, p: None,
            engine="2",
        )


# --- create with engine="2": v2 not yet available ----------------------------


def test_create_engine_two_raises_not_available(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.errors import EngineNotAvailableError

    with pytest.raises(EngineNotAvailableError):
        facade.create(
            ["cfg"],
            engine="2",
            connector_factory=lambda c: None,
            collections_path=str(tmp_path),
        )


def test_create_engine_two_does_not_import_llama_index(tmp_path: Path) -> None:
    """The v2 branch must fail before importing any heavy engine module."""
    import sys

    import indexed.core.engine as facade
    from indexed.core.errors import EngineNotAvailableError

    with pytest.raises(EngineNotAvailableError):
        facade.create(
            ["cfg"],
            engine="2",
            connector_factory=lambda c: None,
            collections_path=str(tmp_path),
        )

    assert "llama_index" not in sys.modules


# --- routing edge cases ------------------------------------------------------


def test_invalid_engine_selector_raises_configuration_error(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.config.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        facade.clear(["x"], collections_path=str(tmp_path), engine="3")


def test_update_without_engine_routes_to_v1(monkeypatch, tmp_path: Path) -> None:
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    captured = {}
    monkeypatch.setattr(
        v1_services,
        "update",
        lambda configs, **kw: captured.update({"configs": configs, "kw": kw}),
    )
    cfg = facade.SourceConfig(name="c", type="localFiles", base_url_or_path="")

    facade.update(
        [cfg], collections_path=str(tmp_path), manifest_factory=lambda m, p: None
    )

    assert captured["configs"] == [cfg]
    assert "engine" not in captured["kw"]


def test_search_all_collections_engine_two_enumerates_and_mismatches(
    tmp_path: Path,
) -> None:
    """search(configs=None) with an explicit engine enumerates on-disk
    collections and raises on the v1 collection it finds."""
    import indexed.core.engine as facade
    from indexed.core.errors import EngineMismatchError

    _make_collection(tmp_path, "legacy")

    with pytest.raises(EngineMismatchError):
        facade.search("q", configs=None, collections_path=str(tmp_path), engine="2")


def test_clear_engine_two_on_missing_collection_is_not_available(
    tmp_path: Path,
) -> None:
    """An explicit engine on a non-existent collection skips detection (nothing
    to conflict with) and routes to the requested engine (v2 unavailable)."""
    import indexed.core.engine as facade
    from indexed.core.errors import EngineNotAvailableError

    with pytest.raises(EngineNotAvailableError):
        facade.clear(["ghost"], collections_path=str(tmp_path), engine="2")


def test_internal_tmp_dirs_excluded_from_enumeration(tmp_path: Path) -> None:
    """Build-aside/trash dirs are skipped when enumerating for an explicit
    engine, so they don't spuriously trigger a mismatch."""
    import indexed.core.engine as facade
    from indexed.core.errors import EngineNotAvailableError

    _make_collection(tmp_path, "col.tmp-1234")
    _make_collection(tmp_path, "col.trash-99")

    # Only transient dirs exist -> nothing real to conflict with -> routes to v2.
    with pytest.raises(EngineNotAvailableError):
        facade.search("q", configs=None, collections_path=str(tmp_path), engine="2")
