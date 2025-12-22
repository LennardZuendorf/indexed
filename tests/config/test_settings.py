"""Test IndexedSettings schema and TOML loading."""

from core.v1.config.settings import IndexedSettings
from core.v1.config.store import atomic_write_toml


def test_settings_defaults(tmp_path, monkeypatch):
    """Test that IndexedSettings loads with correct defaults."""
    # Run in clean directory with no indexed.toml
    monkeypatch.chdir(tmp_path)
    settings = IndexedSettings()

    assert settings.search.max_docs == 10
    assert settings.search.include_full_text is False
    assert settings.index.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert settings.sources.files.base_path is None
    assert settings.mcp.port == 8000


def test_environment_variable_loading(tmp_path, monkeypatch):
    """Test that environment variables override defaults."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INDEXED__SEARCH__MAX_DOCS", "25")
    monkeypatch.setenv("INDEXED__INDEX__USE_GPU", "true")
    monkeypatch.setenv("INDEXED__SOURCES__FILES__BASE_PATH", "/test/path")

    settings = IndexedSettings()

    assert settings.search.max_docs == 25
    assert settings.index.use_gpu is True
    assert settings.sources.files.base_path == "/test/path"


def test_toml_loading(tmp_path, monkeypatch):
    """Test that TOML workspace config values are loaded via ConfigService."""
    from core.v1.config.store import get_workspace_config_path, atomic_write_toml
    from core.v1.engine.services.config_service import ConfigService

    # Ensure we operate inside an isolated tmp dir
    monkeypatch.chdir(tmp_path)

    toml_file = get_workspace_config_path(tmp_path)
    toml_file.parent.mkdir(parents=True, exist_ok=True)

    config_data = {
        "search": {"max_docs": 50, "include_full_text": True},
        "index": {"embedding_model": "sentence-transformers/all-mpnet-base-v2"},
        "sources": {
            "files": {"base_path": "./test-docs"},
            "jira_cloud": {
                "base_url": "https://test.atlassian.net",
                "email": "test@example.com",
            },
        },
    }

    atomic_write_toml(config_data, toml_file)

    # Load through ConfigService which merges global+workspace config
    settings = ConfigService.get_instance().get()

    assert settings.search.max_docs == 50
    assert settings.search.include_full_text is True
    assert settings.index.embedding_model == "sentence-transformers/all-mpnet-base-v2"
    assert settings.sources.files.base_path == "./test-docs"
    assert settings.sources.jira_cloud.base_url == "https://test.atlassian.net"


def test_precedence_env_over_toml(tmp_path, monkeypatch):
    """Test that environment variables override TOML values."""
    # Create TOML with one value
    from core.v1.config.store import get_config_path

    toml_file = get_config_path()
    config_data = {"search": {"max_docs": 30}}

    monkeypatch.chdir(tmp_path)
    atomic_write_toml(config_data, toml_file)

    # Set env var with different value
    monkeypatch.setenv("INDEXED__SEARCH__MAX_DOCS", "99")

    settings = IndexedSettings()

    # Env var should win
    assert settings.search.max_docs == 99


def test_readiness_flags(tmp_path, monkeypatch):
    """Test source readiness flag logic."""
    monkeypatch.chdir(tmp_path)

    # Test files source readiness (no base_path in clean environment)
    settings = IndexedSettings()
    assert settings.sources.files.is_ready is False  # No base_path

    # Test Jira Cloud readiness using environment variables
    monkeypatch.setenv("JIRA_API_TOKEN", "test-token")
    monkeypatch.setenv(
        "INDEXED__SOURCES__JIRA_CLOUD__BASE_URL", "https://test.atlassian.net"
    )
    monkeypatch.setenv("INDEXED__SOURCES__JIRA_CLOUD__EMAIL", "test@example.com")

    settings_with_jira = IndexedSettings()
    assert settings_with_jira.sources.jira_cloud.is_ready is True
