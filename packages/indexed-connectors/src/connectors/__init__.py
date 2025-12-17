"""Document connectors for various sources.

This package provides standardized connector classes for different document sources.
All connectors implement the BaseConnector protocol from core.v1.connectors.
"""

from .files.connector import FileSystemConnector
from .jira.connector import JiraConnector, JiraCloudConnector
from .confluence.connector import ConfluenceConnector, ConfluenceCloudConnector

# Registry for dynamic connector lookup
from .registry import (
    CONNECTOR_REGISTRY,
    CONFIG_REGISTRY,
    NAMESPACE_REGISTRY,
    get_connector_class,
    get_config_class,
    get_config_namespace,
    list_connector_types,
)

__all__ = [
    # Connector classes
    "FileSystemConnector",
    "JiraConnector",
    "JiraCloudConnector",
    "ConfluenceConnector",
    "ConfluenceCloudConnector",
    # Registry
    "CONNECTOR_REGISTRY",
    "CONFIG_REGISTRY",
    "NAMESPACE_REGISTRY",
    "get_connector_class",
    "get_config_class",
    "get_config_namespace",
    "list_connector_types",
]
