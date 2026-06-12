"""Tests for core.v2.errors — exception hierarchy."""

import pytest
from indexed_config.errors import IndexedError

from core.v2.errors import (
    CollectionEngineMismatchError,
    CollectionNotFoundError,
    CoreV2Error,
    EmbeddingError,
    IngestionError,
    VectorStoreError,
)


class TestErrorHierarchy:
    """All v2 errors must inherit from IndexedError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            CoreV2Error,
            CollectionNotFoundError,
            IngestionError,
            EmbeddingError,
            VectorStoreError,
            CollectionEngineMismatchError,
        ],
    )
    def test_inherits_from_indexed_error(self, exc_class: type) -> None:
        assert issubclass(exc_class, IndexedError)

    @pytest.mark.parametrize(
        "exc_class",
        [CollectionNotFoundError, IngestionError, EmbeddingError, VectorStoreError],
    )
    def test_inherits_from_core_v2_error(self, exc_class: type) -> None:
        assert issubclass(exc_class, CoreV2Error)

    def test_mismatch_error_is_a_vector_store_error(self) -> None:
        # Must stay a VectorStoreError subclass so existing `except IndexedError`
        # / `except VectorStoreError` handlers keep catching it unchanged.
        assert issubclass(CollectionEngineMismatchError, VectorStoreError)


class TestCollectionEngineMismatchError:
    """Actionable message for a forced engine against the wrong store."""

    def test_v1_detected_message_is_actionable(self) -> None:
        err = CollectionEngineMismatchError("my-docs", "v1")
        assert err.name == "my-docs"
        assert err.detected_engine == "v1"
        text = str(err)
        assert "v1 collection" in text
        assert "--engine v1" in text
        # No leaked LlamaIndex / FAISS internals.
        assert "llama_index" not in text
        assert "vector_store" not in text

    def test_unknown_engine_message_is_generic(self) -> None:
        err = CollectionEngineMismatchError("my-docs", None)
        assert "not a usable v2 store" in str(err)

    def test_catchable_as_indexed_error(self) -> None:
        with pytest.raises(IndexedError):
            raise CollectionEngineMismatchError("test", "v1")


class TestCollectionNotFoundError:
    """CollectionNotFoundError stores the collection name."""

    def test_stores_name(self) -> None:
        err = CollectionNotFoundError("my-docs")
        assert err.name == "my-docs"

    def test_message_includes_name(self) -> None:
        err = CollectionNotFoundError("my-docs")
        assert "my-docs" in str(err)

    def test_catchable_as_indexed_error(self) -> None:
        with pytest.raises(IndexedError):
            raise CollectionNotFoundError("test")


class TestCoreV2Error:
    """CoreV2Error can be raised with a message."""

    def test_basic_message(self) -> None:
        err = CoreV2Error("something went wrong")
        assert str(err) == "something went wrong"
