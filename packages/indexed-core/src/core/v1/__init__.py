"""Indexed v1 API - Simple, clean interface for document search.

Provides high-level Index and Config classes for managing document
collections and performing semantic search.

Examples:
    >>> from core.v1 import Index, Config
    >>> 
    >>> index = Index()
    >>> index.add_collection("docs", connector="filesystem", path="./docs")
    >>> results = index.search("authentication methods")
"""

from .index import Index
from .core_config import Config

__all__ = ["Index", "Config"]
