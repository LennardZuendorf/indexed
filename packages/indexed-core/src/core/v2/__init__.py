"""Indexed v2 API — LlamaIndex-powered document search.

Usage::

    from core.v2 import Index, IndexConfig

    index = Index()
    index.add_collection("docs", connector=files_connector)
    results = index.search("authentication methods")

Config registration is explicit — call :func:`core.v2.config.register_config`
from app startup. This module has NO import-time side effects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .index import Index, IndexConfig

__version__ = "2.0.0"

__all__ = ["Index", "IndexConfig"]


def __getattr__(name: str) -> Any:
    if name in ("Index", "IndexConfig"):
        from . import index as _index_mod

        return getattr(_index_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
