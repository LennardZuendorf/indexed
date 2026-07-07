"""Tests for FaissIndexer in isolation (mocked embedder + faiss)."""

from unittest.mock import MagicMock

import numpy as np

from core.v1.engine.indexes.indexers.faiss_indexer import FaissIndexer


def _make_indexer(embedder=None):
    embedder = embedder or MagicMock()
    embedder.get_number_of_dimensions.return_value = 8
    return FaissIndexer("stub-indexer", embedder), embedder


class TestFaissIndexerEmptyBatch:
    """B2: a zero-chunk batch must be a safe no-op, not a crash."""

    def test_index_texts_empty_ids_and_texts_is_noop(self):
        indexer, embedder = _make_indexer()

        indexer.index_texts([], [])

        embedder.embed_batch.assert_not_called()
        assert indexer.get_size() == 0

    def test_index_texts_empty_does_not_touch_faiss_index(self):
        indexer, embedder = _make_indexer()
        indexer.faiss_index = MagicMock()

        indexer.index_texts([], [])

        indexer.faiss_index.add_with_ids.assert_not_called()


class TestFaissIndexerIndexTexts:
    def test_index_texts_embeds_and_adds(self):
        indexer, embedder = _make_indexer()
        embedder.embed_batch.return_value = np.array([[0.1] * 8, [0.2] * 8])
        indexer.faiss_index = MagicMock()

        indexer.index_texts([1, 2], ["a", "b"])

        embedder.embed_batch.assert_called_once_with(
            ["a", "b"], batch_size=64, progress_callback=None
        )
        indexer.faiss_index.add_with_ids.assert_called_once()


class TestFaissIndexerRemoveIds:
    def test_remove_ids_empty_is_noop(self):
        """Cleared research: empty remove_ids on FAISS is already a no-op."""
        indexer, _ = _make_indexer()
        indexer.faiss_index = MagicMock()

        indexer.remove_ids(np.array([], dtype=np.int64))

        indexer.faiss_index.remove_ids.assert_called_once()


class TestFaissIndexerMisc:
    def test_get_name(self):
        indexer, _ = _make_indexer()
        assert indexer.get_name() == "stub-indexer"

    def test_get_faiss_index_returns_underlying_index(self):
        indexer, _ = _make_indexer()
        indexer.faiss_index = "sentinel"
        assert indexer.get_faiss_index() == "sentinel"
