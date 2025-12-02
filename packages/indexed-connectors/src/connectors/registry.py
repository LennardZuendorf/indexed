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

# Import config DTOs for type hints
from .files.schema import LocalFilesConfig
from .jira.schema import JiraConfig, JiraCloudConfig
from .confluence.schema import ConfluenceConfig, ConfluenceCloudConfig


# Registry mapping connector_type strings to connector classes
# The keys match the connector_type property of each connector
CONNECTOR_REGISTRY: Dict[str, Type[Any]] = {
    "localFiles": FileSystemConnector,
    "jira": JiraConnector,
    "jiraCloud": JiraCloudConnector,
    "confluence": ConfluenceConnector,
    "confluenceCloud": ConfluenceCloudConnector,
}

# Registry mapping connector_type strings to their config DTO classes
CONFIG_REGISTRY: Dict[str, Type[Any]] = {
    "localFiles": LocalFilesConfig,
    "jira": JiraConfig,
    "jiraCloud": JiraCloudConfig,
    "confluence": ConfluenceConfig,
    "confluenceCloud": ConfluenceCloudConfig,
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
            f"Unknown connector type: '{connector_type}'. "
            f"Available types: {available}"
        )
    return CONNECTOR_REGISTRY[connector_type]


def get_config_class(connector_type: str) -> Type[Any]:
    """Get config DTO class by connector type.
    
    Args:
        connector_type: Connector type string
        
    Returns:
        Pydantic config class for the connector
        
    Raises:
        ValueError: If connector_type is not registered
    """
    if connector_type not in CONFIG_REGISTRY:
        available = ", ".join(CONFIG_REGISTRY.keys())
        raise ValueError(
            f"Unknown connector type: '{connector_type}'. "
            f"Available types: {available}"
        )
    return CONFIG_REGISTRY[connector_type]


def get_config_namespace(connector_type: str) -> str:
    """Get config namespace path by connector type.
    
    Args:
        connector_type: Connector type string
        
    Returns:
        Config namespace path (e.g., "sources.jira_cloud")
        
    Raises:
        ValueError: If connector_type is not registered
    """
    if connector_type not in NAMESPACE_REGISTRY:
        available = ", ".join(NAMESPACE_REGISTRY.keys())
        raise ValueError(
            f"Unknown connector type: '{connector_type}'. "
            f"Available types: {available}"
        )
    return NAMESPACE_REGISTRY[connector_type]


def list_connector_types() -> list[str]:
    """List all registered connector types.
    
    Returns:
        List of connector type identifiers
    """
    return list(CONNECTOR_REGISTRY.keys())

