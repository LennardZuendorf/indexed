"""Tests for the engine seam: status caching, ownership, one-collection search."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from indexed.lsp.backend import STATUS_TTL_SECONDS, KnowledgeBackend

pytestmark = pytest.mark.unit


def _status(name: str = "probe", source_type: str = "localFiles") -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        source_type=source_type,
        indexers=["indexer_FAISS"],
        updated_time="2026-11-02T09:00:00+00:00",
    )


class Recorder:
    def __init__(self, statuses: List[Any]) -> None:
        self.statuses = statuses
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> List[Any]:
        self.calls.append({"args": args, "kwargs": kwargs})
        return self.statuses


def test_statuses_are_cached_for_the_ttl_then_refreshed(tmp_path) -> None:
    now = [0.0]
    status_fn = Recorder([_status()])
    backend = KnowledgeBackend(str(tmp_path), status_fn=status_fn, clock=lambda: now[0])

    backend.statuses()
    now[0] = STATUS_TTL_SECONDS / 2
    backend.statuses()
    assert len(status_fn.calls) == 1

    now[0] = STATUS_TTL_SECONDS * 2
    backend.statuses()
    assert len(status_fn.calls) == 2
    assert status_fn.calls[0]["kwargs"] == {"collections_path": str(tmp_path)}


def test_base_path_is_read_from_the_manifest_reader(tmp_path) -> None:
    collection = tmp_path / "probe"
    collection.mkdir()
    manifest = collection / "manifest.json"
    manifest.write_text(
        json.dumps({"reader": {"type": "files", "basePath": "/repo/src"}}),
        encoding="utf-8",
    )
    now = [0.0]
    backend = KnowledgeBackend(
        str(tmp_path), status_fn=Recorder([]), clock=lambda: now[0]
    )

    assert backend.base_path("probe") == "/repo/src"
    assert backend.base_path("missing") is None

    # A repointed manifest must become visible after the TTL, not at restart.
    manifest.write_text(
        json.dumps({"reader": {"type": "files", "basePath": "/repo/lib"}}),
        encoding="utf-8",
    )
    assert backend.base_path("probe") == "/repo/src"
    now[0] = STATUS_TTL_SECONDS * 2
    assert backend.base_path("probe") == "/repo/lib"
    # A collection that never gains a manifest is re-checked, not cached forever.
    (tmp_path / "missing").mkdir()
    (tmp_path / "missing" / "manifest.json").write_text(
        json.dumps({"reader": {"type": "files", "basePath": "/repo/late"}}),
        encoding="utf-8",
    )
    assert backend.base_path("missing") == "/repo/late"


def test_base_path_is_absent_for_non_file_sources(tmp_path) -> None:
    collection = tmp_path / "jira"
    collection.mkdir()
    (collection / "manifest.json").write_text(
        json.dumps({"reader": {"type": "jira"}}), encoding="utf-8"
    )
    assert (
        KnowledgeBackend(str(tmp_path), status_fn=Recorder([])).base_path("jira")
        is None
    )


def test_ownership_prefers_the_longest_matching_base_path(tmp_path) -> None:
    for name, base in (("repo", "/repo"), ("repo-sub", "/repo/sub")):
        collection = tmp_path / name
        collection.mkdir()
        (collection / "manifest.json").write_text(
            json.dumps({"reader": {"type": "files", "basePath": base}}),
            encoding="utf-8",
        )
    backend = KnowledgeBackend(
        str(tmp_path), status_fn=Recorder([_status("repo"), _status("repo-sub")])
    )

    owned = backend.collection_for_path("/repo/sub/deep/a.py")
    assert owned is not None and owned.name == "repo-sub"
    assert backend.collection_for_path("/elsewhere/a.py") is None


def test_search_scoped_to_a_collection_passes_one_config(tmp_path) -> None:
    calls: List[Dict[str, Any]] = []

    def fake_search(query: str, **kwargs: Any) -> Dict[str, Any]:
        calls.append({"query": query, **kwargs})
        return {"probe": {"results": []}}

    backend = KnowledgeBackend(
        str(tmp_path), search_fn=fake_search, status_fn=Recorder([_status()])
    )
    backend.search("alpha", "probe", max_docs=3, max_chunks=9)

    assert calls[0]["configs"] is not None
    config = calls[0]["configs"][0]
    assert (config.name, config.indexer, config.type) == (
        "probe",
        "indexer_FAISS",
        "localFiles",
    )
    assert calls[0]["collections_path"] == str(tmp_path)
    assert calls[0]["include_matched_chunks"] is True
    assert (calls[0]["max_docs"], calls[0]["max_chunks"]) == (3, 9)


def test_search_across_all_collections_passes_no_configs(tmp_path) -> None:
    calls: List[Dict[str, Any]] = []

    def fake_search(query: str, **kwargs: Any) -> Dict[str, Any]:
        calls.append({"query": query, **kwargs})
        return {}

    backend = KnowledgeBackend(
        str(tmp_path), search_fn=fake_search, status_fn=Recorder([])
    )
    backend.search("alpha")

    assert calls[0]["configs"] is None


def test_search_for_an_unknown_collection_does_not_touch_the_engine(tmp_path) -> None:
    calls: List[Any] = []
    backend = KnowledgeBackend(
        str(tmp_path),
        search_fn=lambda *a, **k: calls.append(a) or {},
        status_fn=Recorder([_status()]),
    )
    assert backend.search("alpha", "ghost") == {}
    assert calls == []


def test_an_unknown_source_type_does_not_break_the_search_config(tmp_path) -> None:
    backend = KnowledgeBackend(
        str(tmp_path),
        search_fn=lambda *a, **k: {},
        status_fn=Recorder([_status(source_type="somethingNew")]),
    )
    config = backend._source_config(_status(source_type="somethingNew"))
    assert config.type == "localFiles"
