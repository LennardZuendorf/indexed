"""Tests for collection_service."""

import os
import pytest
from unittest.mock import Mock, patch

from core.v1.engine.services.collection_service import (
    create,
    update,
    clear,
    _build_reader_converter,
    _collection_exists,
    _create_one,
    _update_one,
)
from core.v1.engine.services.models import SourceConfig


class TestBuildReaderConverter:
    """Test _build_reader_converter function."""

    @patch.dict(os.environ, {"CONF_TOKEN": "test-token"})
    def test_confluence_server_with_token(self):
        """Test building Confluence Server reader with token."""
        config = SourceConfig(
            name="test-confluence",
            type="confluence",
            base_url_or_path="https://confluence.example.com",
            query="space = TEST",
            indexer="test-indexer",
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
                login=None,
                password=None,
                read_all_comments=True,
            )
            mock_converter.assert_called_once()

    @patch.dict(os.environ, {"CONF_LOGIN": "user", "CONF_PASSWORD": "pass"}, clear=True)
    def test_confluence_server_with_login_password(self):
        """Test building Confluence Server reader with login/password."""
        config = SourceConfig(
            name="test-confluence",
            type="confluence",
            base_url_or_path="https://confluence.example.com",
            query="space = TEST",
            indexer="test-indexer",
        )

        with patch(
            "core.v1.engine.services.collection_service.ConfluenceDocumentReader"
        ) as mock_reader:
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_url="https://confluence.example.com",
                query="space = TEST",
                token=None,
                login="user",
                password="pass",
                read_all_comments=True,
            )

    def test_confluence_server_missing_credentials(self):
        """Test error when Confluence Server credentials are missing."""
        config = SourceConfig(
            name="test-confluence",
            type="confluence",
            base_url_or_path="https://confluence.example.com",
            query="space = TEST",
            indexer="test-indexer",
        )

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(
                ValueError, match="Either 'token'.*or both 'login'.*and 'password'"
            ):
                _build_reader_converter(config)

    @patch.dict(
        os.environ,
        {"ATLASSIAN_EMAIL": "user@example.com", "ATLASSIAN_TOKEN": "token123"},
    )
    def test_confluence_cloud(self):
        """Test building Confluence Cloud reader."""
        config = SourceConfig(
            name="test-confluence-cloud",
            type="confluenceCloud",
            base_url_or_path="https://company.atlassian.net",
            query="space = DOC",
            indexer="test-indexer",
            reader_opts={"readOnlyFirstLevelComments": True},
        )

        with patch(
            "core.v1.engine.services.collection_service.ConfluenceCloudDocumentReader"
        ) as mock_reader:
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_url="https://company.atlassian.net",
                query="space = DOC",
                email="user@example.com",
                api_token="token123",
                read_all_comments=False,  # readOnlyFirstLevelComments=True means read_all_comments=False
            )

    @patch.dict(os.environ, {"JIRA_TOKEN": "jira-token"})
    def test_jira_server(self):
        """Test building Jira Server reader."""
        config = SourceConfig(
            name="test-jira",
            type="jira",
            base_url_or_path="https://jira.example.com",
            query="project = PROJ",
            indexer="test-indexer",
        )

        with patch(
            "core.v1.engine.services.collection_service.JiraDocumentReader"
        ) as mock_reader:
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_url="https://jira.example.com",
                query="project = PROJ",
                token="jira-token",
                login=None,
                password=None,
            )

    @patch.dict(
        os.environ,
        {"ATLASSIAN_EMAIL": "user@example.com", "ATLASSIAN_TOKEN": "token123"},
    )
    def test_jira_cloud(self):
        """Test building Jira Cloud reader."""
        config = SourceConfig(
            name="test-jira-cloud",
            type="jiraCloud",
            base_url_or_path="https://company.atlassian.net",
            query="project = PROJ",
            indexer="test-indexer",
        )

        with patch(
            "core.v1.engine.services.collection_service.JiraCloudDocumentReader"
        ) as mock_reader:
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_url="https://company.atlassian.net",
                query="project = PROJ",
                email="user@example.com",
                api_token="token123",
            )

    def test_local_files(self):
        """Test building local files reader."""
        config = SourceConfig(
            name="test-files",
            type="localFiles",
            base_url_or_path="/tmp/docs",
            indexer="test-indexer",
            reader_opts={
                "includePatterns": ["*.md", "*.txt"],
                "excludePatterns": ["*.log"],
                "failFast": True,
            },
        )

        with patch(
            "core.v1.engine.services.collection_service.FilesDocumentReader"
        ) as mock_reader:
            reader, converter = _build_reader_converter(config)

            mock_reader.assert_called_once_with(
                base_path="/tmp/docs",
                include_patterns=["*.md", "*.txt"],
                exclude_patterns=["*.log"],
                fail_fast=True,
            )

    def test_unknown_source_type(self):
        """Test error for unknown source type."""
        config = SourceConfig(
            name="test-unknown",
            type="localFiles",  # We'll change this after creation
            base_url_or_path="/tmp/test",
            indexer="test-indexer",
        )
        # Manually change type to invalid value (bypassing pydantic validation)
        config.__dict__["type"] = "unknownType"

        with pytest.raises(ValueError, match="Unknown source type: unknownType"):
            _build_reader_converter(config)


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

        result = _collection_exists("nonexistent-collection")

        assert result is False


class TestCreateOne:
    """Test _create_one function."""

    @patch("core.v1.engine.services.collection_service._build_reader_converter")
    @patch("core.v1.engine.services.collection_service.create_collection_creator")
    def test_create_one_success(self, mock_factory, mock_build_reader):
        """Test successful creation of one collection."""
        # Setup mocks
        mock_reader = Mock()
        mock_converter = Mock()
        mock_build_reader.return_value = (mock_reader, mock_converter)

        mock_creator = Mock()
        mock_factory.return_value = mock_creator

        config = SourceConfig(
            name="test-collection",
            type="localFiles",
            base_url_or_path="/tmp/test",
            indexer="test-indexer",
        )

        # Call function
        _create_one(config, use_cache=True)

        # Verify calls
        mock_build_reader.assert_called_once_with(config)
        mock_factory.assert_called_once_with(
            collection_name="test-collection",
            indexers=["test-indexer"],
            document_reader=mock_reader,
            document_converter=mock_converter,
            use_cache=True,
            progress_callback=None,
        )
        mock_creator.run.assert_called_once()


class TestUpdateOne:
    """Test _update_one function."""

    @patch("core.v1.engine.services.collection_service.create_collection_updater")
    def test_update_one_success(self, mock_factory):
        """Test successful update of one collection."""
        mock_updater = Mock()
        mock_factory.return_value = mock_updater

        config = SourceConfig(
            name="test-collection",
            type="localFiles",
            base_url_or_path="/tmp/test",
            indexer="test-indexer",
        )

        _update_one(config)

        mock_factory.assert_called_once_with("test-collection", None)
        mock_updater.run.assert_called_once()


class TestPublicFunctions:
    """Test public functions: create, update, clear."""

    @patch("core.v1.engine.services.collection_service._create_one")
    @patch("core.v1.engine.services.collection_service._collection_exists")
    def test_create_without_force(self, mock_exists, mock_create_one):
        """Test create function without force flag."""
        mock_exists.return_value = False

        configs = [
            SourceConfig(
                name="test1",
                type="localFiles",
                base_url_or_path="/tmp/test1",
                indexer="test-indexer",
            ),
            SourceConfig(
                name="test2",
                type="localFiles",
                base_url_or_path="/tmp/test2",
                indexer="test-indexer",
            ),
        ]

        create(configs, use_cache=False)

        assert mock_create_one.call_count == 2
        mock_create_one.assert_any_call(configs[0], False, None)
        mock_create_one.assert_any_call(configs[1], False, None)

    @patch("core.v1.engine.services.collection_service._create_one")
    @patch("core.v1.engine.services.collection_service._collection_exists")
    @patch("core.v1.engine.services.collection_service.clear")
    def test_create_with_force(self, mock_clear, mock_exists, mock_create_one):
        """Test create function with force flag."""
        mock_exists.return_value = True

        config = SourceConfig(
            name="existing-collection",
            type="localFiles",
            base_url_or_path="/tmp/test",
            indexer="test-indexer",
        )

        create([config], force=True)

        mock_clear.assert_called_once_with(["existing-collection"])
        mock_create_one.assert_called_once_with(config, True, None)

    @patch("core.v1.engine.services.collection_service._update_one")
    def test_update(self, mock_update_one):
        """Test update function."""
        configs = [
            SourceConfig(
                name="test1",
                type="localFiles",
                base_url_or_path="/tmp/test1",
                indexer="test-indexer",
            ),
        ]

        update(configs)

        mock_update_one.assert_called_once_with(configs[0], None)

    @patch("core.v1.engine.services.collection_service.DiskPersister")
    def test_clear(self, mock_persister_class):
        """Test clear function."""
        mock_persister = Mock()
        mock_persister_class.return_value = mock_persister

        collection_names = ["collection1", "collection2"]
        clear(collection_names)

        mock_persister_class.assert_called_once_with(base_path="./data/collections")
        assert mock_persister.remove_folder.call_count == 2
        mock_persister.remove_folder.assert_any_call("collection1")
        mock_persister.remove_folder.assert_any_call("collection2")
