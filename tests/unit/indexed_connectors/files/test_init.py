"""Registry membership and public export tests for the Files connector."""

from connectors.files import FileSystemConnector


def test_files_init_imports():
    """Test that imports work correctly."""
    assert FileSystemConnector is not None


def test_files_in_connector_registry() -> None:
    from connectors.registry import CONNECTOR_REGISTRY

    assert "localFiles" in CONNECTOR_REGISTRY


def test_files_in_config_registry() -> None:
    from connectors.registry import CONFIG_REGISTRY

    assert "localFiles" in CONFIG_REGISTRY


def test_files_in_namespace_registry() -> None:
    from connectors.registry import NAMESPACE_REGISTRY

    assert NAMESPACE_REGISTRY["localFiles"] == "sources.files"


def test_get_connector_class_files() -> None:
    from connectors.registry import get_connector_class
    from connectors.files.connector import FileSystemConnector

    assert get_connector_class("localFiles") is FileSystemConnector


def test_get_config_class_files() -> None:
    from connectors.registry import get_config_class
    from connectors.files.schema import LocalFilesConfig

    assert get_config_class("localFiles") is LocalFilesConfig
