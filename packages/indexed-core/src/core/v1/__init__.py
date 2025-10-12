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

# Semantic version of the core v1 API. Used for connector compatibility checks.
__version__ = "1.0.0"

__all__ = ["Index", "Config", "__version__"]
