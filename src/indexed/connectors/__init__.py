"""Document connectors for various sources.

This package provides standardized connector classes for different document sources.
All connectors implement the BaseConnector protocol from protocols.
"""

from .files.connector import FileSystemConnector
from .jira.connector import JiraConnector, JiraCloudConnector
from .confluence.connector import ConfluenceConnector, ConfluenceCloudConnector
from .outline.connector import OutlineConnector

# Registry for dynamic connector lookup
from .registry import (
    CONNECTOR_REGISTRY,
    NAMESPACE_REGISTRY,
    get_connector_class,
    get_config_namespace,
)

__all__ = [
    # Connector classes
    "FileSystemConnector",
    "JiraConnector",
    "JiraCloudConnector",
    "ConfluenceConnector",
    "ConfluenceCloudConnector",
    "OutlineConnector",
    # Registry
    "CONNECTOR_REGISTRY",
    "NAMESPACE_REGISTRY",
    "get_connector_class",
    "get_config_namespace",
]
