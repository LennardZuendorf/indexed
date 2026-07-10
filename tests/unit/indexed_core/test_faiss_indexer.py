"""Tests for FaissIndexer in isolation (mocked embedder + faiss)."""

from unittest.mock import MagicMock

import numpy as np

from indexed.core.v1.engine.indexes.indexers.faiss_indexer import FaissIndexer


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
        """foundation/6 E12: with no config registered, falls back to the
        embedder's own default (128) instead of the old hardcoded 64."""
        indexer, embedder = _make_indexer()
        embedder.embed_batch.return_value = np.array([[0.1] * 8, [0.2] * 8])
        indexer.faiss_index = MagicMock()

        indexer.index_texts([1, 2], ["a", "b"])

        embedder.embed_batch.assert_called_once_with(
            ["a", "b"], batch_size=128, progress_callback=None
        )
        indexer.faiss_index.add_with_ids.assert_called_once()

    def test_index_texts_honors_registered_embedding_batch_size(self):
        """foundation/6 E12: a registered [core.v1.embedding] batch_size must
        actually be read instead of a hardcoded value."""
        from indexed.config import ConfigService
        from indexed.core.v1.config_models import CoreV1EmbeddingConfig

        ConfigService.reset()
        svc = ConfigService.instance()
        svc.register(CoreV1EmbeddingConfig, path="core.v1.embedding")
        # In-memory only (never touches disk) — see ConfigService.set_overlay.
        svc.set_overlay("core.v1.embedding.batch_size", 7)

        indexer, embedder = _make_indexer()
        embedder.embed_batch.return_value = np.array([[0.1] * 8, [0.2] * 8])
        indexer.faiss_index = MagicMock()

        indexer.index_texts([1, 2], ["a", "b"])

        embedder.embed_batch.assert_called_once_with(
            ["a", "b"], batch_size=7, progress_callback=None
        )
        ConfigService.reset()


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
