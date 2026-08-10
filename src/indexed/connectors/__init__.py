"""Document connectors for various sources.

This package provides standardized connector classes for different document sources.
All connectors implement the BaseConnector protocol from protocols.
"""

from .confluence.connector import ConfluenceCloudConnector, ConfluenceConnector
from .files.connector import FileSystemConnector
from .jira.connector import JiraCloudConnector, JiraConnector
from .outline.connector import OutlineConnector

# Registry for dynamic connector lookup
from .registry import (
    CONNECTOR_REGISTRY,
    NAMESPACE_REGISTRY,
    get_config_namespace,
    get_connector_class,
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
