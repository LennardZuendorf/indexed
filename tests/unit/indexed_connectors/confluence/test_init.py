"""Registry membership and public export tests for the Confluence connector."""

from connectors.confluence import ConfluenceConnector, ConfluenceCloudConnector


def test_confluence_init_imports():
    """Test that imports work correctly."""
    assert ConfluenceConnector is not None
    assert ConfluenceCloudConnector is not None


def test_confluence_in_connector_registry() -> None:
    from connectors.registry import CONNECTOR_REGISTRY

    assert "confluence" in CONNECTOR_REGISTRY
    assert "confluenceCloud" in CONNECTOR_REGISTRY


def test_confluence_in_config_registry() -> None:
    from connectors.registry import CONFIG_REGISTRY

    assert "confluence" in CONFIG_REGISTRY
    assert "confluenceCloud" in CONFIG_REGISTRY


def test_confluence_in_namespace_registry() -> None:
    from connectors.registry import NAMESPACE_REGISTRY

    assert NAMESPACE_REGISTRY["confluence"] == "sources.confluence"
    assert NAMESPACE_REGISTRY["confluenceCloud"] == "sources.confluence"


def test_get_connector_class_confluence() -> None:
    from connectors.registry import get_connector_class
    from connectors.confluence.connector import (
        ConfluenceConnector,
        ConfluenceCloudConnector,
    )

    assert get_connector_class("confluence") is ConfluenceConnector
    assert get_connector_class("confluenceCloud") is ConfluenceCloudConnector


def test_get_config_class_confluence() -> None:
    from connectors.registry import get_config_class
    from connectors.confluence.schema import ConfluenceConfig, ConfluenceCloudConfig

    assert get_config_class("confluence") is ConfluenceConfig
    assert get_config_class("confluenceCloud") is ConfluenceCloudConfig
