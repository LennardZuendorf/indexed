"""Tests for SentenceEmbedder."""

from unittest.mock import patch, MagicMock

import numpy as np

from core.v1.engine.indexes.embeddings.sentence_embeder import (
    SentenceEmbedder,
    DEFAULT_EMBEDDING_BATCH_SIZE,
)


class TestSentenceEmbedderInit:
    def test_default_model_name(self):
        embedder = SentenceEmbedder()
        assert embedder.model_name == "sentence-transformers/all-MiniLM-L6-v2"

    def test_custom_model_name(self):
        embedder = SentenceEmbedder(model_name="custom-model")
        assert embedder.model_name == "custom-model"

    def test_default_batch_size_constant(self):
        assert DEFAULT_EMBEDDING_BATCH_SIZE == 128


class TestSentenceEmbedderEmbed:
    @patch("core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model")
    def test_embed_calls_model_encode(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        result = embedder.embed("hello world")

        mock_model.encode.assert_called_once_with("hello world")
        np.testing.assert_array_equal(result, np.array([0.1, 0.2, 0.3]))

    @patch("core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model")
    def test_model_is_lazy_loaded(self, mock_get_model):
        mock_model = MagicMock()
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        # Model not loaded yet
        mock_get_model.assert_not_called()

        # Access model property triggers loading
        _ = embedder.model
        mock_get_model.assert_called_once_with("sentence-transformers/all-MiniLM-L6-v2")


class TestSentenceEmbedderBatch:
    @patch("core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model")
    def test_embed_batch_without_callback(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        texts = ["hello", "world"]
        embedder.embed_batch(texts)

        mock_model.encode.assert_called_once_with(
            texts,
            batch_size=DEFAULT_EMBEDDING_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

    @patch("core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model")
    def test_embed_batch_with_progress_callback(self, mock_get_model):
        mock_model = MagicMock()
        # Return 2D arrays for each batch
        mock_model.encode.side_effect = [
            np.array([[0.1, 0.2], [0.3, 0.4]]),
            np.array([[0.5, 0.6]]),
        ]
        mock_get_model.return_value = mock_model

        callback = MagicMock()
        embedder = SentenceEmbedder()
        texts = ["a", "b", "c"]
        result = embedder.embed_batch(texts, batch_size=2, progress_callback=callback)

        # Callback should be called for each batch
        assert callback.call_count == 2
        callback.assert_any_call(2)  # first batch of 2
        callback.assert_any_call(1)  # second batch of 1

        # Result should be vstacked
        assert result.shape == (3, 2)

    @patch("core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model")
    def test_embed_batch_single_batch(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1], [0.2]])
        mock_get_model.return_value = mock_model

        callback = MagicMock()
        embedder = SentenceEmbedder()
        embedder.embed_batch(["a", "b"], batch_size=10, progress_callback=callback)

        callback.assert_called_once_with(2)


class TestSentenceEmbedderDimensions:
    @patch("core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model")
    def test_get_number_of_dimensions(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        dims = embedder.get_number_of_dimensions()

        assert dims == 384
