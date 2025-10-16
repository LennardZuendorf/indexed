"""Confluence connectors for indexing pages from Confluence Server/DC and Cloud."""

from .connector import ConfluenceConnector, ConfluenceCloudConnector

__all__ = ["ConfluenceConnector", "ConfluenceCloudConnector"]