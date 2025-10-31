"""Tests for collection service."""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock

from core.v1.engine.services.collection_service import (
    _build_connector_from_config,
    _collection_exists,
)
from core.v1.engine.services.models import SourceConfig


class TestBuildConnectorFromConfig:
    """Test _build_connector_from_config function with new config system."""

    @patch.dict(os.environ, {
        "CONF_TOKEN": "test-token",
    })
    def test_build_confluence_connector(self):
        """Test building Confluence connector."""
        config_service = MagicMock()
        
        source_config = SourceConfig(
            name="test-collection",
            type="confluence",
            base_url_or_path="https://confluence.example.com",
            query="space = TEST",
            indexer="test-indexer",
            reader_opts={
                "readAllComments": True,
            },
        )

        with patch(
            "core.v1.engine.services.collection_service.ConfluenceConnector"
        ) as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector
            
            connector = _build_connector_from_config(source_config, config_service)

            # Verify connector was created via from_config
            mock_connector_class.from_config.assert_called_once_with(config_service)
            assert connector == mock_connector

    @patch.dict(os.environ, {
        "ATLASSIAN_EMAIL": "test@example.com",
        "ATLASSIAN_TOKEN": "test-token"
    })
    def test_build_confluence_cloud_connector(self):
        """Test building Confluence Cloud connector."""
        config_service = MagicMock()
        
        source_config = SourceConfig(
            name="test-collection",
            type="confluenceCloud",
            base_url_or_path="https://example.atlassian.net",
            query="space = TEST",
            indexer="test-indexer",
            reader_opts={
                "readAllComments": False,
            },
        )

        with patch(
            "core.v1.engine.services.collection_service.ConfluenceCloudConnector"
        ) as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector
            
            connector = _build_connector_from_config(source_config, config_service)

            # Verify connector was created via from_config
            mock_connector_class.from_config.assert_called_once_with(config_service)
            assert connector == mock_connector

    @patch.dict(os.environ, {
        "JIRA_TOKEN": "test-token"
    })
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

        with patch(
            "core.v1.engine.services.collection_service.JiraConnector"
        ) as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector
            
            connector = _build_connector_from_config(source_config, config_service)

            # Verify connector was created via from_config
            mock_connector_class.from_config.assert_called_once_with(config_service)
            assert connector == mock_connector

    @patch.dict(os.environ, {
        "ATLASSIAN_EMAIL": "test@example.com",
        "ATLASSIAN_TOKEN": "test-token"
    })
    def test_build_jira_cloud_connector(self):
        """Test building Jira Cloud connector."""
        config_service = MagicMock()
        
        source_config = SourceConfig(
            name="test-collection",
            type="jiraCloud",
            base_url_or_path="https://example.atlassian.net",
            query="project = TEST",
            indexer="test-indexer",
            reader_opts={},
        )

        with patch(
            "core.v1.engine.services.collection_service.JiraCloudConnector"
        ) as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector
            
            connector = _build_connector_from_config(source_config, config_service)

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

        with patch(
            "core.v1.engine.services.collection_service.FileSystemConnector"
        ) as mock_connector_class:
            mock_connector = Mock()
            mock_connector_class.from_config.return_value = mock_connector
            
            connector = _build_connector_from_config(source_config, config_service)

            # Verify connector was created via from_config
            mock_connector_class.from_config.assert_called_once_with(config_service)
            assert connector == mock_connector


class TestCollectionExists:
    """Test _collection_exists function."""

    def test_collection_exists_true(self):
        """Test collection exists returns True when collection folder exists."""
        with patch("core.v1.engine.services.collection_service.DiskPersister") as mock_persister_class:
            mock_persister = Mock()
            mock_persister.is_path_exists.return_value = True
            mock_persister_class.return_value = mock_persister

            result = _collection_exists("test-collection")

            assert result is True
            mock_persister.is_path_exists.assert_called_once_with("test-collection")

    def test_collection_exists_false(self):
        """Test collection exists returns False when collection folder does not exist."""
        with patch("core.v1.engine.services.collection_service.DiskPersister") as mock_persister_class:
            mock_persister = Mock()
            mock_persister.is_path_exists.return_value = False
            mock_persister_class.return_value = mock_persister

            result = _collection_exists("non-existent")

            assert result is False
            mock_persister.is_path_exists.assert_called_once_with("non-existent")
