"""Tests for collection service."""

import os
from unittest.mock import Mock, patch, MagicMock

from core.v1.engine.services.collection_service import (
    _build_connector_from_config,
    _collection_exists,
)
from core.v1.engine.services.models import SourceConfig


class TestBuildConnectorFromConfig:
    """Test _build_connector_from_config function with new config system.

    The function now uses a registry-based pattern:
    1. Sets config values via config_service.set()
    2. Calls ConnectorClass.from_config(config_service) which internally
       registers specs, binds, and creates the connector

    Note: Both Cloud and non-Cloud variants use unified namespaces
    (sources.jira for all Jira, sources.confluence for all Confluence).
    """

    @patch.dict(os.environ, {"CONF_TOKEN": "test-token"})
    def test_build_confluence_connector(self):
        """Test building Confluence connector."""
        config_service = MagicMock()

        source_config = SourceConfig(
            name="test-collection",
            type="confluence",
            base_url_or_path="https://confluence.example.com",
            query="space = TEST",
            indexer="test-indexer",
            reader_opts={"readAllComments": True},
        )

        with patch("connectors.confluence.ConfluenceConnector") as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector

            connector = _build_connector_from_config(source_config, config_service)

            # Verify config values were set (unified namespace)
            config_service.set.assert_any_call(
                "sources.confluence.url", "https://confluence.example.com"
            )
            config_service.set.assert_any_call(
                "sources.confluence.query", "space = TEST"
            )

            # Verify connector was created via from_config
            mock_connector_class.from_config.assert_called_once_with(config_service)
            assert connector == mock_connector

    @patch.dict(
        os.environ,
        {"ATLASSIAN_EMAIL": "test@example.com", "ATLASSIAN_TOKEN": "test-token"},
    )
    def test_build_confluence_cloud_type_connector(self):
        """Test building Confluence Cloud connector (confluenceCloud type)."""
        config_service = MagicMock()

        source_config = SourceConfig(
            name="test-collection",
            type="confluenceCloud",
            base_url_or_path="https://example.atlassian.net",
            query="space = TEST",
            indexer="test-indexer",
            reader_opts={"readAllComments": False},
        )

        with patch(
            "connectors.confluence.ConfluenceCloudConnector"
        ) as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector

            connector = _build_connector_from_config(source_config, config_service)

            # Verify config values were set (uses unified sources.confluence namespace)
            config_service.set.assert_any_call(
                "sources.confluence.url", "https://example.atlassian.net"
            )
            config_service.set.assert_any_call(
                "sources.confluence.query", "space = TEST"
            )

            # Verify connector was created via from_config
            mock_connector_class.from_config.assert_called_once_with(config_service)
            assert connector == mock_connector

    @patch.dict(os.environ, {"JIRA_TOKEN": "test-token"})
    def test_build_jira_connector(self):
        """Test building Jira connector."""
        config_service = MagicMock()

        source_config = SourceConfig(
            name="test-collection",
            type="jira",
            base_url_or_path="https://jira.example.com",
            query="project = TEST",
            indexer="test-indexer",
            reader_opts={},
        )

        with patch("connectors.jira.JiraConnector") as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector

            connector = _build_connector_from_config(source_config, config_service)

            # Verify config values were set
            config_service.set.assert_any_call(
                "sources.jira.url", "https://jira.example.com"
            )
            config_service.set.assert_any_call("sources.jira.query", "project = TEST")

            # Verify connector was created via from_config
            mock_connector_class.from_config.assert_called_once_with(config_service)
            assert connector == mock_connector

    @patch.dict(
        os.environ,
        {"ATLASSIAN_EMAIL": "test@example.com", "ATLASSIAN_TOKEN": "test-token"},
    )
    def test_build_jira_cloud_type_connector(self):
        """Test building Jira Cloud connector (jiraCloud type)."""
        config_service = MagicMock()

        source_config = SourceConfig(
            name="test-collection",
            type="jiraCloud",
            base_url_or_path="https://example.atlassian.net",
            query="project = TEST",
            indexer="test-indexer",
            reader_opts={},
        )

        with patch("connectors.jira.JiraCloudConnector") as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector

            connector = _build_connector_from_config(source_config, config_service)

            # Verify config values were set (uses unified sources.jira namespace)
            config_service.set.assert_any_call(
                "sources.jira.url", "https://example.atlassian.net"
            )
            config_service.set.assert_any_call("sources.jira.query", "project = TEST")

            # Verify connector was created via from_config
            mock_connector_class.from_config.assert_called_once_with(config_service)
            assert connector == mock_connector

    def test_build_files_connector(self):
        """Test building files connector."""
        config_service = MagicMock()

        source_config = SourceConfig(
            name="test-collection",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={
                "includePatterns": [r".*\.md$"],
                "excludePatterns": [r".*\.tmp$"],
                "failFast": True,
            },
        )

        with patch("connectors.files.FileSystemConnector") as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector

            connector = _build_connector_from_config(source_config, config_service)

            # Verify config values were set
            config_service.set.assert_any_call("sources.files.path", "./docs")

            # Verify connector was created via from_config
            mock_connector_class.from_config.assert_called_once_with(config_service)
            assert connector == mock_connector


class TestBuildLocalFilesConnectorOpts:
    """Test _build_connector_from_config with localFiles reader_opts."""

    def test_files_connector_with_include_patterns(self):
        config_service = MagicMock()
        source_config = SourceConfig(
            name="test-col",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={"includePatterns": [r".*\.md$"]},
        )

        with patch("connectors.files.FileSystemConnector") as mock_cls:
            mock_cls.from_config.return_value = Mock()
            _build_connector_from_config(source_config, config_service)

            config_service.set.assert_any_call(
                "sources.files.include_patterns", [r".*\.md$"]
            )

    def test_files_connector_with_exclude_patterns(self):
        config_service = MagicMock()
        source_config = SourceConfig(
            name="test-col",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={"excludePatterns": [r".*\.tmp$"]},
        )

        with patch("connectors.files.FileSystemConnector") as mock_cls:
            mock_cls.from_config.return_value = Mock()
            _build_connector_from_config(source_config, config_service)

            config_service.set.assert_any_call(
                "sources.files.exclude_patterns", [r".*\.tmp$"]
            )

    def test_files_connector_with_fail_fast(self):
        config_service = MagicMock()
        source_config = SourceConfig(
            name="test-col",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={"failFast": True},
        )

        with patch("connectors.files.FileSystemConnector") as mock_cls:
            mock_cls.from_config.return_value = Mock()
            _build_connector_from_config(source_config, config_service)

            config_service.set.assert_any_call("sources.files.fail_fast", True)


class TestUnknownSourceType:
    """Test unknown source type handling."""

    def test_raises_for_unknown_type(self):
        import pytest

        config_service = MagicMock()
        # Create a valid SourceConfig then patch the type to an invalid value
        source_config = Mock()
        source_config.type = "unknownSource"
        source_config.base_url_or_path = "http://example.com"
        source_config.query = None
        source_config.reader_opts = {}

        with pytest.raises(ValueError, match="Unknown source type"):
            _build_connector_from_config(source_config, config_service)


class TestClearCaches:
    """Test _clear_caches function."""

    def test_clear_caches_removes_entries(self, tmp_path):
        from core.v1.engine.services.collection_service import _clear_caches

        # Create some cache entries
        (tmp_path / "cache1").mkdir()
        (tmp_path / "cache1" / "data.json").write_text("{}")
        (tmp_path / "cache2_completed").write_text("")

        _clear_caches(str(tmp_path))

        assert not (tmp_path / "cache1").exists()
        assert not (tmp_path / "cache2_completed").exists()

    def test_clear_caches_nonexistent_dir(self):
        from core.v1.engine.services.collection_service import _clear_caches

        # Should not raise
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

        with patch(
            "core.v1.engine.services.collection_service._clear_caches"
        ):
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

        with patch(
            "core.v1.engine.services.collection_service._create_one"
        ):
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
