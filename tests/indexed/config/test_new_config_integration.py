"""Integration tests for new config system migration."""

import pytest
from indexed_config import ConfigService


def test_config_service_crud_operations(tmp_path):
    """Test basic CRUD operations on ConfigService."""
    # Create a config service
    config = ConfigService()

    # Test set
    config.set("sources.jira_cloud.url", "https://test.atlassian.net")
    config.set("sources.jira_cloud.query", "project = TEST")

    # Test get (via load_raw)
    raw = config.load_raw()
    assert "sources" in raw
    assert "jira_cloud" in raw["sources"]
    assert raw["sources"]["jira_cloud"]["url"] == "https://test.atlassian.net"
    assert raw["sources"]["jira_cloud"]["query"] == "project = TEST"

    # Test delete
    deleted = config.delete("sources.jira_cloud.query")
    assert deleted is True

    raw = config.load_raw()
    assert "query" not in raw["sources"]["jira_cloud"]

    # Test delete non-existent key
    deleted = config.delete("sources.nonexistent.key")
    assert deleted is False


def test_connector_from_dto(tmp_path):
    """Test that connectors can be instantiated via from_dto()."""
    from connectors.files import FileSystemConnector
    from connectors.files.schema import LocalFilesConfig

    # Create a temporary test directory
    test_dir = tmp_path / "test"
    test_dir.mkdir()

    # Create a config DTO directly
    config_dto = LocalFilesConfig(
        path=str(test_dir),
        include_patterns=[r".*\.md$"],  # Use regex, not glob
        exclude_patterns=[],
        fail_fast=False,
    )

    # Create connector from DTO
    connector = FileSystemConnector.from_dto(config_dto)

    # Verify connector has expected properties
    assert hasattr(connector, "reader")
    assert hasattr(connector, "converter")
    assert connector.connector_type == "localFiles"


def test_jira_connector_from_dto():
    """Test Jira connector instantiation via from_dto()."""
    from connectors.jira import JiraCloudConnector
    from connectors.jira.schema import JiraCloudConfig
    import os

    # Set required env vars
    os.environ["ATLASSIAN_EMAIL"] = "test@example.com"
    os.environ["ATLASSIAN_TOKEN"] = "test-token"

    try:
        # Create a config DTO directly
        config_dto = JiraCloudConfig(
            url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
            query="project = TEST",
        )

        # Create connector from DTO
        connector = JiraCloudConnector.from_dto(config_dto)

        # Verify connector has expected properties
        assert hasattr(connector, "reader")
        assert hasattr(connector, "converter")
        assert connector.connector_type == "jiraCloud"
    finally:
        # Cleanup
        del os.environ["ATLASSIAN_EMAIL"]
        del os.environ["ATLASSIAN_TOKEN"]


def test_config_service_validate(tmp_path):
    """Test config validation with registered specs."""
    from connectors.files.schema import LocalFilesConfig

    # Create a temporary test directory
    test_dir = tmp_path / "test"
    test_dir.mkdir()

    config = ConfigService()

    # Register a spec
    config.register(LocalFilesConfig, path="sources.files")

    # Set valid config with existing path
    config.set("sources.files.path", str(test_dir))

    # Validate should return empty errors
    errors = config.validate()
    assert len(errors) == 0


def test_config_merging_priority():
    """Test that config sources are merged correctly."""
    config = ConfigService()

    # Set workspace config
    config.set("sources.files.path", "./workspace")

    raw = config.load_raw()

    # Workspace should override defaults
    assert raw["sources"]["files"]["path"] == "./workspace"


def test_collection_service_with_config():
    """Test that collection service works with new config system."""
    from core.v1.engine.services import SourceConfig

    # Create a source config to verify API compatibility
    source_cfg = SourceConfig(
        name="test-collection",
        type="localFiles",
        base_url_or_path="./test",
        indexer="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
        reader_opts={"includePatterns": ["*.txt"], "excludePatterns": [], "failFast": False},
    )

    # Verify the source config was created successfully
    assert source_cfg.name == "test-collection"
    assert source_cfg.type == "localFiles"
    
    # Note: We're not actually creating the collection here
    # Just verifying that the API is compatible with the new config system


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
