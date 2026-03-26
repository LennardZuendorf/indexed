"""Tests for core.v2.errors — exception hierarchy."""

import pytest
from indexed_config.errors import IndexedError

from core.v2.errors import (
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
        [CoreV2Error, CollectionNotFoundError, IngestionError, EmbeddingError, VectorStoreError],
    )
    def test_inherits_from_indexed_error(self, exc_class: type) -> None:
        assert issubclass(exc_class, IndexedError)

    @pytest.mark.parametrize(
        "exc_class",
        [CollectionNotFoundError, IngestionError, EmbeddingError, VectorStoreError],
    )
    def test_inherits_from_core_v2_error(self, exc_class: type) -> None:
        assert issubclass(exc_class, CoreV2Error)


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
