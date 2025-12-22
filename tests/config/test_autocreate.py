"""Validate auto-creation behavior for workspace config and .env.example."""

from pathlib import Path
from typing import Dict, Any
import json

from core.v1.config.store import (
    ensure_workspace_config_exists,
    ensure_env_example,
    read_toml,
    get_workspace_config_path,
)
from core.v1.engine.services.config_service import ConfigService


def test_ensure_workspace_config_exists_creates_minimal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg_path = get_workspace_config_path(tmp_path)
    assert not cfg_path.exists()

    ensure_workspace_config_exists(tmp_path)

    assert cfg_path.exists()
    data: Dict[str, Any] = read_toml(cfg_path)

    # Minimal scaffold keys present
    assert "paths" in data
    assert "search" in data and isinstance(data["search"], dict)
    assert "index" in data and isinstance(data["index"], dict)
    assert "sources" in data and isinstance(data["sources"], dict)
    assert "mcp" in data and isinstance(data["mcp"], dict)

    # No secrets persisted; only *_env names
    assert data["sources"]["jira_cloud"]["api_token_env"] == "JIRA_API_TOKEN"
    assert (
        data["sources"]["confluence_cloud"]["api_token_env"] == "CONFLUENCE_API_TOKEN"
    )
    # and there should be no direct token values
    dumped = json.dumps(data)
    assert "secret" not in dumped.lower()


def test_ensure_env_example_creation_and_append(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env_example = Path(".env.example")

    # Create when missing
    ensure_env_example()
    assert env_example.exists()
    content1 = env_example.read_text()
    assert "JIRA_API_TOKEN" in content1
    assert "CONFLUENCE_API_TOKEN" in content1

    # Running again should not duplicate keys
    ensure_env_example()
    content2 = env_example.read_text()
    assert content2.count("JIRA_API_TOKEN") == 1
    assert content2.count("CONFLUENCE_API_TOKEN") == 1

    # If file already contains one key, only append the missing one
    env_example.write_text("JIRA_API_TOKEN=\n")
    ensure_env_example()
    content3 = env_example.read_text()
    assert content3.count("JIRA_API_TOKEN") == 1
    assert content3.count("CONFLUENCE_API_TOKEN") == 1


def test_config_service_get_triggers_creation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Reset singleton
    ConfigService._instance = None
    ConfigService._settings_cache = None

    # Use a temp directory for global config to avoid conflicts with existing config
    temp_global_config_dir = tmp_path / "global_config"
    temp_global_config_dir.mkdir(parents=True)
    temp_global_config_path = temp_global_config_dir / "config.toml"

    # Mock the global config path to use temp directory
    from core.v1.config import store

    def mock_get_global_config_path():
        return temp_global_config_path

    monkeypatch.setattr(store, "get_global_config_path", mock_get_global_config_path)

    workspace_cfg_path = get_workspace_config_path(tmp_path)
    env_example = Path(".env.example")

    assert not workspace_cfg_path.exists()
    assert not temp_global_config_path.exists()
    assert not env_example.exists()

    # Calling get should create files
    service = ConfigService.get_instance()
    settings = service.get()

    # Workspace config should be created
    assert workspace_cfg_path.exists()
    # Global config should be created
    assert temp_global_config_path.exists()
    # .env.example should be created
    assert env_example.exists()

    # Basic sanity on loaded settings
    assert settings.search.max_docs >= 1
