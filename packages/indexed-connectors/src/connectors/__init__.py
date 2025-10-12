"""Document connectors for various sources.

This package provides standardized connector classes for different document sources.
All connectors implement the BaseConnector protocol from core.v1.connectors.
"""

from .files.connector import FileSystemConnector
from .jira.connector import JiraConnector, JiraCloudConnector
from .confluence.connector import ConfluenceConnector, ConfluenceCloudConnector

__all__ = [
    "FileSystemConnector",
    "JiraConnector",
    "JiraCloudConnector",
    "ConfluenceConnector",
    "ConfluenceCloudConnector",
]
