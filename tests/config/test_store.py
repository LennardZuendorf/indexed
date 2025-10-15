"""Test TOML file operations and secret filtering."""

from pathlib import Path
import pytest
from core.v1.config.store import (
    read_toml,
    atomic_write_toml,
    validate_no_secrets,
    get_config_path,
    get_backup_path,
)


def test_read_empty_toml(tmp_path, monkeypatch):
    """Test reading non-existent TOML file returns empty dict."""
    monkeypatch.chdir(tmp_path)
    result = read_toml(Path("nonexistent.toml"))
    assert result == {}


def test_atomic_write_and_read(tmp_path, monkeypatch):
    """Test atomic write creates correct TOML file."""
    monkeypatch.chdir(tmp_path)

    data = {
        "search": {"max_docs": 15, "include_full_text": True},
        "paths": {"collections_dir": "./test-collections"},
    }

    config_path = get_config_path()
    atomic_write_toml(data, config_path)

    # Verify file exists
    assert config_path.exists()

    # Read back and verify content
    result = read_toml(config_path)
    assert result["search"]["max_docs"] == 15
    assert result["search"]["include_full_text"] is True
    assert result["paths"]["collections_dir"] == "./test-collections"


def test_secret_filtering(tmp_path, monkeypatch):
    """Test that secrets are filtered out during write."""
    monkeypatch.chdir(tmp_path)

    data_with_secrets = {
        "search": {"max_docs": 20},
        "sources": {
            "jira_cloud": {
                "base_url": "https://test.atlassian.net",
                "email": "test@example.com",
                "jql": "project = TEST",  # This should be kept (not a secret)
                "api_token": "secret-value",  # This should be filtered out
            }
        },
    }

    config_path = get_config_path()
    atomic_write_toml(data_with_secrets, config_path)

    # Read back and verify secret was filtered
    result = read_toml(config_path)
    assert "api_token" not in result["sources"]["jira_cloud"]
    assert result["sources"]["jira_cloud"]["jql"] == "project = TEST"
    assert result["sources"]["jira_cloud"]["base_url"] == "https://test.atlassian.net"


def test_validate_no_secrets():
    """Test secret validation function."""
    # Valid data (no secrets)
    valid_data = {
        "search": {"max_docs": 10},
        "sources": {"jira_cloud": {"jql": "project = TEST"}},
    }
    validate_no_secrets(valid_data)  # Should not raise

    # Invalid data (contains secret)
    invalid_data = {
        "search": {"max_docs": 10},
        "sources": {"jira_cloud": {"api_token": "secret-value"}},
    }

    with pytest.raises(ValueError, match="Secret field.*cannot be persisted"):
        validate_no_secrets(invalid_data)


def test_backup_creation(tmp_path, monkeypatch):
    """Test that backup file is created on subsequent writes."""
    monkeypatch.chdir(tmp_path)

    config_path = get_config_path()
    backup_path = get_backup_path()

    # First write
    data1 = {"search": {"max_docs": 10}}
    atomic_write_toml(data1, config_path)
    assert config_path.exists()
    assert not backup_path.exists()  # No backup on first write

    # Second write should create backup
    data2 = {"search": {"max_docs": 20}}
    atomic_write_toml(data2, config_path)

    assert config_path.exists()
    assert backup_path.exists()  # Backup should exist now

    # Verify backup contains old data
    backup_content = read_toml(backup_path)
    assert backup_content["search"]["max_docs"] == 10

    # Verify current file has new data
    current_content = read_toml(config_path)
    assert current_content["search"]["max_docs"] == 20
