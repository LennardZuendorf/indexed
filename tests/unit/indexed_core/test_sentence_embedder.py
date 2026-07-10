"""Tests for SentenceEmbedder."""

from unittest.mock import patch, MagicMock

import numpy as np

from indexed.core.v1.engine.indexes.embeddings.sentence_embeder import (
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
    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_embed_calls_model_encode(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        result = embedder.embed("hello world")

        mock_model.encode.assert_called_once_with("hello world")
        np.testing.assert_array_equal(result, np.array([0.1, 0.2, 0.3]))

    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_model_is_lazy_loaded(self, mock_get_model):
        mock_model = MagicMock()
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        # Model not loaded yet
        mock_get_model.assert_not_called()

        # Access model property triggers loading
        _ = embedder.model
        mock_get_model.assert_called_once_with("sentence-transformers/all-MiniLM-L6-v2")

    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_max_seq_length_exposes_model_window(self, mock_get_model):
        """A4: the embedder must expose the model's real token window so
        chunkers have a single source of truth to derive max_tokens from."""
        mock_model = MagicMock()
        mock_model.max_seq_length = 256
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()

        assert embedder.max_seq_length == 256


class TestSentenceEmbedderBatch:
    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_embed_batch_without_callback(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.max_seq_length = 256
        mock_model.tokenizer.encode.return_value = [1, 2, 3]  # well within window
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

    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_embed_batch_with_progress_callback(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.max_seq_length = 256
        mock_model.tokenizer.encode.return_value = [1, 2, 3]  # well within window
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

    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_embed_batch_single_batch(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.max_seq_length = 256
        mock_model.tokenizer.encode.return_value = [1, 2, 3]  # well within window
        mock_model.encode.return_value = np.array([[0.1], [0.2]])
        mock_get_model.return_value = mock_model

        callback = MagicMock()
        embedder = SentenceEmbedder()
        embedder.embed_batch(["a", "b"], batch_size=10, progress_callback=callback)

        callback.assert_called_once_with(2)

    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_embed_batch_empty_list(self, mock_get_model):
        """B2: empty input must not consult the tokenizer/model.encode at all
        and must return a properly-shaped ``(0, dim)`` array — not
        ``np.vstack([])`` (shape ``(0,)``), which the FAISS indexer's
        ``add_with_ids`` cannot unpack."""
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        result = embedder.embed_batch([])

        mock_model.tokenizer.encode.assert_not_called()
        mock_model.encode.assert_not_called()
        assert result.shape == (0, 384)

    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_embed_batch_empty_list_with_progress_callback(self, mock_get_model):
        """B2: the empty-input guard applies regardless of progress_callback
        (previously only the callback-less branch avoided the malformed
        ``np.vstack([])`` shape)."""
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        result = embedder.embed_batch([], progress_callback=MagicMock())

        assert result.shape == (0, 384)

    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_embed_batch_splits_over_window_text(self, mock_get_model):
        """A4: a text exceeding max_seq_length is split into windows and the
        window embeddings are mean-pooled + renormalized, not truncated."""
        mock_model = MagicMock()
        mock_model.max_seq_length = 4
        mock_model.tokenizer.encode.return_value = [1, 2, 3, 4, 5, 6, 7, 8]  # 8 > 4
        mock_model.tokenizer.decode.side_effect = lambda ids: f"window-{ids}"
        mock_model.encode.return_value = np.array([[1.0, 0.0], [0.0, 1.0]])
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        result = embedder.embed_batch(["a very long text"])

        assert result.shape == (1, 2)
        # mean-pooled [0.5, 0.5] renormalized to unit length
        assert abs(float(np.linalg.norm(result[0])) - 1.0) < 1e-6

    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_embed_batch_mixed_lengths_reports_progress(self, mock_get_model):
        """A mixed batch (one short text, one over-window text) embeds each
        item individually via the per-item path and reports progress once
        per item, regardless of which branch handled it."""
        mock_model = MagicMock()
        mock_model.max_seq_length = 4

        def fake_tokenizer_encode(text, add_special_tokens=False):
            return [1] if text == "short" else [1, 2, 3, 4, 5, 6]

        mock_model.tokenizer.encode.side_effect = fake_tokenizer_encode
        mock_model.tokenizer.decode.side_effect = lambda ids: f"window-{ids}"
        mock_model.encode.side_effect = [
            np.array([1.0, 1.0]),  # the short text (single-item encode call)
            np.array([[1.0, 0.0], [0.0, 1.0]]),  # over-window text's windows
        ]
        mock_get_model.return_value = mock_model

        callback = MagicMock()
        embedder = SentenceEmbedder()
        result = embedder.embed_batch(
            ["short", "a much longer text"], progress_callback=callback
        )

        assert result.shape == (2, 2)
        assert callback.call_count == 2
        callback.assert_any_call(1)


class TestSentenceEmbedderDimensions:
    @patch(
        "indexed.core.v1.engine.indexes.embeddings.sentence_embeder.get_embedding_model"
    )
    def test_get_number_of_dimensions(self, mock_get_model):
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_get_model.return_value = mock_model

        embedder = SentenceEmbedder()
        dims = embedder.get_number_of_dimensions()

        assert dims == 384
