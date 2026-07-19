"""Unit tests for core-v2/1 error types (``indexed.core.errors``)."""

from __future__ import annotations


def test_engine_mismatch_error_is_indexed_error() -> None:
    from indexed.config.errors import IndexedError
    from indexed.core.errors import CoreError, EngineMismatchError

    assert issubclass(EngineMismatchError, CoreError)
    assert issubclass(EngineMismatchError, IndexedError)


def test_engine_mismatch_message_names_engine_and_remedy() -> None:
    from indexed.core.errors import EngineMismatchError

    err = EngineMismatchError("my-docs", found="1", requested="2")

    message = str(err)
    # Documented remedy pattern (tech.md §Errors), generalized for found/requested.
    assert "my-docs" in message
    assert "v1 collection" in message
    assert "--engine v1" in message
    assert "indexed index migrate my-docs" in message


def test_engine_not_available_error_is_indexed_error() -> None:
    from indexed.config.errors import IndexedError
    from indexed.core.errors import CoreError, EngineNotAvailableError

    assert issubclass(EngineNotAvailableError, CoreError)
    assert issubclass(EngineNotAvailableError, IndexedError)


def test_engine_not_available_message_is_actionable() -> None:
    from indexed.core.errors import EngineNotAvailableError

    err = EngineNotAvailableError("2")
    message = str(err)
    assert "v2" in message
    assert "not yet available" in message
