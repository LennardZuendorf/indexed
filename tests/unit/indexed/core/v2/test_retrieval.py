"""v2 SEARCH path tests (core-v2/2c ``retrieval.search``).

Result-shape, threshold, discovery, per-collection error handling and the
Settings-untouched proof are MODEL-FREE (MockEmbedding). The KNOWN-HIT relevance
test gates on ``model_available()`` and uses the real corpus + model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indexed.core.v2 import ingestion, retrieval
from indexed.protocols import SourceConfig

from tests.conftest import model_available

from tests.unit.indexed.core.v2._engine_helpers import (
    make_connector_factory,
    make_doc,
    mock_embedding,
)


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
