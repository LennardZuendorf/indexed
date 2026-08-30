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


# --- default path (engine=None) is manifest-authoritative ---------------------


def test_status_without_engine_on_unknown_marker_raises(tmp_path: Path) -> None:
    """A default-path op on a readable ``version:"3"`` collection fails loud
    (never a silent v1 fallback), leaving the collection untouched."""
    import indexed.core.engine as facade
    from indexed.core.errors import UnknownEngineVersionError

    coll = _make_collection(tmp_path, "future", {"version": "3"})
    before = (coll / "manifest.json").read_bytes()

    with pytest.raises(UnknownEngineVersionError):
        facade.status(["future"], collections_path=str(tmp_path))

    assert (coll / "manifest.json").read_bytes() == before


def test_clear_without_engine_on_unknown_marker_raises(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.errors import UnknownEngineVersionError

    coll = _make_collection(tmp_path, "future", {"version": "3"})
    assert coll.is_dir()

    with pytest.raises(UnknownEngineVersionError):
        facade.clear(["future"], collections_path=str(tmp_path))

    # Fail loud, touch nothing: the collection dir is still present.
    assert coll.is_dir()


def test_search_without_engine_on_unknown_marker_raises(tmp_path: Path) -> None:
    import indexed.core.engine as facade
    from indexed.core.errors import UnknownEngineVersionError

    _make_collection(tmp_path, "future", {"version": "3"})
    cfg = facade.SourceConfig(name="future", type="localFiles", base_url_or_path="")

    with pytest.raises(UnknownEngineVersionError):
        facade.search("q", configs=[cfg], collections_path=str(tmp_path))


def test_status_without_engine_on_v1_marker_routes_to_v1(
    monkeypatch, tmp_path: Path
) -> None:
    """A default-path op on a marked ``version:"1"`` collection detects v1 and
    routes to it (one extra manifest read is acceptable)."""
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    _make_collection(tmp_path, "legacy", {"version": "1"})
    sentinel = object()
    monkeypatch.setattr(v1_services, "status", lambda *a, **kw: sentinel)

    result = facade.status(["legacy"], collections_path=str(tmp_path))

    assert result is sentinel


def test_status_without_engine_on_corrupt_manifest_does_not_raise(
    monkeypatch, tmp_path: Path
) -> None:
    """A default-path op on a collection with a CORRUPT manifest must NOT raise
    from the facade — detection swallows the collection-level ``ValueError`` and
    falls through to v1's own corrupt-collection handling (R6)."""
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    corrupt = tmp_path / "corrupt"
    corrupt.mkdir()
    (corrupt / "manifest.json").write_text("{ not valid json", encoding="utf-8")

    sentinel = object()
    monkeypatch.setattr(v1_services, "status", lambda *a, **kw: sentinel)

    # No exception escapes the facade; it routes to v1 (default engine).
    result = facade.status(["corrupt"], collections_path=str(tmp_path))
    assert result is sentinel


def test_collection_exists_without_engine_on_unknown_marker_does_not_raise(
    tmp_path: Path,
) -> None:
    """``collection_exists`` stays engine-agnostic: a filesystem existence probe
    that must not fail loud even on a readable unknown marker."""
    import indexed.core.engine as facade

    _make_collection(tmp_path, "future", {"version": "3"})

    # Must not raise UnknownEngineVersionError — this is a pure existence check.
    assert facade.collection_exists("future", collections_path=str(tmp_path)) is True


# --- explicit engine="1" on a v1 collection is a regression check ------------


def test_update_engine_one_on_v1_marker_routes_to_v1(
    monkeypatch, tmp_path: Path
) -> None:
    """``update --engine v1`` on a v1 collection works (no TypeError) and routes
    to v1 — the retargeted update seam must accept ``engine=``."""
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    _make_collection(tmp_path, "legacy", {"version": "1"})
    captured = {}
    monkeypatch.setattr(
        v1_services,
        "update",
        lambda configs, **kw: captured.update({"configs": configs, "kw": kw}),
    )
    cfg = facade.SourceConfig(name="legacy", type="localFiles", base_url_or_path="")

    facade.update(
        [cfg],
        collections_path=str(tmp_path),
        manifest_factory=lambda m, p: None,
        engine="1",
    )

    assert captured["configs"] == [cfg]
    # engine is resolved by the facade, never forwarded into v1's signature.
    assert "engine" not in captured["kw"]


def test_update_engine_two_mismatch_message_names_both_engines_and_remedy(
    tmp_path: Path,
) -> None:
    """``update --engine v2`` on a v1 collection raises ``EngineMismatchError``
    whose message names both engines and the migrate remedy (R2 surfacing)."""
    import indexed.core.engine as facade
    from indexed.core.errors import EngineMismatchError

    _make_collection(tmp_path, "legacy", {"version": "1"})
    cfg = facade.SourceConfig(name="legacy", type="localFiles", base_url_or_path="")

    with pytest.raises(EngineMismatchError) as excinfo:
        facade.update(
            [cfg],
            collections_path=str(tmp_path),
            manifest_factory=lambda m, p: None,
            engine="2",
        )

    message = str(excinfo.value)
    assert "v1" in message and "v2" in message
    assert "indexed index migrate legacy" in message


# --- create with engine="2": v2 is now available (core-v2/2c) -----------------


def test_create_engine_two_routes_to_v2(monkeypatch, tmp_path: Path) -> None:
    """``create --engine v2`` now routes to the real v2 engine services."""
    import indexed.core.engine as facade
    import indexed.core.v2.services as v2_services

    captured: dict = {}
    monkeypatch.setattr(
        v2_services,
        "create",
        lambda configs, **kw: captured.update({"configs": configs, "kw": kw}),
    )

    facade.create(
        ["cfg"],
        engine="2",
        connector_factory=lambda c: None,
        collections_path=str(tmp_path),
    )

    assert captured["configs"] == ["cfg"]
    # engine is resolved by the facade, never forwarded into the engine signature.
    assert "engine" not in captured["kw"]


def test_create_engine_two_on_v1_marker_raises_mismatch(tmp_path: Path) -> None:
    """``create --engine v2`` against an EXISTING v1 collection must raise
    ``EngineMismatchError`` before any I/O, not silently overwrite it (#185)."""
    import indexed.core.engine as facade
    from indexed.core.errors import EngineMismatchError

    _make_collection(tmp_path, "legacy", {"version": "1"})
    cfg = facade.SourceConfig(name="legacy", type="localFiles", base_url_or_path="")

    with pytest.raises(EngineMismatchError) as excinfo:
        facade.create(
            [cfg],
            engine="2",
            connector_factory=lambda c: None,
            collections_path=str(tmp_path),
        )

    message = str(excinfo.value)
    assert "v1" in message and "v2" in message
    assert "indexed index migrate legacy" in message


def test_create_without_engine_on_existing_v2_collection_routes_to_v2(
    monkeypatch, tmp_path: Path
) -> None:
    """Re-running ``create`` with no ``--engine`` against an existing v2
    collection must route to v2 (matching the on-disk manifest), not silently
    dispatch to the v1 default and replace the collection (#185)."""
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services
    import indexed.core.v2.services as v2_services

    _make_collection(tmp_path, "flip-test", {"version": "2"})
    captured: dict = {}
    monkeypatch.setattr(
        v2_services,
        "create",
        lambda configs, **kw: captured.update({"configs": configs, "kw": kw}),
    )
    monkeypatch.setattr(
        v1_services,
        "create",
        lambda *a, **kw: pytest.fail("must not route to v1"),
    )
    cfg = facade.SourceConfig(name="flip-test", type="localFiles", base_url_or_path="")

    facade.create(
        [cfg],
        connector_factory=lambda c: None,
        collections_path=str(tmp_path),
    )

    assert captured["configs"] == [cfg]


def test_v2_services_module_import_is_llama_index_lazy() -> None:
    """Resolving the v2 engine services module (what ``_engine_impl('2')`` does)
    must NOT import llama-index at module top, keeping CLI startup <1s."""
    import subprocess
    import sys

    code = (
        "import indexed.core.v2.services\n"
        "import sys\n"
        "bad = sorted(m for m in sys.modules if m.startswith('llama_index'))\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


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


def test_clear_engine_two_on_missing_collection_routes_to_v2(
    tmp_path: Path,
) -> None:
    """An explicit engine on a non-existent collection skips detection (nothing
    to conflict with) and routes to v2, whose clear is a safe no-op."""
    import indexed.core.engine as facade

    # Must not raise: v2 clear of a non-existent dir is a no-op.
    facade.clear(["ghost"], collections_path=str(tmp_path), engine="2")
    assert not (tmp_path / "ghost").exists()


def test_internal_tmp_dirs_excluded_from_enumeration(tmp_path: Path) -> None:
    """Build-aside/trash dirs are skipped when enumerating for an explicit
    engine, so they don't spuriously trigger a mismatch and route cleanly to
    v2 (which discovers no real collection and returns an empty result set)."""
    import indexed.core.engine as facade

    _make_collection(tmp_path, "col.tmp-1234")
    _make_collection(tmp_path, "col.trash-99")

    result = facade.search(
        "q", configs=None, collections_path=str(tmp_path), engine="2"
    )
    assert result == {}
