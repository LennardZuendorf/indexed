"""v2 CREATE path tests (core-v2/2c ``ingestion.create``).

Structural properties (manifest shape, node-count == chunk-count with NO
re-chunking, build-aside crash-safety, empty-corpus error) are MODEL-FREE via a
MockEmbedding. The KNOWN-HIT relevance test lives in the retrieval/facade
suites.
"""

from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from indexed.core.v2 import ingestion
from indexed.protocols import SourceConfig

from tests.unit.indexed.core.v2._engine_helpers import (
    make_connector_factory,
    make_doc,
    mock_embedding,
)


def _cfg(name: str) -> SourceConfig:
    return SourceConfig(name=name, type="localFiles", base_url_or_path="/corpus")


def test_create_writes_version_marked_manifest_and_storage(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    docs = [
        make_doc("needle", ["penguin migration antarctic", "more penguin facts"]),
        make_doc("other", ["kubernetes autoscaler crash loop"]),
    ]
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg("c1")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )

    manifest = json.loads((cols / "c1" / "manifest.json").read_text())
    assert manifest["version"] == "2"
    assert manifest["collectionName"] == "c1"
    assert manifest["numberOfDocuments"] == 2
    assert manifest["numberOfChunks"] == 3  # 2 + 1 chunks
    assert manifest["reader"]["type"] == "localFiles"
    assert manifest["engine"]["embedding"]["dimension"] == 8
    assert manifest["engine"]["vectorStore"] == "simple"
    assert manifest["engine"]["scoreKind"] == "cosine"

    storage_files = {p.name for p in (cols / "c1" / "storage").iterdir()}
    assert {
        "docstore.json",
        "index_store.json",
        "default__vector_store.json",
    } <= storage_files


def test_node_count_equals_chunk_count_no_rechunk(tmp_path: Path) -> None:
    """The pre-chunked nodes must NOT be re-split by LlamaIndex: exactly one node
    per input chunk, with the deterministic ``<id>::chunk_<i>`` node ids."""
    cols = tmp_path / "cols"
    docs = [
        make_doc("d1", ["chunk a", "chunk b", "chunk c"]),
        make_doc("d2", ["only one"]),
    ]
    total_chunks = 3 + 1

    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg("c1")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )

    docstore = json.loads((cols / "c1" / "storage" / "docstore.json").read_text())
    node_ids = set(docstore["docstore/data"].keys())
    assert len(node_ids) == total_chunks
    assert node_ids == {
        "d1::chunk_0",
        "d1::chunk_1",
        "d1::chunk_2",
        "d2::chunk_0",
    }
    manifest = json.loads((cols / "c1" / "manifest.json").read_text())
    assert manifest["numberOfChunks"] == total_chunks


def test_create_empty_corpus_raises_clear_error(tmp_path: Path) -> None:
    from indexed.core.errors import CoreV2Error

    cols = tmp_path / "cols"
    with mock_embedding(embed_dim=8):
        # Typed IndexedError (not a bare ValueError) so the service boundary's
        # _wrap passes the actionable message through unprefixed.
        with pytest.raises(CoreV2Error, match="No documents found"):
            ingestion.create(
                [_cfg("empty")],
                use_cache=False,
                connector_factory=make_connector_factory([]),
                collections_path=str(cols),
            )
    assert not (cols / "empty").exists()


def test_build_aside_leaves_prior_collection_intact_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A create failure mid-build (persist raises) discards only the staging dir;
    the prior collection stays byte-identical and no ``.tmp-`` dir survives."""
    cols = tmp_path / "cols"
    docs = [make_doc("d1", ["penguin migration"])]

    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg("c1")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )
    before = (cols / "c1" / "manifest.json").read_bytes()

    def boom_persist(storage_context, storage_dir):  # noqa: ANN001
        raise RuntimeError("persist boom")

    monkeypatch.setattr("indexed.core.v2.stores.persist", boom_persist)

    with mock_embedding(embed_dim=8):
        with pytest.raises(RuntimeError, match="persist boom"):
            ingestion.create(
                [_cfg("c1")],
                use_cache=False,
                connector_factory=make_connector_factory(docs),
                collections_path=str(cols),
            )

    # Prior collection untouched; no staging dir left behind.
    assert (cols / "c1" / "manifest.json").read_bytes() == before
    assert not any(p.name.startswith("c1.tmp-") for p in cols.iterdir())


def test_last_modified_document_time_is_max_across_docs(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    docs = [
        make_doc("a", ["x"], modified_time="2026-01-10T00:00:00+00:00"),
        make_doc("b", ["y"], modified_time="2026-03-01T00:00:00+00:00"),
    ]
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg("c1")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )
    manifest = json.loads((cols / "c1" / "manifest.json").read_text())
    assert manifest["lastModifiedDocumentTime"] == "2026-03-01T00:00:00+00:00"


def _kill_before_swap(staging, dest):  # noqa: ANN001
    # A BaseException (not Exception) models a hard signal-driven kill: the
    # ingestion swap wrapper catches only ``Exception`` (so a graceful failure
    # cleans up), so this bypasses cleanup and leaves the staging dir on disk —
    # exactly the post-kill state discovery must exclude.
    raise KeyboardInterrupt("simulated kill before atomic swap")


def _fail_before_swap(staging, dest):  # noqa: ANN001
    raise RuntimeError("simulated swap failure")


def test_interrupted_create_staging_dir_excluded_from_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A create hard-KILLED after the staging manifest is written but before the
    swap leaves a complete v2 collection on disk under ``<name>.tmp-...``;
    discovery (both the v2 helper AND the facade) MUST exclude it — else it
    surfaces as a phantom collection (core-v2/2c review, Critical).

    A hard kill is modeled with a ``BaseException`` so it bypasses the swap
    wrapper's graceful ``except Exception`` cleanup (a graceful failure removes
    the staging dir — see ``test_create_swap_failure_removes_staging_dir``).

    Deterministic: a letter-leading hex (``e288c54c``) is forced — that is the
    historically-escaping case, so the staging name depends only on the fix
    (pid-first prefix), not on a random uuid.
    """
    from indexed.core.engine import _existing_collection_names
    from indexed.core.v2 import ingestion as ing
    from indexed.core.v2._common import discover_v2_collections

    cols = tmp_path / "cols"
    docs = [make_doc("needle", ["penguin migration antarctic"])]

    # Force the letter-leading hex that escaped the exclusion regex pre-fix.
    monkeypatch.setattr(
        ing.uuid, "uuid4", lambda: types.SimpleNamespace(hex="e288c54c")
    )
    # Hard-kill the atomic swap so the built staging dir survives on disk.
    monkeypatch.setattr("indexed.core.v2.persist.replace_dir", _kill_before_swap)

    with mock_embedding(embed_dim=8):
        with pytest.raises(KeyboardInterrupt, match="kill before atomic swap"):
            ingestion.create(
                [_cfg("needle")],
                use_cache=False,
                connector_factory=make_connector_factory(docs),
                collections_path=str(cols),
            )

    # A complete staging collection (with manifest.json) survived the "kill".
    leftovers = [p.name for p in cols.iterdir() if p.name.startswith("needle.tmp-")]
    assert len(leftovers) == 1, f"expected one leftover staging dir, got {leftovers}"
    assert (cols / leftovers[0] / "manifest.json").is_file()

    # Neither discovery site may surface the staging dir; the real 'needle'
    # collection was never swapped in, so both return nothing.
    assert discover_v2_collections(cols) == []
    assert _existing_collection_names(str(cols)) == []


def test_create_swap_failure_removes_staging_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A graceful ``replace_dir`` swap failure (an ``Exception``) cleans up the
    ``.tmp-`` staging dir before re-raising — no leaked staging dir (matches
    ``migration._swap``). The prior collection is untouched (replace_dir rolled
    it back)."""
    cols = tmp_path / "cols"
    docs = [make_doc("d1", ["penguin migration"])]

    monkeypatch.setattr("indexed.core.v2.persist.replace_dir", _fail_before_swap)

    with mock_embedding(embed_dim=8):
        with pytest.raises(RuntimeError, match="simulated swap failure"):
            ingestion.create(
                [_cfg("c1")],
                use_cache=False,
                connector_factory=make_connector_factory(docs),
                collections_path=str(cols),
            )

    # No staging dir leaked, and the (never-created) target is absent.
    assert not any(".tmp-" in p.name for p in cols.iterdir())
    assert not (cols / "c1").exists()
