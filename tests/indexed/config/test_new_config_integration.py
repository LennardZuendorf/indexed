"""Integration tests for new config system migration."""

import pytest
import os
from pathlib import Path
from indexed_config import ConfigService


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Create an isolated ConfigService that uses a temp directory.
    
    This prevents tests from polluting the real .indexed/config.toml.
    """
    # Reset singleton before each test
    ConfigService.reset()
    
    # Create the config in temp directory
    config_dir = tmp_path / ".indexed"
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Change to temp directory so ConfigService uses it
    monkeypatch.chdir(tmp_path)
    
    config = ConfigService(workspace=tmp_path)
    yield config
    
    # Reset singleton after test
    ConfigService.reset()


def test_config_service_crud_operations(isolated_config):
    """Test basic CRUD operations on ConfigService."""
    config = isolated_config

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


def test_connector_direct_instantiation(tmp_path):
    """Test that connectors can be instantiated directly with constructor args."""
    from connectors.files import FileSystemConnector

    # Create a temporary test directory
    test_dir = tmp_path / "test"
    test_dir.mkdir()

    # Create connector directly (no from_dto needed)
    connector = FileSystemConnector(
        path=str(test_dir),
        include_patterns=[r".*\.md$"],
        exclude_patterns=[],
        fail_fast=False,
    )

    # Verify connector has expected properties
    assert hasattr(connector, "reader")
    assert hasattr(connector, "converter")
    assert connector.connector_type == "localFiles"


def test_jira_connector_direct_instantiation():
    """Test Jira connector instantiation directly."""
    from connectors.jira import JiraCloudConnector

    # Create connector directly with all required args
    connector = JiraCloudConnector(
        url="https://test.atlassian.net",
        email="test@example.com",
        api_token="test-token",
        query="project = TEST",
    )

    # Verify connector has expected properties
    assert hasattr(connector, "reader")
    assert hasattr(connector, "converter")
    assert connector.connector_type == "jiraCloud"


def test_config_service_validate(tmp_path, monkeypatch):
    """Test config validation with registered specs."""
    from connectors.files.schema import LocalFilesConfig

    # Reset and create isolated config
    ConfigService.reset()
    monkeypatch.chdir(tmp_path)
    
    # Create a temporary test directory
    test_dir = tmp_path / "test"
    test_dir.mkdir()

    config = ConfigService(workspace=tmp_path)

    # Register a spec
    config.register(LocalFilesConfig, path="sources.files")

    # Set valid config with existing path
    config.set("sources.files.path", str(test_dir))

    # Validate should return empty errors
    errors = config.validate()
    assert len(errors) == 0
    
    ConfigService.reset()


def test_config_merging_priority(tmp_path, monkeypatch):
    """Test that config sources are merged correctly."""
    ConfigService.reset()
    monkeypatch.chdir(tmp_path)
    
    config = ConfigService(workspace=tmp_path)

    # Set workspace config
    config.set("sources.files.path", "./workspace")

    raw = config.load_raw()

    # Workspace should override defaults
    assert raw["sources"]["files"]["path"] == "./workspace"
    
    ConfigService.reset()


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
