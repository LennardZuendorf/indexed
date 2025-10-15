"""Connector protocol and interfaces for document sources."""

from .base import BaseConnector
from .metadata import ConnectorMetadata

__all__ = ["BaseConnector", "ConnectorMetadata"]
