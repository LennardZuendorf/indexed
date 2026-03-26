"""Indexed v2 API — LlamaIndex-powered document search.

Usage::

    from core.v2 import Index, IndexConfig

    index = Index()
    index.add_collection("docs", connector=files_connector)
    results = index.search("authentication methods")

Config registration is explicit — call :func:`core.v2.config.register_config`
from app startup. This module has NO import-time side effects.
"""

__version__ = "2.0.0"

__all__ = ["__version__"]
