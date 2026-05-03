"""Registry membership and public export tests for the Outline connector."""


def test_outline_in_connector_registry() -> None:
    from connectors.registry import CONNECTOR_REGISTRY

    assert "outline" in CONNECTOR_REGISTRY


def test_outline_in_config_registry() -> None:
    from connectors.registry import CONFIG_REGISTRY

    assert "outline" in CONFIG_REGISTRY


def test_outline_in_namespace_registry() -> None:
    from connectors.registry import NAMESPACE_REGISTRY

    assert "outline" in NAMESPACE_REGISTRY
    assert NAMESPACE_REGISTRY["outline"] == "sources.outline"


def test_outline_connector_importable_from_connectors() -> None:
    from connectors import OutlineConnector

    assert OutlineConnector is not None


def test_outline_config_importable_from_connectors() -> None:
    from connectors.outline import OutlineConfig

    assert OutlineConfig is not None


def test_get_connector_class_outline() -> None:
    from connectors.registry import get_connector_class
    from connectors.outline.connector import OutlineConnector

    cls = get_connector_class("outline")
    assert cls is OutlineConnector


def test_get_config_class_outline() -> None:
    from connectors.registry import get_config_class
    from connectors.outline.schema import OutlineConfig

    cls = get_config_class("outline")
    assert cls is OutlineConfig


def test_get_config_namespace_outline() -> None:
    from connectors.registry import get_config_namespace

    ns = get_config_namespace("outline")
    assert ns == "sources.outline"


def test_list_connector_types_includes_outline() -> None:
    from connectors.registry import list_connector_types

    types = list_connector_types()
    assert "outline" in types
