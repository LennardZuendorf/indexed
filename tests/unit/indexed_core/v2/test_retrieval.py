"""Tests for core.v2.retrieval — search/retrieval pipeline."""

from unittest.mock import MagicMock

import pytest

from core.v2.retrieval import _format_results


def _make_node_with_score(
    text: str = "chunk text",
    score: float = 0.9,
    source_id: str = "doc-1",
    url: str = "http://example.com",
    chunk_index: int = 0,
) -> MagicMock:
    """Create a mock NodeWithScore matching LlamaIndex's interface."""
    node = MagicMock()
    node.text = text
    node.node_id = f"{source_id}__chunk_{chunk_index}"
    node.metadata = {
        "source_id": source_id,
        "url": url,
        "chunk_index": chunk_index,
        "collection_name": "test-col",
    }

    nws = MagicMock()
    nws.node = node
    nws.score = score
    return nws


class TestFormatResults:
    """_format_results converts LlamaIndex results to v1-compatible format."""

    def test_basic_result(self) -> None:
        nodes = [_make_node_with_score()]
        result = _format_results("col", nodes, max_docs=10, include_matched_chunks=True)

        assert result["collectionName"] == "col"
        assert len(result["results"]) == 1
        doc = result["results"][0]
        assert doc["id"] == "doc-1"
        assert doc["url"] == "http://example.com"
        assert len(doc["matchedChunks"]) == 1

    def test_chunks_grouped_by_document(self) -> None:
        nodes = [
            _make_node_with_score(source_id="doc-1", chunk_index=0, score=0.9),
            _make_node_with_score(source_id="doc-1", chunk_index=1, score=0.8),
            _make_node_with_score(source_id="doc-2", chunk_index=0, score=0.7),
        ]
        result = _format_results("col", nodes, max_docs=10, include_matched_chunks=True)

        assert len(result["results"]) == 2
        doc1 = result["results"][0]
        assert doc1["id"] == "doc-1"
        assert len(doc1["matchedChunks"]) == 2

    def test_max_docs_truncation(self) -> None:
        nodes = [
            _make_node_with_score(source_id=f"doc-{i}") for i in range(5)
        ]
        result = _format_results("col", nodes, max_docs=2, include_matched_chunks=True)
        assert len(result["results"]) == 2

    def test_include_matched_chunks_true(self) -> None:
        nodes = [_make_node_with_score(text="hello world")]
        result = _format_results("col", nodes, max_docs=10, include_matched_chunks=True)

        chunk = result["results"][0]["matchedChunks"][0]
        assert chunk["content"]["indexedData"] == "hello world"

    def test_include_matched_chunks_false(self) -> None:
        nodes = [_make_node_with_score(text="hello world")]
        result = _format_results("col", nodes, max_docs=10, include_matched_chunks=False)

        chunk = result["results"][0]["matchedChunks"][0]
        assert "content" not in chunk

    def test_score_in_chunk(self) -> None:
        nodes = [_make_node_with_score(score=0.85)]
        result = _format_results("col", nodes, max_docs=10, include_matched_chunks=False)

        chunk = result["results"][0]["matchedChunks"][0]
        assert chunk["score"] == pytest.approx(0.85)

    def test_empty_results(self) -> None:
        result = _format_results("col", [], max_docs=10, include_matched_chunks=True)
        assert result["collectionName"] == "col"
        assert result["results"] == []

    def test_none_score_defaults_to_zero(self) -> None:
        nodes = [_make_node_with_score(score=None)]
        result = _format_results("col", nodes, max_docs=10, include_matched_chunks=False)
        assert result["results"][0]["matchedChunks"][0]["score"] == 0.0
