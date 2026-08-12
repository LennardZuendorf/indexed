"""Tests for ConfigService class."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel, Field
from indexed.config.errors import ConfigValidationError
from indexed.config.service import ConfigService, get_config, reload


class SampleConfig(BaseModel):
    """Test config model."""

    value: int = Field(..., description="Test value")


class OptionalConfig(BaseModel):
    """Optional config model."""

    name: str = Field(default="default", description="Name")


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
    """Test get_config() returns the cached singleton."""
    reload()  # Reset singleton
    instance1 = get_config()
    instance2 = get_config()

    assert instance1 is instance2
    assert isinstance(instance1, ConfigService)


def test_get_config_does_not_rebuild_for_a_changed_workspace():
    """workspace-profile/1 R1: the singleton serves the GLOBAL base only.

    The profile deliberately does not live here — it travels in a
    ``WorkspaceScope`` — so a different workspace must NOT quietly swap the
    cached service out from under other callers.
    """
    reload()
    first = get_config()

    assert get_config(workspace=Path("/somewhere/else")) is first


class TestLoadRaw:
    """load_raw() reads the ONE global config (workspace-profile/1, R1)."""

    def test_load_raw_reads_the_global_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"

            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"')

            with patch.object(Path, "home", return_value=global_home):
                service = ConfigService(workspace=workspace)
                assert service.load_raw()["test"]["key"] == "global_value"

    def test_load_raw_ignores_a_leftover_local_config(self):
        """A stale ./.indexed/config.toml no longer diverts the read."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"

            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text('[test]\nkey = "local_value"')

            global_dir = global_home / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text('[test]\nkey = "global_value"')

            with patch.object(Path, "home", return_value=global_home):
                service = ConfigService(workspace=workspace)
                assert service.load_raw()["test"]["key"] == "global_value"


class TestResolvedEnvPath:
    """Test that EnvFileWriter gets the correct env path."""

    def test_env_writer_always_uses_the_global_env(self):
        """workspace-profile/1 R1: secrets are written to ~/.indexed/.env."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            global_home = Path(tmpdir) / "home"

            # A leftover local config must not divert the secret.
            local_dir = workspace / ".indexed"
            local_dir.mkdir(parents=True)
            (local_dir / "config.toml").write_text("[test]")

            with patch.object(Path, "home", return_value=global_home):
                service = ConfigService(workspace=workspace)
                assert service._resolved_env_path() == str(
                    global_home / ".indexed" / ".env"
                )


class TestInMemoryOverlay:
    """R3 / foundation/6b bug E4: set_overlay() must never touch disk."""

    def test_set_overlay_visible_via_get(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                service = ConfigService(workspace=Path(tmpdir))
                service.set_overlay("sources.files.path", "/bad/path")
                assert service.get("sources.files.path") == "/bad/path"

    def test_set_overlay_does_not_write_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".indexed" / "config.toml"

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                service = ConfigService(workspace=Path(tmpdir))
                service.set_overlay("sources.files.path", "/bad/path")

            assert (
                not config_path.exists() or "/bad/path" not in config_path.read_text()
            )

    def test_set_overlay_wins_over_disk_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            global_dir = Path(tmpdir) / ".indexed"
            global_dir.mkdir(parents=True)
            (global_dir / "config.toml").write_text(
                '[sources.files]\npath = "/old/path"'
            )

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                service = ConfigService(workspace=Path(tmpdir))
                service.set_overlay("sources.files.path", "/new/path")
                assert service.get("sources.files.path") == "/new/path"

    def test_clear_overlay_removes_all_overrides(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(Path, "home", return_value=Path(tmpdir)):
                service = ConfigService(workspace=Path(tmpdir))
                service.set_overlay("sources.files.path", "/bad/path")
                service.clear_overlay()
                assert service.get("sources.files.path") is None

    def test_set_still_persists_to_disk(self):
        """Only set()/set_value() (the real writer) touches config.toml."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / ".indexed" / "config.toml"

            with patch.object(Path, "home", return_value=Path(tmpdir)):
                ConfigService(workspace=Path(tmpdir)).set(
                    "sources.files.path", "/real/path"
                )

            assert "/real/path" in config_path.read_text()
