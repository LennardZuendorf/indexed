"""Tests for collection service."""
import os
import pytest
from unittest.mock import Mock, patch

from core.v1.engine.services.collection_service import (
    _build_reader_converter,
    _collection_exists,
)
from core.v1.engine.services.models import SourceConfig


class TestBuildReaderConverter:
    """Test _build_reader_converter function."""

    @patch.dict(os.environ, {
        "CONF_TOKEN": "test-token",
        "CONF_LOGIN": "test-user",
        "CONF_PASSWORD": "test-pass"
    })
    def test_build_confluence_reader_converter(self):
        """Test building Confluence reader and converter."""
        config = SourceConfig(
            name="test-collection",
            type="confluence",
            base_url_or_path="https://confluence.example.com",
            query="space = TEST",
            indexer="test-indexer",
            reader_opts={
                "readOnlyFirstLevelComments": True,
                "username": "user",
                "password": "pass",
            },
        )

        with (
            patch(
                "core.v1.engine.services.collection_service.ConfluenceDocumentReader"
            ) as mock_reader,
            patch(
                "core.v1.engine.services.collection_service.ConfluenceDocumentConverter"
            ) as mock_converter,
        ):
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_url="https://confluence.example.com",
                query="space = TEST",
                token="test-token",
                username="user",
                password="pass",
                read_all_comments=False,
            )
            mock_converter.assert_called_once()
            assert reader == mock_reader.return_value
            assert converter == mock_converter.return_value

    @patch.dict(os.environ, {
        "ATLASSIAN_EMAIL": "test@example.com",
        "ATLASSIAN_TOKEN": "test-token"
    })
    def test_build_confluence_cloud_reader_converter(self):
        """Test building Confluence Cloud reader and converter."""
        config = SourceConfig(
            name="test-collection",
            type="confluenceCloud", 
            base_url_or_path="https://acme.atlassian.net",
            query="space = ENG",
            indexer="test-indexer",
            reader_opts={
                "readOnlyFirstLevelComments": True,
                "email": "user@example.com",
                "api_token": "token",
            },
        )

        with patch(
            "core.v1.engine.services.collection_service.ConfluenceCloudDocumentReader"
        ) as mock_reader:
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_url="https://acme.atlassian.net",
                query="space = ENG",
                email="user@example.com",
                api_token="token",
                read_all_comments=False,
            )

    @patch.dict(os.environ, {
        "JIRA_TOKEN": "test-token",
        "JIRA_LOGIN": "test-user",
        "JIRA_PASSWORD": "test-pass"
    })
    def test_build_jira_reader_converter(self):
        """Test building Jira reader and converter."""
        config = SourceConfig(
            name="test-collection",
            type="jira",
            base_url_or_path="https://jira.example.com",
            query="project = TEST",
            indexer="test-indexer",
            reader_opts={
                "username": "user",
                "password": "pass",
            },
        )

        with patch(
            "core.v1.engine.services.collection_service.JiraDocumentReader"
        ) as mock_reader:
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_url="https://jira.example.com",
                query="project = TEST",
                token="test-token",
                username="user",
                password="pass",
            )

    @patch.dict(os.environ, {
        "ATLASSIAN_EMAIL": "test@example.com",
        "ATLASSIAN_TOKEN": "test-token"
    })
    def test_build_jira_cloud_reader_converter(self):
        """Test building Jira Cloud reader and converter."""
        config = SourceConfig(
            name="test-collection",
            type="jiraCloud",
            base_url_or_path="https://acme.atlassian.net",
            query="project = TEST",
            indexer="test-indexer",
            reader_opts={
                "email": "user@example.com",
                "api_token": "token",
            },
        )

        with patch(
            "core.v1.engine.services.collection_service.JiraCloudDocumentReader"
        ) as mock_reader:
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_url="https://acme.atlassian.net",
                query="project = TEST",
                email="user@example.com",
                api_token="token",
            )

            mock_reader.assert_called_once_with(
                base_url="https://acme.atlassian.net",
                query="project = TEST",
                email="user@example.com",
                api_token="token",
            )

    def test_build_files_reader_converter(self):
        """Test building Files reader and converter."""
        config = SourceConfig(
            name="test-collection",
            type="localFiles",
            base_url_or_path="./docs",
            query=None,
            indexer="test-indexer",
            reader_opts={
                "includePatterns": ["*.md"],
                "excludePatterns": ["*.tmp"],
                "failFast": True,
            },
        )

        with patch(
            "core.v1.engine.services.collection_service.FilesDocumentReader"
        ) as mock_reader:
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_path="./docs",
                include_patterns=["*.md"],
                exclude_patterns=["*.tmp"],
                fail_fast=True,
            )

    def test_build_unknown_reader_converter(self):
        """Test building reader for unknown source type raises Pydantic validation error."""
        with pytest.raises(ValueError, match="Input should be"):
            SourceConfig(
                name="test-collection",
                type="unknown",
                base_url_or_path="",
                query=None,
                indexer="test-indexer",
            )


class TestCollectionExists:
    """Test _collection_exists function."""

    @patch("core.v1.engine.services.collection_service.DiskPersister")
    def test_collection_exists_true(self, mock_persister_class):
        """Test when collection exists."""
        mock_persister = Mock()
        mock_persister.is_path_exists.return_value = True
        mock_persister_class.return_value = mock_persister

        result = _collection_exists("test-collection")

        assert result is True
        mock_persister_class.assert_called_once_with(base_path="./data/collections")
        mock_persister.is_path_exists.assert_called_once_with("test-collection")

    @patch("core.v1.engine.services.collection_service.DiskPersister")
    def test_collection_exists_false(self, mock_persister_class):
        """Test when collection does not exist."""
        mock_persister = Mock()
        mock_persister.is_path_exists.return_value = False
        mock_persister_class.return_value = mock_persister

        result = _collection_exists("test-collection")

        assert result is False
        mock_persister.is_path_exists.assert_called_once_with("test-collection")