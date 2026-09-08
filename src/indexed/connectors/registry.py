"""Connector registry for dynamic connector lookup.

This module provides a registry that maps connector type identifiers to their
corresponding connector classes. This enables:
- Dynamic connector instantiation based on type string
- Decoupling of service layer from specific connector imports
- Easier testing and mocking
"""

from typing import Dict, Type, Any

# Import all connector classes
from .files.connector import FileSystemConnector
from .jira.connector import JiraConnector, JiraCloudConnector
from .confluence.connector import ConfluenceConnector, ConfluenceCloudConnector
from .outline.connector import OutlineConnector
from .github.connector import GitHubConnector


# Registry mapping connector_type strings to connector classes
# The keys match the connector_type property of each connector
CONNECTOR_REGISTRY: Dict[str, Type[Any]] = {
    "localFiles": FileSystemConnector,
    "jira": JiraConnector,
    "jiraCloud": JiraCloudConnector,
    "confluence": ConfluenceConnector,
    "confluenceCloud": ConfluenceCloudConnector,
    "outline": OutlineConnector,
    "github": GitHubConnector,
}

# Registry mapping connector_type strings to their config namespace paths
# NOTE: Cloud and Server variants use UNIFIED namespaces (e.g., both jira and
# jiraCloud use "sources.jira"). The Cloud vs Server type is determined at
# runtime from the URL. This matches the pattern in collection_service.py.
NAMESPACE_REGISTRY: Dict[str, str] = {
    "localFiles": "sources.files",
    "jira": "sources.jira",
    "jiraCloud": "sources.jira",  # Unified with jira
    "confluence": "sources.confluence",
    "confluenceCloud": "sources.confluence",  # Unified with confluence
    "outline": "sources.outline",
    "github": "sources.github",
}

# Registry mapping connector_type strings to the config key their
# ``SourceConfig.base_url_or_path`` writes to. Most sources call it "url";
# files stores a filesystem "path" and GitHub a "host", so the composition
# root must look this up instead of assuming "url".
PATH_KEY_REGISTRY: Dict[str, str] = {
    "localFiles": "path",
    "jira": "url",
    "jiraCloud": "url",
    "confluence": "url",
    "confluenceCloud": "url",
    "outline": "url",
    "github": "host",
}


def get_connector_class(connector_type: str) -> Type[Any]:
    """Get connector class by type identifier.

    Args:
        connector_type: Connector type string (e.g., "jiraCloud", "localFiles")

    Returns:
        Connector class that can be instantiated

    Raises:
        ValueError: If connector_type is not registered

    Examples:
        >>> cls = get_connector_class("jiraCloud")
        >>> connector = cls.from_dto(config)
    """
    if connector_type not in CONNECTOR_REGISTRY:
        available = ", ".join(CONNECTOR_REGISTRY.keys())
        raise ValueError(
            f"Unknown connector type: '{connector_type}'. Available types: {available}"
        )
    return CONNECTOR_REGISTRY[connector_type]


def get_config_namespace(connector_type: str) -> str:
    """Get config namespace path by connector type.

    Args:
        connector_type: Connector type string

    Returns:
        Config namespace path (e.g., "sources.jira")

    Raises:
        ValueError: If connector_type is not registered
    """
    if connector_type not in NAMESPACE_REGISTRY:
        available = ", ".join(NAMESPACE_REGISTRY.keys())
        raise ValueError(
            f"Unknown connector type: '{connector_type}'. Available types: {available}"
        )
    return NAMESPACE_REGISTRY[connector_type]


def get_source_path_key(connector_type: str) -> str:
    """Get the config key a source's base_url_or_path writes to.

    Args:
        connector_type: Connector type string

    Returns:
        Config key name (e.g., "url", "path", "host")

    Raises:
        ValueError: If connector_type is not registered
    """
    if connector_type not in PATH_KEY_REGISTRY:
        available = ", ".join(PATH_KEY_REGISTRY.keys())
        raise ValueError(
            f"Unknown connector type: '{connector_type}'. Available types: {available}"
        )
    return PATH_KEY_REGISTRY[connector_type]
