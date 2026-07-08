"""Tests for collection service."""

from unittest.mock import Mock, patch

import pytest

from indexed_config.errors import ConfigurationError

from core.v1.engine.services.collection_service import (
    _resolve_connector,
    _create_one,
    _collection_exists,
    collection_exists,
)
from core.v1.engine.services.models import SourceConfig


def _source_config(name: str = "test-collection") -> SourceConfig:
    return SourceConfig(
        name=name,
        type="localFiles",
        base_url_or_path="./docs",
        query=None,
        indexer="test-indexer",
        reader_opts={},
    )


class TestResolveConnector:
    """Test connector resolution via injected factory."""

    def test_raises_when_factory_not_injected(self):
        with pytest.raises(
            ConfigurationError, match="connector_factory must be injected"
        ):
            _resolve_connector(_source_config())

    def test_delegates_to_injected_factory(self):
        source_config = _source_config()
        mock_connector = Mock()
        factory = Mock(return_value=mock_connector)

        connector = _resolve_connector(source_config, connector_factory=factory)

        factory.assert_called_once_with(source_config)
        assert connector is mock_connector


class TestCreateOneWithInjectedFactory:
    """Test _create_one builds via the injected connector factory."""

    def test_create_one_uses_injected_factory(self):
        cfg = _source_config("test-col")
        mock_connector = Mock()
        mock_connector.reader = Mock()
        mock_connector.converter = Mock()

        with patch(
            "core.v1.engine.services.collection_service.create_collection_creator"
        ) as mock_creator_factory:
            mock_creator = Mock()
            mock_creator_factory.return_value = mock_creator

            _create_one(
                cfg,
                use_cache=False,
                connector_factory=lambda _cfg: mock_connector,
            )

            mock_creator_factory.assert_called_once()
            call_kwargs = mock_creator_factory.call_args.kwargs
            assert call_kwargs["document_reader"] is mock_connector.reader
            assert call_kwargs["document_converter"] is mock_connector.converter
            mock_creator.run.assert_called_once()


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

        cfg = _source_config("test-col")
        factory = Mock()

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
                    create([cfg], force=True, connector_factory=factory)

                    mock_clear.assert_called_once()
                    mock_create.assert_called_once()
                    assert mock_create.call_args.kwargs["connector_factory"] is factory

    def test_create_with_force_and_existing_collection(self):
        from core.v1.engine.services.collection_service import create

        cfg = _source_config("test-col")

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
                        create([cfg], force=True, connector_factory=Mock())

                        mock_clear_col.assert_called_once()


class TestUpdateFunction:
    """Test update function delegates to the collection updater."""

    def test_update_delegates_to_updater(self):
        from core.v1.engine.services.collection_service import update

        cfg = _source_config("test-col")
        factory = Mock()

        with patch(
            "core.v1.engine.factories.update_collection_factory.create_collection_updater"
        ) as mock_factory:
            mock_updater = Mock()
            mock_factory.return_value = mock_updater

            update([cfg], manifest_factory=factory)

            mock_factory.assert_called_once()
            assert mock_factory.call_args.kwargs["manifest_factory"] is factory
            mock_updater.run.assert_called_once()


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

    def test_public_collection_exists_delegates_to_private_helper(self):
        """The public ``collection_exists`` wrapper (used by CLI commands to
        detect a present-but-corrupt collection) must delegate to the same
        on-disk check as ``_collection_exists``."""
        with patch(
            "core.v1.engine.services.collection_service.DiskPersister"
        ) as mock_persister_class:
            mock_persister = Mock()
            mock_persister.is_path_exists.return_value = True
            mock_persister_class.return_value = mock_persister

            result = collection_exists("corrupt-coll", collections_path="/tmp/x")

            assert result is True
            mock_persister.is_path_exists.assert_called_once_with("corrupt-coll")
