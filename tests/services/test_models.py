"""Tests for services models."""

import pytest
from pydantic import ValidationError

from main.services.models import SourceConfig, CollectionStatus


class TestSourceConfig:
    """Test SourceConfig pydantic model."""

    def test_valid_local_files_config(self):
        """Test creating a valid local files configuration."""
        config = SourceConfig(
            name="test-collection",
            type="localFiles",
            base_url_or_path="/tmp/test",
            query=None,
            indexer="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
            reader_opts={"includePatterns": ["*.txt"], "excludePatterns": ["*.log"]},
        )

        assert config.name == "test-collection"
        assert config.type == "localFiles"
        assert config.base_url_or_path == "/tmp/test"
        assert config.query is None
        assert (
            config.indexer == "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
        )
        assert config.reader_opts == {
            "includePatterns": ["*.txt"],
            "excludePatterns": ["*.log"],
        }

    def test_valid_jira_cloud_config(self):
        """Test creating a valid Jira Cloud configuration."""
        config = SourceConfig(
            name="jira-prod",
            type="jiraCloud",
            base_url_or_path="https://company.atlassian.net",
            query="project = PROJ AND status != Done",
            indexer="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
        )

        assert config.name == "jira-prod"
        assert config.type == "jiraCloud"
        assert config.base_url_or_path == "https://company.atlassian.net"
        assert config.query == "project = PROJ AND status != Done"
        assert config.reader_opts == {}  # Default empty dict

    def test_valid_confluence_cloud_config(self):
        """Test creating a valid Confluence Cloud configuration."""
        config = SourceConfig(
            name="confluence-docs",
            type="confluenceCloud",
            base_url_or_path="https://company.atlassian.net",
            query="space = DOC",
            indexer="indexer_FAISS_IndexFlatL2__embeddings_all-mpnet-base-v2",
            reader_opts={"readOnlyFirstLevelComments": True},
        )

        assert config.name == "confluence-docs"
        assert config.type == "confluenceCloud"
        assert config.reader_opts == {"readOnlyFirstLevelComments": True}

    def test_missing_required_fields(self):
        """Test validation errors for missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            SourceConfig(
                type="localFiles",
                base_url_or_path="/tmp/test",
                indexer="test-indexer",
            )

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("name",) for error in errors)

    def test_invalid_source_type(self):
        """Test validation error for invalid source type."""
        with pytest.raises(ValidationError) as exc_info:
            SourceConfig(
                name="test",
                type="invalidType",  # Invalid type
                base_url_or_path="/tmp/test",
                indexer="test-indexer",
            )

        errors = exc_info.value.errors()
        assert any("type" in str(error) for error in errors)

    def test_default_reader_opts(self):
        """Test that reader_opts defaults to empty dict."""
        config = SourceConfig(
            name="test",
            type="localFiles",
            base_url_or_path="/tmp/test",
            indexer="test-indexer",
        )

        assert config.reader_opts == {}

    def test_all_source_types(self):
        """Test all valid source types."""
        valid_types = [
            "jira",
            "jiraCloud",
            "confluence",
            "confluenceCloud",
            "localFiles",
        ]

        for source_type in valid_types:
            config = SourceConfig(
                name=f"test-{source_type}",
                type=source_type,
                base_url_or_path="https://example.com",
                indexer="test-indexer",
            )
            assert config.type == source_type


class TestCollectionStatus:
    """Test CollectionStatus dataclass."""

    def test_create_collection_status(self):
        """Test creating a CollectionStatus object."""
        status = CollectionStatus(
            name="test-collection",
            number_of_documents=100,
            number_of_chunks=300,
            updated_time="2024-01-01T12:00:00Z",
            last_modified_document_time="2024-01-01T11:00:00Z",
            indexers=["indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"],
            index_size=1500,
        )

        assert status.name == "test-collection"
        assert status.number_of_documents == 100
        assert status.number_of_chunks == 300
        assert status.updated_time == "2024-01-01T12:00:00Z"
        assert status.last_modified_document_time == "2024-01-01T11:00:00Z"
        assert status.indexers == [
            "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2"
        ]
        assert status.index_size == 1500

    def test_collection_status_without_index_size(self):
        """Test CollectionStatus with default None index_size."""
        status = CollectionStatus(
            name="test-collection",
            number_of_documents=50,
            number_of_chunks=150,
            updated_time="2024-01-01T12:00:00Z",
            last_modified_document_time="2024-01-01T11:00:00Z",
            indexers=["test-indexer"],
        )

        assert status.index_size is None

    def test_collection_status_multiple_indexers(self):
        """Test CollectionStatus with multiple indexers."""
        indexers = [
            "indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
            "indexer_FAISS_IndexFlatL2__embeddings_all-mpnet-base-v2",
        ]

        status = CollectionStatus(
            name="multi-index-collection",
            number_of_documents=200,
            number_of_chunks=600,
            updated_time="2024-01-01T12:00:00Z",
            last_modified_document_time="2024-01-01T11:00:00Z",
            indexers=indexers,
        )

        assert status.indexers == indexers
        assert len(status.indexers) == 2
