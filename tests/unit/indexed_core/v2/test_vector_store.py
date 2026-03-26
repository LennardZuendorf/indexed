"""Tests for core.v2.vector_store — pluggable vector store factory."""

from unittest.mock import MagicMock, patch

import pytest

from core.v2.errors import VectorStoreError
from core.v2.vector_store import create_vector_store


class TestCreateVectorStore:
    """create_vector_store creates the correct backend."""

    def test_faiss_default(self) -> None:
        store = create_vector_store("faiss", embed_dim=384)
        # Should return a FaissVectorStore wrapping IndexFlatL2
        from llama_index.vector_stores.faiss import FaissVectorStore

        assert isinstance(store, FaissVectorStore)

    def test_faiss_respects_dimension(self) -> None:
        store = create_vector_store("faiss", embed_dim=768)
        from llama_index.vector_stores.faiss import FaissVectorStore

        assert isinstance(store, FaissVectorStore)
        # The underlying FAISS index should have the right dimension
        assert store._faiss_index.d == 768

    def test_default_args(self) -> None:
        store = create_vector_store()
        from llama_index.vector_stores.faiss import FaissVectorStore

        assert isinstance(store, FaissVectorStore)
        assert store._faiss_index.d == 384

    def test_unknown_type_raises(self) -> None:
        with pytest.raises(VectorStoreError, match="Unknown vector store type"):
            create_vector_store("unknown_backend")

    def test_error_message_lists_supported(self) -> None:
        with pytest.raises(VectorStoreError, match="Supported types: faiss"):
            create_vector_store("chroma")

    def test_import_error_raises_vector_store_error(self) -> None:
        with patch.dict("sys.modules", {"faiss": None}):
            with pytest.raises(VectorStoreError, match="faiss-cpu"):
                create_vector_store("faiss")
