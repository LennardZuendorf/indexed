"""v2 SEARCH path tests (core-v2/2c ``retrieval.search``).

Result-shape, threshold, discovery, per-collection error handling and the
Settings-untouched proof are MODEL-FREE (MockEmbedding). The KNOWN-HIT relevance
test gates on ``model_available()`` and uses the real corpus + model.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from indexed.core.v2 import ingestion, retrieval
from indexed.core.v2.config_models import CoreV2RerankConfig
from indexed.protocols import SourceConfig

from tests.conftest import model_available

from tests.unit.indexed.core.v2._engine_helpers import (
    make_connector_factory,
    make_doc,
    mock_embedding,
)

pytestmark = pytest.mark.unit


def _cross_encoder_cached() -> bool:
    """True when the default cross-encoder rerank model is already cached.

    Mirrors ``model_available()`` for the embedding model — enabling rerank the
    first time downloads the CE model (opt-in), so real-CE tests gate on this.
    """
    from indexed.core.v2.embedding.local import _is_model_cached

    return _is_model_cached("cross-encoder/ms-marco-MiniLM-L-6-v2")


def _cfg(name: str) -> SourceConfig:
    return SourceConfig(name=name, type="localFiles", base_url_or_path="")


def _build(cols: Path, name: str, docs) -> None:
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [SourceConfig(name=name, type="localFiles", base_url_or_path="/corpus")],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )


def test_search_returns_v1_result_shape(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    docs = [make_doc("d1", ["penguin migration", "second chunk"])]
    _build(cols, "c1", docs)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            include_matched_chunks=True,
        )

    assert set(res.keys()) == {"c1"}
    per = res["c1"]
    assert per["collectionName"] == "c1"
    assert "indexerName" in per
    assert "error" not in per
    doc = per["results"][0]
    assert doc["id"] == "d1"
    assert "url" in doc and "path" in doc
    chunk = doc["matchedChunks"][0]
    assert set(chunk) == {"chunkNumber", "score", "content"}
    assert isinstance(chunk["score"], float)
    assert chunk["content"] == {"indexedData": "penguin migration"}


def test_search_omits_content_when_not_requested(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin"])])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin", configs=[_cfg("c1")], collections_path=str(cols)
        )
    chunk = res["c1"]["results"][0]["matchedChunks"][0]
    assert "content" not in chunk


def test_full_text_and_all_chunks_absent_by_default(tmp_path: Path) -> None:
    """R4 parity: neither field appears unless explicitly requested (v1)."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration", "second chunk"])])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin", configs=[_cfg("c1")], collections_path=str(cols)
        )
    doc = res["c1"]["results"][0]
    assert "text" not in doc
    assert "allChunks" not in doc


def test_include_full_text_attaches_reconstructed_text(tmp_path: Path) -> None:
    """``include_full_text`` reconstructs the document text from its chunk nodes
    (v2 keeps no ``documents/<id>.json``)."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration", "second chunk"])])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            include_full_text=True,
        )
    doc = res["c1"]["results"][0]
    assert doc["id"] == "d1"
    assert "penguin migration" in doc["text"]
    assert "second chunk" in doc["text"]


def test_include_all_chunks_returns_every_document_chunk(tmp_path: Path) -> None:
    """``include_all_chunks`` returns ALL of a matched doc's chunks (not only the
    matched ones), in order, in v1's ``{"indexedData": ...}`` shape."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration", "second chunk"])])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            include_all_chunks=True,
        )
    doc = res["c1"]["results"][0]
    all_chunks = doc["allChunks"]
    assert [c["indexedData"] for c in all_chunks] == [
        "penguin migration",
        "second chunk",
    ]
    # No original per-chunk metadata → v1's minimal on-disk shape (indexedData only).
    assert all(set(c) == {"indexedData"} for c in all_chunks)


def test_all_chunks_recovers_original_chunk_metadata(tmp_path: Path) -> None:
    """A chunk that carried its own metadata surfaces it in ``allChunks`` with the
    engine-owned keys (source_id/url/chunk_number/collection/modified_time)
    stripped — v1's on-disk ``{"indexedData", "metadata"}`` shape."""
    cols = tmp_path / "cols"
    doc = {
        "id": "d1",
        "url": "u",
        "modifiedTime": "2026-01-10T00:00:00+00:00",
        "text": "body",
        "chunks": [{"indexedData": "penguin", "metadata": {"heading": "Intro"}}],
    }
    _build(cols, "c1", [doc])
    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            include_all_chunks=True,
        )
    (chunk,) = res["c1"]["results"][0]["allChunks"]
    assert chunk["indexedData"] == "penguin"
    assert chunk["metadata"] == {"heading": "Intro"}  # engine keys stripped


def test_search_never_resolves_settings_llm(tmp_path: Path) -> None:
    """Retriever-only: the search path must NEVER read ``Settings.llm`` (no
    as_query_engine, no OpenAI-by-default trap). We install a property that
    raises on any access and assert the search still succeeds."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration"])])

    from llama_index.core import Settings

    original = type(Settings).llm

    def _boom(self):  # noqa: ANN001, ANN202
        raise AssertionError("search resolved Settings.llm — must be retriever-only")

    type(Settings).llm = property(_boom)
    try:
        with mock_embedding(embed_dim=8):
            res = retrieval.search(
                "penguin", configs=[_cfg("c1")], collections_path=str(cols)
            )
    finally:
        type(Settings).llm = original

    assert res["c1"]["results"], "search should return hits without touching the LLM"


def test_score_threshold_filters_below_cutoff(tmp_path: Path) -> None:
    """v2 threshold keeps ``score >= threshold`` (cosine, higher-better).

    MockEmbedding yields identical vectors → cosine ≈ 1.0, so a 1.5 cutoff drops
    everything while a 0.5 cutoff keeps the hit."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin"])])

    with mock_embedding(embed_dim=8):
        keep = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            score_threshold=0.5,
        )
        drop = retrieval.search(
            "penguin",
            configs=[_cfg("c1")],
            collections_path=str(cols),
            score_threshold=1.5,
        )

    assert keep["c1"]["results"]
    assert drop["c1"]["results"] == []


def test_search_discovers_all_v2_collections_when_configs_none(tmp_path: Path) -> None:
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin"])])
    _build(cols, "c2", [make_doc("d2", ["walrus"])])

    with mock_embedding(embed_dim=8):
        res = retrieval.search("anything", configs=None, collections_path=str(cols))

    assert set(res.keys()) == {"c1", "c2"}


def test_search_missing_collection_returns_error_entry_not_raise(
    tmp_path: Path,
) -> None:
    cols = tmp_path / "cols"
    cols.mkdir()
    with mock_embedding(embed_dim=8):
        res = retrieval.search("q", configs=[_cfg("ghost")], collections_path=str(cols))
    assert "error" in res["ghost"]


@pytest.mark.slow
@pytest.mark.skipif(
    not model_available(), reason="Embedding model not cached (all-MiniLM-L6-v2)"
)
def test_search_known_hit_with_real_model(tmp_path: Path, files_corpus: Path) -> None:
    """Real model + real files corpus: the needle doc is the top hit for its
    query, and a different query ranks a different doc first (not just 'no
    error')."""
    from indexed.connectors.files.connector import FileSystemConnector

    cols = tmp_path / "cols"
    ingestion.create(
        [
            SourceConfig(
                name="files-v2", type="localFiles", base_url_or_path=str(files_corpus)
            )
        ],
        use_cache=False,
        connector_factory=lambda cfg: FileSystemConnector(path=str(files_corpus)),
        collections_path=str(cols),
    )

    needle = retrieval.search(
        "penguin migration antarctic coastline",
        configs=[_cfg("files-v2")],
        collections_path=str(cols),
        include_matched_chunks=True,
    )
    ranked = [d["id"] for d in needle["files-v2"]["results"]]
    assert ranked, "expected at least one hit"
    assert ranked[0] == "needle.txt", ranked

    other = retrieval.search(
        "semantic search finds documents by meaning",
        configs=[_cfg("files-v2")],
        collections_path=str(cols),
    )
    other_ranked = [d["id"] for d in other["files-v2"]["results"]]
    assert other_ranked[0] != "needle.txt", other_ranked
    # v2 score is cosine, higher-is-better (0..1).
    top_score = needle["files-v2"]["results"][0]["matchedChunks"][0]["score"]
    assert 0.0 < top_score <= 1.0


# --- R10: optional reranking -------------------------------------------------


def test_rerank_disabled_imports_no_cross_encoder(tmp_path: Path) -> None:
    """Disabled (the default) → zero cost: the search must import NO
    ``sentence_transformers`` / ``CrossEncoder`` at all.

    An import guard fails the search if any ``sentence_transformers`` import is
    attempted during a rerank-disabled search (MockEmbedding, so nothing else
    would legitimately import it)."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration"]), make_doc("d2", ["x"])])

    import builtins

    real_import = builtins.__import__

    def _guard(name, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        if name == "sentence_transformers" or name.startswith("sentence_transformers."):
            raise AssertionError(f"rerank disabled must not import {name!r}")
        return real_import(name, *args, **kwargs)

    with mock_embedding(embed_dim=8):
        with patch("builtins.__import__", side_effect=_guard):
            res = retrieval.search(
                "penguin", configs=[_cfg("c1")], collections_path=str(cols)
            )
    assert res["c1"]["results"], "disabled-rerank search still returns hits"


def test_rerank_enabled_reorders_and_respects_top_n(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enabled → the postprocessor is constructed with the configured model +
    ``top_n``, and its reordered/truncated node list drives the output (order
    changes, ``top_n`` respected). Deterministic via a FAKE reranker (no CE
    download), so this runs everywhere; the real-CE path is a gated test below.
    """
    cols = tmp_path / "cols"
    _build(
        cols,
        "c1",
        [
            make_doc("d1", ["alpha"]),
            make_doc("d2", ["beta"]),
            make_doc("d3", ["gamma"]),
        ],
    )

    with mock_embedding(embed_dim=8):
        baseline = retrieval.search(
            "alpha", configs=[_cfg("c1")], collections_path=str(cols)
        )
    baseline_ids = [d["id"] for d in baseline["c1"]["results"]]
    assert len(baseline_ids) == 3

    monkeypatch.setattr(
        "indexed.core.v2.retrieval.resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, model="test-ce", top_n=2),
    )

    import llama_index.core.postprocessor as pp

    class _FakeRerank:
        seen: dict = {}

        def __init__(self, *, model: str, top_n: int) -> None:
            _FakeRerank.seen = {"model": model, "top_n": top_n}
            self._top_n = top_n

        def postprocess_nodes(self, nodes, *, query_str=None, query_bundle=None):  # noqa: ANN001, ANN002, ANN003, ANN202
            # Reverse (so order provably changes) and truncate to top_n.
            return list(reversed(nodes))[: self._top_n]

    monkeypatch.setattr(pp, "SentenceTransformerRerank", _FakeRerank)

    with mock_embedding(embed_dim=8):
        reranked = retrieval.search(
            "alpha", configs=[_cfg("c1")], collections_path=str(cols)
        )
    reranked_ids = [d["id"] for d in reranked["c1"]["results"]]

    assert _FakeRerank.seen == {"model": "test-ce", "top_n": 2}
    assert len(reranked_ids) == 2  # top_n respected
    assert reranked_ids == list(reversed(baseline_ids))[:2]  # order changed


@pytest.mark.unit
def test_reranked_response_uses_rerank_score_kind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enabled rerank REPLACES ``NodeWithScore.score`` with a cross-encoder
    relevance, so the response must report ``scoreKind == "rerank"`` — not the
    manifest's ``"cosine"`` — or downstream mixed-engine sorting mislabels the
    scores (PR #158 review #8). ``_apply_rerank`` is stubbed to identity so no
    real cross-encoder loads."""
    cols = tmp_path / "cols"
    _build(cols, "c1", [make_doc("d1", ["penguin migration"])])

    monkeypatch.setattr(
        retrieval,
        "resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, model="x", top_n=3),
    )
    monkeypatch.setattr(retrieval, "_apply_rerank", lambda nws, q, cfg: nws)

    with mock_embedding(embed_dim=8):
        res = retrieval.search(
            "penguin", configs=[_cfg("c1")], collections_path=str(cols)
        )

    assert res["c1"]["scoreKind"] == "rerank"


@pytest.mark.slow
@pytest.mark.skipif(
    not (model_available() and _cross_encoder_cached()),
    reason="embedding or cross-encoder model not cached",
)
def test_rerank_enabled_real_cross_encoder(
    tmp_path: Path, files_corpus: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real cross-encoder over the real corpus: rerank runs end to end and
    honours ``top_n`` (opt-in; gated on the CE model being cached)."""
    from indexed.connectors.files.connector import FileSystemConnector

    cols = tmp_path / "cols"
    ingestion.create(
        [
            SourceConfig(
                name="files-v2", type="localFiles", base_url_or_path=str(files_corpus)
            )
        ],
        use_cache=False,
        connector_factory=lambda cfg: FileSystemConnector(path=str(files_corpus)),
        collections_path=str(cols),
    )

    monkeypatch.setattr(
        "indexed.core.v2.retrieval.resolve_rerank_config",
        lambda: CoreV2RerankConfig(enabled=True, top_n=2),
    )
    res = retrieval.search(
        "penguin migration antarctic coastline",
        configs=[_cfg("files-v2")],
        collections_path=str(cols),
        include_matched_chunks=True,
    )
    docs = res["files-v2"]["results"]
    assert docs, "reranked search returns hits"
    assert len(docs) <= 2  # top_n respected
