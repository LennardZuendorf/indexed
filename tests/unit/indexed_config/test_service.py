"""Tests for ConfigService class."""

import pytest
from pydantic import BaseModel, Field
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

    with pytest.raises(ValueError, match="Invalid config for 'test.path'"):
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
