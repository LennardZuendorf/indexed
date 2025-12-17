"""Tests for Provider class."""
import pytest
from pydantic import BaseModel
from indexed_config.provider import Provider


class SampleConfig(BaseModel):
    """Test config model."""
    value: int


class AnotherConfig(BaseModel):
    """Another test config model."""
    name: str


def test_provider_get():
    """Test Provider.get() retrieves config by type."""
    config = SampleConfig(value=42)
    provider = Provider({SampleConfig: config}, {}, {})
    
    result = provider.get(SampleConfig)
    assert result == config
    assert result.value == 42


def test_provider_get_not_found():
    """Test Provider.get() raises KeyError when config not found."""
    provider = Provider({}, {}, {})
    
    with pytest.raises(KeyError, match="Config spec SampleConfig not found"):
        provider.get(SampleConfig)


def test_provider_get_by_path():
    """Test Provider.get_by_path() retrieves config by path."""
    config = SampleConfig(value=42)
    provider = Provider(
        {SampleConfig: config},
        {},
        {"test.path": SampleConfig}
    )
    
    result = provider.get_by_path("test.path")
    assert result == config
    assert result.value == 42


def test_provider_get_by_path_not_found():
    """Test Provider.get_by_path() raises KeyError when path not found."""
    provider = Provider({}, {}, {})
    
    with pytest.raises(KeyError, match="Config path 'test.path' not found"):
        provider.get_by_path("test.path")


def test_provider_raw():
    """Test Provider.raw property returns raw config dict."""
    raw_data = {"a": {"b": 42}}
    provider = Provider({}, raw_data, {})
    
    assert provider.raw == raw_data


def test_provider_with_path_to_type():
    """Test Provider works with path_to_type mapping."""
    config1 = SampleConfig(value=42)
    config2 = AnotherConfig(name="test")
    provider = Provider(
        {SampleConfig: config1, AnotherConfig: config2},
        {},
        {"test.path": SampleConfig, "another.path": AnotherConfig}
    )
    
    assert provider.get_by_path("test.path") == config1
    assert provider.get_by_path("another.path") == config2


def test_provider_none_path_to_type():
    """Test Provider handles None path_to_type."""
    config = SampleConfig(value=42)
    provider = Provider({SampleConfig: config}, {}, None)
    
    # Should still work for get()
    assert provider.get(SampleConfig) == config
    
    # But get_by_path() should fail
    with pytest.raises(KeyError):
        provider.get_by_path("test.path")
