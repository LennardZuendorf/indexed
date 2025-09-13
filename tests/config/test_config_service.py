"""Test ConfigService CRUD operations and functionality."""

import pytest
from src.main.services.config_service import ConfigService, get_config
from src.main.config.store import atomic_write_toml, get_config_path


@pytest.fixture
def clean_service(tmp_path, monkeypatch):
    """Provide a clean ConfigService instance in isolated directory."""
    monkeypatch.chdir(tmp_path)
    # Reset singleton
    ConfigService._instance = None
    ConfigService._settings_cache = None
    return ConfigService.get_instance()


def test_singleton_pattern(clean_service):
    """Test that ConfigService follows singleton pattern."""
    service1 = ConfigService.get_instance()
    service2 = ConfigService.get_instance()
    
    assert service1 is service2
    assert service1 is clean_service


def test_get_basic_functionality(clean_service):
    """Test basic get operation loads default settings."""
    settings = clean_service.get()
    
    assert settings.search.max_docs == 10  # Default value
    assert settings.search.include_full_text is False
    assert settings.index.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"


def test_get_with_existing_toml(clean_service, tmp_path, monkeypatch):
    """Test get operation loads from existing TOML file."""
    # Create TOML with custom values
    config_data = {
        "search": {"max_docs": 50, "include_full_text": True},
        "index": {"use_gpu": True}
    }
    atomic_write_toml(config_data, get_config_path())
    
    settings = clean_service.get()
    
    assert settings.search.max_docs == 50
    assert settings.search.include_full_text is True
    assert settings.index.use_gpu is True


def test_set_operation(clean_service):
    """Test set operation overwrites configuration."""
    new_config = {
        "search": {"max_docs": 25, "include_full_text": True},
        "paths": {"collections_dir": "./custom-collections"}
    }
    
    clean_service.set(new_config)
    
    # Verify settings were updated
    settings = clean_service.get()
    assert settings.search.max_docs == 25
    assert settings.search.include_full_text is True
    assert settings.paths.collections_dir == "./custom-collections"


def test_update_operation(clean_service):
    """Test update operation merges patch into existing config."""
    # Set initial config
    initial_config = {
        "search": {"max_docs": 10, "include_full_text": False},
        "index": {"use_gpu": False}
    }
    clean_service.set(initial_config)
    
    # Update with patch
    patch = {
        "search": {"max_docs": 30},  # Change this
        "paths": {"collections_dir": "./new-path"}  # Add this
    }
    clean_service.update(patch)
    
    # Verify merge worked correctly
    settings = clean_service.get()
    assert settings.search.max_docs == 30  # Updated
    assert settings.search.include_full_text is False  # Preserved
    assert settings.index.use_gpu is False  # Preserved
    assert settings.paths.collections_dir == "./new-path"  # Added


def test_delete_operation(clean_service):
    """Test delete operation removes specified keys."""
    # Set initial config
    initial_config = {
        "search": {"max_docs": 20, "include_full_text": True, "max_chunks": 50},
        "paths": {"collections_dir": "./test-collections"}
    }
    clean_service.set(initial_config)
    
    # Delete specific keys
    clean_service.delete(["search.include_full_text", "paths.collections_dir"])
    
    # Verify keys were removed (should fall back to defaults)
    settings = clean_service.get()
    assert settings.search.max_docs == 20  # Preserved
    assert settings.search.include_full_text is False  # Back to default
    assert settings.paths.collections_dir == "./data/collections"  # Back to default


def test_profile_operations(clean_service):
    """Test profile creation, listing, and loading."""
    # Initially no profiles
    assert clean_service.list_profiles() == []
    
    # Create profiles
    dev_config = {"search": {"max_docs": 5}, "index": {"use_gpu": False}}
    prod_config = {"search": {"max_docs": 100}, "index": {"use_gpu": True}}
    
    clean_service.create_profile("dev", dev_config)
    clean_service.create_profile("prod", prod_config)
    
    # Verify profiles exist
    profiles = clean_service.list_profiles()
    assert "dev" in profiles
    assert "prod" in profiles
    
    # Test profile loading
    dev_settings = clean_service.get(profile="dev")
    assert dev_settings.search.max_docs == 5
    assert dev_settings.index.use_gpu is False
    
    prod_settings = clean_service.get(profile="prod")
    assert prod_settings.search.max_docs == 100
    assert prod_settings.index.use_gpu is True


def test_profile_with_base_config(clean_service):
    """Test that profiles overlay base configuration correctly."""
    # Set base config
    base_config = {
        "search": {"max_docs": 10, "include_full_text": True},
        "index": {"use_gpu": False, "embedding_batch_size": 32}
    }
    clean_service.set(base_config)
    
    # Create profile that only overrides some values
    profile_config = {"search": {"max_docs": 99}}
    clean_service.create_profile("test", profile_config)
    
    # Load with profile
    settings = clean_service.get(profile="test")
    
    # Profile value should override
    assert settings.search.max_docs == 99
    # Base values should be preserved
    assert settings.search.include_full_text is True
    assert settings.index.use_gpu is False
    assert settings.index.embedding_batch_size == 32


def test_runtime_overrides(clean_service):
    """Test runtime overrides work correctly."""
    # Set base config
    base_config = {"search": {"max_docs": 10}}
    clean_service.set(base_config)
    
    # Test overrides without profile
    overrides = {"search": {"max_docs": 777}, "index": {"use_gpu": True}}
    settings = clean_service.get(overrides=overrides)
    
    assert settings.search.max_docs == 777
    assert settings.index.use_gpu is True
    
    # Verify base config unchanged
    base_settings = clean_service.get()
    assert base_settings.search.max_docs == 10


def test_profile_with_runtime_overrides(clean_service):
    """Test profile + runtime overrides work together."""
    # Create profile
    profile_config = {"search": {"max_docs": 50, "include_full_text": True}}
    clean_service.create_profile("test", profile_config)
    
    # Apply runtime overrides on top of profile
    overrides = {"search": {"max_docs": 999}}
    settings = clean_service.get(profile="test", overrides=overrides)
    
    # Runtime override should win
    assert settings.search.max_docs == 999
    # Profile value should be preserved where not overridden
    assert settings.search.include_full_text is True


def test_secret_validation(clean_service):
    """Test that secrets are rejected in all operations."""
    # Test set with secrets
    with pytest.raises(ValueError, match="Secret field.*cannot be persisted"):
        clean_service.set({"sources": {"jira_cloud": {"api_token": "secret"}}})
    
    # Test update with secrets
    with pytest.raises(ValueError, match="Secret field.*cannot be persisted"):
        clean_service.update({"sources": {"jira_cloud": {"password": "secret"}}})
    
    # Test profile creation with secrets
    with pytest.raises(ValueError, match="Secret field.*cannot be persisted"):
        clean_service.create_profile("bad", {"sources": {"jira_cloud": {"credential": "secret"}}})


def test_caching_behavior(clean_service):
    """Test that caching works correctly."""
    # First call should cache
    settings1 = clean_service.get()
    settings2 = clean_service.get()
    
    # Should return same cached instance
    assert settings1 is settings2
    
    # Update should invalidate cache
    clean_service.update({"search": {"max_docs": 99}})
    settings3 = clean_service.get()
    
    # Should be different instance with new values
    assert settings3 is not settings1
    assert settings3.search.max_docs == 99


def test_convenience_functions(clean_service):
    """Test convenience functions work correctly."""
    # Test get_config
    settings1 = get_config()
    settings2 = clean_service.get()
    
    # Should return equivalent settings
    assert settings1.search.max_docs == settings2.search.max_docs
    
    # Test with overrides
    override_settings = get_config(overrides={"search": {"max_docs": 555}})
    assert override_settings.search.max_docs == 555


def test_profile_update_and_delete(clean_service):
    """Test updating and deleting profile configurations."""
    # Create initial profile
    clean_service.create_profile("test", {"search": {"max_docs": 20}})
    
    # Update profile
    clean_service.update({"search": {"include_full_text": True}}, profile="test")
    
    # Verify profile was updated
    settings = clean_service.get(profile="test")
    assert settings.search.max_docs == 20  # Preserved
    assert settings.search.include_full_text is True  # Added
    
    # Delete from profile
    clean_service.delete(["search.max_docs"], profile="test")
    
    # Verify key was removed from profile
    settings = clean_service.get(profile="test")
    assert settings.search.max_docs == 10  # Back to default
    assert settings.search.include_full_text is True  # Still in profile
