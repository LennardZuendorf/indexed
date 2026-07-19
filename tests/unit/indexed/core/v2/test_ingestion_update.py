"""v2 incremental UPDATE path tests (core-v2/3 ``ingestion.update``).

All model-free via a MockEmbedding. The incrementality proof uses a RECORDING
embedding (``recording_embedding``) that captures every document chunk embedded,
so a test can assert EXACTLY the changed/new chunks were re-embedded and the
unchanged ones were not. Deletions, empty-body no-op, and build-aside
crash-safety (PR #86: an update failing mid-swap must leave the prior collection
fully searchable) are covered here too.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from indexed.core.v2 import ingestion, retrieval
from indexed.protocols import SourceConfig

from tests.unit.indexed.core.v2._engine_helpers import (
    make_connector_factory,
    make_doc,
    make_update_manifest_factory,
    mock_embedding,
    recording_embedding,
)


def _cfg(name: str) -> SourceConfig:
    return SourceConfig(name=name, type="localFiles", base_url_or_path="/corpus")


def _create(cols: Path, name: str, docs) -> None:
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg(name)],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )


def _node_ids(cols: Path, name: str) -> set[str]:
    docstore = json.loads((cols / name / "storage" / "docstore.json").read_text())
    return set(docstore["docstore/data"].keys())


def _manifest(cols: Path, name: str) -> dict:
    return json.loads((cols / name / "manifest.json").read_text())


def test_update_reembeds_only_changed_and_new_docs(tmp_path: Path) -> None:
    """R5 core scenario: modified + added + unchanged docs → exactly the changed
    set is re-embedded, unchanged docs are SKIPPED, and their node ids are STABLE."""
    cols = tmp_path / "cols"
    _create(
        cols,
        "c1",
        [make_doc("alpha", ["alpha one", "alpha two"]), make_doc("beta", ["beta one"])],
    )
    ids_before = _node_ids(cols, "c1")

    with recording_embedding(embed_dim=8) as embedded:
        ingestion.update(
            [_cfg("c1")],
            collections_path=str(cols),
            manifest_factory=make_update_manifest_factory(
                [
                    make_doc("alpha", ["alpha one", "alpha two"]),  # UNCHANGED
                    make_doc("beta", ["beta one edited", "beta two added"]),  # CHANGED
                    make_doc("gamma", ["gamma one"]),  # NEW
                ]
            ),
        )

    # Only beta's two new chunks + gamma's one chunk were embedded — alpha (the
    # unchanged doc) was NOT re-embedded (proven: no "alpha" text in the record).
    assert len(embedded) == 3, embedded
    assert not any("alpha" in text for text in embedded), embedded
    assert any("beta one edited" in text for text in embedded)
    assert any("gamma one" in text for text in embedded)

    # Unchanged doc's node ids are byte-stable across the update (present both
    # before and after — alpha was never deleted/reinserted).
    ids_after = _node_ids(cols, "c1")
    assert {"alpha::chunk_0", "alpha::chunk_1"} <= ids_before
    assert {"alpha::chunk_0", "alpha::chunk_1"} <= ids_after
    assert ids_after == {
        "alpha::chunk_0",
        "alpha::chunk_1",
        "beta::chunk_0",
        "beta::chunk_1",
        "gamma::chunk_0",
    }

    manifest = _manifest(cols, "c1")
    assert manifest["numberOfDocuments"] == 3
    assert manifest["numberOfChunks"] == 5
    assert manifest["createdTime"]  # preserved from create


def test_update_no_op_when_nothing_changed_does_not_reembed(tmp_path: Path) -> None:
    """Re-supplying identical docs re-embeds nothing (all hashes match → skip)."""
    cols = tmp_path / "cols"
    docs = [make_doc("alpha", ["alpha one"]), make_doc("beta", ["beta one"])]
    _create(cols, "c1", docs)

    with recording_embedding(embed_dim=8) as embedded:
        ingestion.update(
            [_cfg("c1")],
            collections_path=str(cols),
            manifest_factory=make_update_manifest_factory(
                [make_doc("alpha", ["alpha one"]), make_doc("beta", ["beta one"])]
            ),
        )
    assert embedded == [], "identical docs must not be re-embedded"


def test_update_honors_deletions_making_doc_unfindable(tmp_path: Path) -> None:
    """``ConnectorRun.deletions`` → ``delete_ref_doc``: the doc + nodes are gone
    and the document is no longer returned by search."""
    cols = tmp_path / "cols"
    _create(
        cols,
        "c1",
        [
            make_doc("keep", ["penguin migration antarctic"]),
            make_doc("drop", ["kubernetes autoscaler crash loop"]),
        ],
    )

    with recording_embedding(embed_dim=8) as embedded:
        ingestion.update(
            [_cfg("c1")],
            collections_path=str(cols),
            manifest_factory=make_update_manifest_factory([], deletions=["drop"]),
        )
    assert embedded == [], "a deletion-only update embeds nothing"

    ids = _node_ids(cols, "c1")
    assert ids == {"keep::chunk_0"}
    assert not any(nid.startswith("drop::") for nid in ids)

    manifest = _manifest(cols, "c1")
    assert manifest["numberOfDocuments"] == 1
    assert manifest["numberOfChunks"] == 1

    with mock_embedding(embed_dim=8):
        results = retrieval.search(
            "kubernetes autoscaler",
            configs=[_cfg("c1")],
            collections_path=str(cols),
        )
    found_ids = {r["id"] for r in results["c1"]["results"]}
    assert "drop" not in found_ids, "deleted doc must be unfindable"


def test_update_changed_doc_deletes_stale_chunks(tmp_path: Path) -> None:
    """A changed doc that SHRINKS (2 chunks → 1) drops the removed chunk's node."""
    cols = tmp_path / "cols"
    _create(cols, "c1", [make_doc("d", ["first chunk", "second chunk"])])
    assert _node_ids(cols, "c1") == {"d::chunk_0", "d::chunk_1"}

    with recording_embedding(embed_dim=8) as embedded:
        ingestion.update(
            [_cfg("c1")],
            collections_path=str(cols),
            manifest_factory=make_update_manifest_factory(
                [make_doc("d", ["only one chunk now"])]
            ),
        )
    assert len(embedded) == 1, embedded
    assert _node_ids(cols, "c1") == {"d::chunk_0"}
    assert _manifest(cols, "c1")["numberOfChunks"] == 1


def test_update_empty_body_is_timestamp_bump_not_crash(tmp_path: Path) -> None:
    """No new docs and no deletions → timestamp-only manifest bump (v1 invariant).

    Nothing is embedded, counts are unchanged, and no staging dir is left behind.
    """
    cols = tmp_path / "cols"
    _create(cols, "c1", [make_doc("d", ["only chunk"])])
    before = _manifest(cols, "c1")

    called = {"post": 0}

    def _post() -> None:
        called["post"] += 1

    with recording_embedding(embed_dim=8) as embedded:
        ingestion.update(
            [_cfg("c1")],
            collections_path=str(cols),
            manifest_factory=make_update_manifest_factory([], post_run=_post),
        )
    assert embedded == []

    after = _manifest(cols, "c1")
    assert after["updatedTime"] != before["updatedTime"], "updatedTime bumped"
    assert after["numberOfDocuments"] == before["numberOfDocuments"]
    assert after["numberOfChunks"] == before["numberOfChunks"]
    assert after["createdTime"] == before["createdTime"]
    assert called["post"] == 1, "post_run runs on the no-op path too (v1 parity)"
    assert not any(".tmp-" in p.name for p in cols.iterdir())


def test_update_calls_post_run_after_swap(tmp_path: Path) -> None:
    """The connector's ``post_run`` (files: persist change-tracker state) runs
    only after a successful update, and the final collection is already present."""
    cols = tmp_path / "cols"
    _create(cols, "c1", [make_doc("d", ["one"])])

    seen = {}

    def _post() -> None:
        # By the time post_run runs, the swap is done: the live collection has
        # the updated content on disk.
        seen["chunks"] = _manifest(cols, "c1")["numberOfChunks"]

    with mock_embedding(embed_dim=8):
        ingestion.update(
            [_cfg("c1")],
            collections_path=str(cols),
            manifest_factory=make_update_manifest_factory(
                [make_doc("d", ["one"]), make_doc("e", ["two"])], post_run=_post
            ),
        )
    assert seen["chunks"] == 2


def test_update_missing_collection_raises_typed_error(tmp_path: Path) -> None:
    from indexed.core.errors import CoreV2Error

    cols = tmp_path / "cols"
    cols.mkdir(parents=True)
    with pytest.raises(CoreV2Error, match="does not exist"):
        ingestion.update(
            [_cfg("ghost")],
            collections_path=str(cols),
            manifest_factory=make_update_manifest_factory([make_doc("d", ["x"])]),
        )


def test_update_failure_mid_swap_leaves_prior_collection_searchable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR #86 regression: an update that fails DURING the atomic swap must never
    damage the prior collection — it stays byte-identical AND fully searchable
    (build-aside: the live dir is only read until the swap)."""
    cols = tmp_path / "cols"
    _create(
        cols,
        "c1",
        [make_doc("keep", ["penguin migration antarctic coastline survey"])],
    )
    manifest_before = (cols / "c1" / "manifest.json").read_bytes()
    docstore_before = (cols / "c1" / "storage" / "docstore.json").read_bytes()

    def _boom(staging, dest):  # noqa: ANN001
        raise RuntimeError("swap boom")

    monkeypatch.setattr("indexed.core.v2.persist.replace_dir", _boom)

    with pytest.raises(RuntimeError, match="swap boom"):
        with mock_embedding(embed_dim=8):
            ingestion.update(
                [_cfg("c1")],
                collections_path=str(cols),
                manifest_factory=make_update_manifest_factory(
                    [make_doc("new", ["volcanic soil sulfur caldera"])]
                ),
            )

    # The prior collection's files are byte-identical (never mutated in place).
    assert (cols / "c1" / "manifest.json").read_bytes() == manifest_before
    assert (cols / "c1" / "storage" / "docstore.json").read_bytes() == docstore_before

    # And it is still fully searchable — the original doc is returned; the
    # would-be new doc was never swapped in.
    with mock_embedding(embed_dim=8):
        results = retrieval.search(
            "penguin migration antarctic",
            configs=[_cfg("c1")],
            collections_path=str(cols),
        )
    found = {r["id"] for r in results["c1"]["results"]}
    assert found == {"keep"}, found
