"""Tests for collection service."""

from unittest.mock import Mock, patch, MagicMock

import pytest

from indexed_config.errors import ConfigurationError

from core.v1.engine.services.collection_service import (
    _build_connector_from_config,
    _collection_exists,
)
from core.v1.engine.services.models import SourceConfig


class TestBuildConnectorFromConfig:
    """Test _build_connector_from_config delegates to injected factory."""

    def test_raises_when_factory_not_injected(self):
        config_service = MagicMock()
        source_config = SourceConfig(
            name="test-collection",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={},
        )

        with pytest.raises(
            ConfigurationError, match="connector_factory must be injected"
        ):
            _build_connector_from_config(source_config, config_service)

    def test_delegates_to_injected_factory(self):
        config_service = MagicMock()
        source_config = SourceConfig(
            name="test-collection",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={},
        )
        mock_connector = Mock()
        factory = Mock(return_value=mock_connector)

        connector = _build_connector_from_config(
            source_config, config_service, connector_factory=factory
        )

        factory.assert_called_once_with(source_config)
        assert connector is mock_connector


class TestClearCaches:
    """Test _clear_caches function."""

    def test_clear_caches_removes_entries(self, tmp_path):
        from core.v1.engine.services.collection_service import _clear_caches

        (tmp_path / "cache1").mkdir()
        (tmp_path / "cache1" / "data.json").write_text("{}")
        (tmp_path / "cache2_completed").write_text("")

        _clear_caches(str(tmp_path))

        assert not (tmp_path / "cache1").exists()
        assert not (tmp_path / "cache2_completed").exists()

    def test_clear_caches_nonexistent_dir(self):
        from core.v1.engine.services.collection_service import _clear_caches

        _clear_caches("/nonexistent/path/12345")


class TestClearCollections:
    """Test clear function."""

    def test_clear_removes_collection(self):
        from core.v1.engine.services.collection_service import clear

        with patch(
            "core.v1.engine.services.collection_service.DiskPersister"
        ) as mock_cls:
            mock_persister = Mock()
            mock_cls.return_value = mock_persister

            clear(["col1", "col2"], collections_path="/tmp/test")

            assert mock_persister.remove_folder.call_count == 2
            mock_persister.remove_folder.assert_any_call("col1")
            mock_persister.remove_folder.assert_any_call("col2")


class TestCreateFunction:
    """Test create function."""

    def test_create_with_force_clears_caches(self):
        from core.v1.engine.services.collection_service import create

        cfg = SourceConfig(
            name="test-col",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={},
        )

        with patch(
            "core.v1.engine.services.collection_service._clear_caches"
        ) as mock_clear:
            with patch(
                "core.v1.engine.services.collection_service._collection_exists",
                return_value=False,
            ):
                with patch(
                    "core.v1.engine.services.collection_service._create_one"
                ) as mock_create:
                    create(
                        [cfg],
                        config_service=MagicMock(),
                        force=True,
                    )

                    mock_clear.assert_called_once()
                    mock_create.assert_called_once()

    def test_create_with_force_and_existing_collection(self):
        from core.v1.engine.services.collection_service import create

        cfg = SourceConfig(
            name="test-col",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={},
        )

        with patch("core.v1.engine.services.collection_service._clear_caches"):
            with patch(
                "core.v1.engine.services.collection_service._collection_exists",
                return_value=True,
            ):
                with patch(
                    "core.v1.engine.services.collection_service.clear"
                ) as mock_clear_col:
                    with patch(
                        "core.v1.engine.services.collection_service._create_one"
                    ):
                        create(
                            [cfg],
                            config_service=MagicMock(),
                            force=True,
                        )

                        mock_clear_col.assert_called_once()

    def test_create_initializes_config_service_when_none(self):
        from core.v1.engine.services.collection_service import create

        cfg = SourceConfig(
            name="test-col",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={},
        )

        with patch("core.v1.engine.services.collection_service._create_one"):
            with patch("indexed_config.ConfigService") as mock_cs:
                mock_cs.return_value = MagicMock()
                create([cfg], config_service=None, force=False)
                mock_cs.assert_called_once()


class TestCollectionExists:
    """Test _collection_exists function."""

    def test_collection_exists_true(self):
        """Test collection exists returns True when collection folder exists."""
        with patch(
            "core.v1.engine.services.collection_service.DiskPersister"
        ) as mock_persister_class:
            mock_persister = Mock()
            mock_persister.is_path_exists.return_value = True
            mock_persister_class.return_value = mock_persister

            result = _collection_exists("test-collection")

            assert result is True
            mock_persister.is_path_exists.assert_called_once_with("test-collection")

    def test_collection_exists_false(self):
        """Test collection exists returns False when collection folder does not exist."""
        with patch(
            "core.v1.engine.services.collection_service.DiskPersister"
        ) as mock_persister_class:
            mock_persister = Mock()
            mock_persister.is_path_exists.return_value = False
            mock_persister_class.return_value = mock_persister

            result = _collection_exists("non-existent")

            assert result is False
            mock_persister.is_path_exists.assert_called_once_with("non-existent")
