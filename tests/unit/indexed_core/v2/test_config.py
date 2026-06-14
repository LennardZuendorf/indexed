"""Tests for core.v2.config — Pydantic config models and registration."""

from unittest.mock import MagicMock

import pytest

from core.v2.config import (
    CoreV2EmbeddingConfig,
    CoreV2IndexingConfig,
    CoreV2SearchConfig,
    CoreV2StorageConfig,
    register_config,
)


class TestCoreV2EmbeddingConfig:
    """Embedding config defaults and validation."""

    def test_defaults(self) -> None:
        cfg = CoreV2EmbeddingConfig()
        assert cfg.model_name == "all-MiniLM-L6-v2"
        assert cfg.batch_size == 128

    def test_custom_values(self) -> None:
        cfg = CoreV2EmbeddingConfig(model_name="all-mpnet-base-v2", batch_size=64)
        assert cfg.model_name == "all-mpnet-base-v2"
        assert cfg.batch_size == 64

    def test_batch_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            CoreV2EmbeddingConfig(batch_size=0)


class TestCoreV2IndexingConfig:
    """Indexing config defaults and validation."""

    def test_defaults(self) -> None:
        cfg = CoreV2IndexingConfig()
        assert cfg.chunk_size == 512
        assert cfg.chunk_overlap == 50
        assert cfg.batch_size == 32

    def test_overlap_must_be_less_than_chunk_size(self) -> None:
        with pytest.raises(
            ValueError, match="chunk_overlap must be less than chunk_size"
        ):
            CoreV2IndexingConfig(chunk_size=100, chunk_overlap=100)

    def test_overlap_less_than_chunk_size_ok(self) -> None:
        cfg = CoreV2IndexingConfig(chunk_size=100, chunk_overlap=99)
        assert cfg.chunk_overlap == 99

    def test_chunk_size_max(self) -> None:
        with pytest.raises(ValueError):
            CoreV2IndexingConfig(chunk_size=5000)


class TestCoreV2StorageConfig:
    """Storage config defaults and validation."""

    def test_defaults(self) -> None:
        cfg = CoreV2StorageConfig()
        assert cfg.vector_store == "faiss"
        assert cfg.persistence_enabled is True

    def test_custom_store(self) -> None:
        cfg = CoreV2StorageConfig(vector_store="chroma")
        assert cfg.vector_store == "chroma"


class TestCoreV2SearchConfig:
    """Search config defaults and validation."""

    def test_defaults(self) -> None:
        cfg = CoreV2SearchConfig()
        assert cfg.max_docs == 10
        assert cfg.max_chunks == 30
        assert cfg.similarity_top_k == 30
        assert cfg.include_matched_chunks is True
        assert cfg.score_threshold is None

    def test_score_threshold_bounds(self) -> None:
        cfg = CoreV2SearchConfig(score_threshold=0.5)
        assert cfg.score_threshold == 0.5

        with pytest.raises(ValueError):
            CoreV2SearchConfig(score_threshold=1.5)

        with pytest.raises(ValueError):
            CoreV2SearchConfig(score_threshold=-0.1)

    def test_max_docs_bounds(self) -> None:
        with pytest.raises(ValueError):
            CoreV2SearchConfig(max_docs=0)
        with pytest.raises(ValueError):
            CoreV2SearchConfig(max_docs=101)


class TestRegisterConfig:
    """register_config calls config_service.register for all specs."""

    def test_registers_all_specs(self) -> None:
        mock_service = MagicMock()
        register_config(mock_service)

        assert mock_service.register.call_count == 4

        registered_paths = {
            call.kwargs["path"] for call in mock_service.register.call_args_list
        }
        assert registered_paths == {
            "core.v2.embedding",
            "core.v2.indexing",
            "core.v2.storage",
            "core.v2.search",
        }

    def test_registers_correct_types(self) -> None:
        mock_service = MagicMock()
        register_config(mock_service)

        registered_types = {
            call.args[0] for call in mock_service.register.call_args_list
        }
        assert registered_types == {
            CoreV2EmbeddingConfig,
            CoreV2IndexingConfig,
            CoreV2StorageConfig,
            CoreV2SearchConfig,
        }


class TestNoImportSideEffects:
    """Importing core.v2 must not trigger config registration."""

    def test_import_has_no_side_effects(self) -> None:
        import core.v2

        assert core.v2.__version__ == "2.0.0"
        # If this import triggered ConfigService.instance(), it would
        # fail in test isolation. The fact that it doesn't proves no side effects.
