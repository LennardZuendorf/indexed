"""Tests for ConfigService functionality."""

import os
import tempfile
from pathlib import Path
from pydantic import BaseModel, Field

import pytest

from indexed_config import ConfigService, Provider


class SampleConfigSpec(BaseModel):
    test_field: str = "default_value"
    test_number: int = 42


class RequiredSpec(BaseModel):
    required_field: str = Field(..., description="Required field")


@pytest.fixture
def temp_workspace():
    """
    Create a temporary directory and set it as the current working directory for the fixture's scope.

    The directory is removed and the original working directory is restored when the fixture finishes.

    Returns:
        Path: Path object pointing to the temporary workspace directory for the test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        original_cwd = os.getcwd()
        os.chdir(tmpdir)
        try:
            yield Path(tmpdir)
        finally:
            os.chdir(original_cwd)


@pytest.fixture
def config_service(temp_workspace):
    """
    Create and return a fresh ConfigService singleton configured for tests.

    Resets the ConfigService singleton, obtains a new instance, and registers
    SampleConfigSpec at "test.config" and RequiredSpec at "test.required".

    Returns:
        ConfigService: the singleton instance with the test specs registered.
    """
    # Clear singleton
    ConfigService._instance = None
    svc = ConfigService.instance()
    # Register test specs
    svc.register(SampleConfigSpec, path="test.config")
    svc.register(RequiredSpec, path="test.required")
    return svc


def test_singleton_pattern():
    """Test ConfigService singleton behavior."""
    ConfigService._instance = None  # Reset
    svc1 = ConfigService.instance()
    svc2 = ConfigService.instance()
    assert svc1 is svc2


def test_basic_set_get(config_service):
    """Test basic set/get operations."""
    config_service.set("test.key", "test_value")
    assert config_service.get("test.key") == "test_value"


def test_nested_set_get(config_service):
    """Test nested dot-path operations."""
    config_service.set("section.subsection.key", "nested_value")
    assert config_service.get("section.subsection.key") == "nested_value"


def test_delete_operation(config_service):
    """Test delete operations."""
    config_service.set("to_delete", "value")
    assert config_service.get("to_delete") == "value"

    result = config_service.delete("to_delete")
    assert result is True
    assert config_service.get("to_delete") is None


def test_config_file_creation(config_service, temp_workspace):
    """Test that config file is created."""
    config_service.set("test.setting", "value")

    config_file = temp_workspace / ".indexed" / "config.toml"
    assert config_file.exists()

    content = config_file.read_text()
    assert "test" in content
    assert "setting" in content


def test_validation_with_specs(config_service):
    """Test validation against registered specs."""
    # Initially empty/missing sections are skipped (treated as optional)
    errors = config_service.validate()
    assert len(errors) == 0

    # Force the section to exist but be invalid (missing required field)
    # We add an unknown field so the payload is not empty/None
    config_service.set("test.required.unknown_field", "value")
    errors = config_service.validate()
    assert len(errors) == 1  # RequiredSpec missing required field

    # Set required field
    config_service.set("test.required.required_field", "provided")
    errors = config_service.validate()
    assert len(errors) == 0


def test_provider_creation(config_service):
    """Test Provider creation and typed access."""
    config_service.set("test.config.test_field", "custom_value")
    config_service.set("test.required.required_field", "required_value")

    provider = config_service.bind()
    assert isinstance(provider, Provider)

    test_spec = provider.get(SampleConfigSpec)
    assert test_spec.test_field == "custom_value"
    assert test_spec.test_number == 42  # default

    req_spec = provider.get(RequiredSpec)
    assert req_spec.required_field == "required_value"


def test_env_variable_override(config_service, temp_workspace):
    """Test environment variable overrides."""
    os.environ["INDEXED__test__config__test_field"] = "env_value"
    try:
        raw = config_service.load_raw()
        assert raw.get("test", {}).get("config", {}).get("test_field") == "env_value"
    finally:
        del os.environ["INDEXED__test__config__test_field"]


def test_merge_order(config_service, temp_workspace):
    """
    Verify that environment variables take precedence over workspace configuration when merging settings.

    Sets a workspace key and an environment variable for the same path, then asserts the merged raw configuration contains the environment value.
    """
    # Set workspace config
    config_service.set("merge.test", "workspace_value")

    # Set env var (should override)
    os.environ["INDEXED__merge__test"] = "env_value"
    try:
        raw = config_service.load_raw()
        assert raw["merge"]["test"] == "env_value"
    finally:
        del os.environ["INDEXED__merge__test"]


def test_unknown_keys_preserved(config_service):
    """Test that unknown keys are preserved."""
    config_service.set("unknown.section.key", "preserved_value")

    # Should not cause validation errors for unknown sections
    raw = config_service.load_raw()
    assert raw["unknown"]["section"]["key"] == "preserved_value"
