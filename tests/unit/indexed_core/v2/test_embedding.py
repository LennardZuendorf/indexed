"""Tests for core.v2.embedding — lazy HuggingFace embedding wrapper."""

from unittest.mock import MagicMock, patch

import pytest

from core.v2.embedding import get_embed_model, reset_cache
from core.v2.errors import EmbeddingError


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the embedding cache before each test."""
    reset_cache()
    yield
    reset_cache()


class TestGetEmbedModel:
    """get_embed_model lazy-loads and caches a HuggingFaceEmbedding."""

    @patch("core.v2.embedding.HuggingFaceEmbedding", create=True)
    def test_prepends_sentence_transformers_prefix(self, mock_cls: MagicMock) -> None:
        with patch.dict(
            "sys.modules",
            {
                "llama_index.embeddings.huggingface": MagicMock(
                    HuggingFaceEmbedding=mock_cls
                )
            },
        ):
            get_embed_model("all-MiniLM-L6-v2")
            mock_cls.assert_called_once_with(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )

    @patch("core.v2.embedding.HuggingFaceEmbedding", create=True)
    def test_keeps_full_repo_id(self, mock_cls: MagicMock) -> None:
        with patch.dict(
            "sys.modules",
            {
                "llama_index.embeddings.huggingface": MagicMock(
                    HuggingFaceEmbedding=mock_cls
                )
            },
        ):
            get_embed_model("my-org/my-model")
            mock_cls.assert_called_once_with(model_name="my-org/my-model")

    def test_caches_model_across_calls(self) -> None:
        mock_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "llama_index.embeddings.huggingface": MagicMock(
                    HuggingFaceEmbedding=mock_cls
                )
            },
        ):
            model1 = get_embed_model("all-MiniLM-L6-v2")
            model2 = get_embed_model("all-MiniLM-L6-v2")
            assert model1 is model2
            assert mock_cls.call_count == 1

    def test_different_model_replaces_cache(self) -> None:
        instances = [MagicMock(name="model_a"), MagicMock(name="model_b")]
        mock_cls = MagicMock(side_effect=instances)
        with patch.dict(
            "sys.modules",
            {
                "llama_index.embeddings.huggingface": MagicMock(
                    HuggingFaceEmbedding=mock_cls
                )
            },
        ):
            model1 = get_embed_model("all-MiniLM-L6-v2")
            model2 = get_embed_model("all-mpnet-base-v2")
            assert model1 is not model2
            assert mock_cls.call_count == 2

    def test_raises_embedding_error_on_import_failure(self) -> None:
        with patch.dict("sys.modules", {"llama_index.embeddings.huggingface": None}):
            with pytest.raises(
                EmbeddingError, match="llama-index-embeddings-huggingface"
            ):
                get_embed_model()

    def test_raises_embedding_error_on_load_failure(self) -> None:
        mock_cls = MagicMock(side_effect=RuntimeError("model not found"))
        with patch.dict(
            "sys.modules",
            {
                "llama_index.embeddings.huggingface": MagicMock(
                    HuggingFaceEmbedding=mock_cls
                )
            },
        ):
            with pytest.raises(EmbeddingError, match="Failed to load"):
                get_embed_model()


class TestResetCache:
    """reset_cache clears the cached model."""

    def test_reset_allows_reload(self) -> None:
        mock_cls = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "llama_index.embeddings.huggingface": MagicMock(
                    HuggingFaceEmbedding=mock_cls
                )
            },
        ):
            get_embed_model("all-MiniLM-L6-v2")
            reset_cache()
            get_embed_model("all-MiniLM-L6-v2")
            assert mock_cls.call_count == 2
