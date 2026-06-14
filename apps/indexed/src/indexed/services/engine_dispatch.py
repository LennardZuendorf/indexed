"""Engine service dispatch — maps an engine name to its service module.

Kept separate from :mod:`engine_router` (which resolves *which* engine to use)
so each module stays small and single-purpose. Imports are lazy so selecting
v1 never loads v2's LlamaIndex stack and vice versa.
"""

from __future__ import annotations

from typing import Any


def get_collection_service(engine: str) -> Any:
    """Return the collection service module (``create``/``update``/``clear``)."""
    if engine == "v2":
        from core.v2.services import collection_service as svc
    else:
        from core.v1.engine.services import collection_service as svc
    return svc


def get_search_service(engine: str) -> Any:
    """Return the search service module (``search``/``SearchService``)."""
    if engine == "v2":
        from core.v2.services import search_service as svc
    else:
        from core.v1.engine.services import search_service as svc
    return svc


def get_inspect_service(engine: str) -> Any:
    """Return the inspect service module (``status``/``inspect``)."""
    if engine == "v2":
        from core.v2.services import inspect_service as svc
    else:
        from core.v1.engine.services import inspect_service as svc
    return svc
