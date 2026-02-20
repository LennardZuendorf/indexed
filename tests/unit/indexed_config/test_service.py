"""Tests for ConfigService class."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Field
from indexed_config.errors import ConfigValidationError
from indexed_config.service import ConfigService


class SampleConfig(BaseModel):
    """Test config model."""

    value: int = Field(..., description="Test value")


class OptionalConfig(BaseModel):
    """Optional config model."""

    name: str = Field(default="default", description="Name")


def test_config_service_get_raw():
    """Test get_raw() alias for load_raw()."""
    service = ConfigService()
    result1 = service.load_raw()
    result2 = service.get_raw()
    assert result1 == result2


def test_config_service_bind_skips_missing():
    """Test bind() skips specs that are not present in config."""
    service = ConfigService()
    service.register(SampleConfig, path="test.path")

    # Should not raise even though test.path doesn't exist
    provider = service.bind()
    assert provider is not None


def test_config_service_bind_skips_empty_dict():
    """Test bind() skips specs that are empty dict."""
    service = ConfigService()
    service.register(SampleConfig, path="test.path")

    # Set empty dict
    service.set("test.path", {})

    # Should not raise
    provider = service.bind()
    assert provider is not None


def test_config_service_bind_validation_error():
    """Test bind() raises ValueError on validation error."""
    service = ConfigService()
    service.register(SampleConfig, path="test.path")

    # Set invalid value (missing required field)
    service.set("test.path", {"wrong": "value"})

    with pytest.raises(
        (ValueError, ConfigValidationError), match="Invalid config for 'test.path'"
    ):
        service.bind()


def test_config_service_validate():
    """Test validate() returns list of errors."""
    service = ConfigService()
    service.register(SampleConfig, path="test.path")

    # Clear any existing config first
    service.delete("test.path")

    # Empty config should return no errors (skipped)
    errors = service.validate()
    assert errors == []

    # Set invalid config
    service.set("test.path", {"wrong": "value"})
    errors = service.validate()
    assert len(errors) == 1
    assert errors[0][0] == "test.path"
    assert "value" in errors[0][1] or "SampleConfig" in errors[0][1]


def test_config_service_validate_skips_missing():
    """Test validate() skips missing optional sections."""
    service = ConfigService()
    service.register(SampleConfig, path="test.path2")

    # Clear any existing config first
    service.delete("test.path2")

    # No config set, should skip
    errors = service.validate()
    assert errors == []


def test_config_service_validate_skips_empty_dict():
    """Test validate() skips empty dict sections."""
    service = ConfigService()
    service.register(SampleConfig, path="test.path")

    # Set empty dict
    service.set("test.path", {})

    # Should skip empty dict
    errors = service.validate()
    assert errors == []


def test_config_service_instance_singleton():
    """Test instance() class method returns singleton."""
    ConfigService._instance = None  # Reset singleton
    instance1 = ConfigService.instance()
    instance2 = ConfigService.instance()

    assert instance1 is instance2
    assert isinstance(instance1, ConfigService)


class TestLoadRawModeResolution:
    """Test that load_raw() resolves the storage mode correctly."""

    def test_load_raw_with_mode_override_uses_store_read(self):
        """load_raw() delegates to store.read() when mode_override is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"')

            service = ConfigService(workspace=workspace, mode_override="local")
            result = service.load_raw()
            assert result.get("test", {}).get("key") == "local_value"

    def test_load_raw_without_override_resolves_mode(self):
        """load_raw() resolves mode via WorkspaceManager when no override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"

            # Create only global config
            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"')

            # No local config exists → should resolve to global
            with patch.object(Path, "home", return_value=global_home):
                service = ConfigService(workspace=workspace)
                result = service.load_raw()
                assert result.get("test", {}).get("key") == "global_value"

    def test_load_raw_without_override_uses_local_when_exists(self):
        """load_raw() uses local mode when local config exists and no override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"

            # Create both configs
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"')

            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"')

            # Local config exists → resolve_storage_mode returns "local"
            with patch.object(Path, "home", return_value=global_home):
                service = ConfigService(workspace=workspace)
                result = service.load_raw()
                # Should read ONLY local, not merge
                assert result.get("test", {}).get("key") == "local_value"


class TestResolvedEnvPath:
    """Test that EnvFileWriter gets the correct env path."""

    def test_env_writer_uses_resolved_mode_path(self):
        """EnvFileWriter path resolves based on storage mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"

            with patch.object(Path, "home", return_value=global_home):
                # No local config → resolves to global
                service = ConfigService(workspace=workspace)
                env_path = service._resolved_env_path()
                expected = str(global_home / ".indexed" / ".env")
                assert env_path == expected

    def test_env_writer_uses_local_when_local_config_exists(self):
        """EnvFileWriter path resolves to local when local config exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"

            # Create local config
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text("[test]")

            with patch.object(Path, "home", return_value=global_home):
                service = ConfigService(workspace=workspace)
                env_path = service._resolved_env_path()
                expected = str(workspace / ".indexed" / ".env")
                assert env_path == expected
