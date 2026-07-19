"""Version-dispatching core engine facade (core-v2/1).

The app (CLI/MCP) imports collection/search/inspect operations and the shared
models from ``indexed.core.engine`` — never from ``core.v1.engine`` (or a future
``core.v2.engine``) directly. This facade re-exports the exact 14-name v1 surface
with identical signatures and adds a thin per-collection routing layer:

- **create** chooses the engine from an already-resolved selector (R3) — a new
  collection's engine.
- **existing-collection ops** resolve the engine FROM the collection's on-disk
  ``version`` marker (R2); an explicit conflicting ``engine`` raises
  ``EngineMismatchError`` before any I/O.

Only v1 exists today: unmarked and ``version: "1"`` collections route to v1;
``--engine v2`` (``engine="2"``) is detected and fails cleanly until a later unit
implements it. Resolution stays lazy — no heavy imports at module top, mirroring
the v1 facade — so CLI startup stays <1s and no LlamaIndex import happens here.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from indexed.config.errors import ConfigurationError
from indexed.core.errors import EngineMismatchError, EngineNotAvailableError
from indexed.core.versioning import EngineVersion, detect_engine_version

# Shared types/classes re-exported unchanged from v1 (no routing) — resolved
# lazily so importing the facade stays cheap. v2 will reuse the same types.
_SHARED_TYPES = frozenset(
    {
        "SourceConfig",
        "CollectionStatus",
        "CollectionInfo",
        "PhasedProgressCallback",
        "SearchService",
        "InspectService",
    }
)

# Routed callables — defined as real functions below (each adds version dispatch).
_ROUTED = frozenset(
    {
        "create",
        "update",
        "clear",
        "collection_exists",
        "search",
        "status",
        "inspect",
    }
)

# Same 14-name surface as ``core.v1.engine._EXPORTS`` (asserted equal in tests).
_EXPORTS = _SHARED_TYPES | _ROUTED

_DEFAULT_ENGINE: EngineVersion = "1"
_SUPPORTED_ENGINES = ("1", "2")

# Transient build-aside/rollback dirs the durable-create path leaves on disk;
# excluded from collection discovery exactly as v1 does.
_INTERNAL_COLLECTION_DIR_RE = re.compile(r"\.(tmp|trash)-\d+")


def _validate_engine(engine: str) -> EngineVersion:
    """Coerce an engine selector to a supported ``EngineVersion`` or fail clearly."""
    if engine == "1":
        return "1"
    if engine == "2":
        return "2"
    raise ConfigurationError(
        f"Unknown engine {engine!r}; supported engines: {', '.join(_SUPPORTED_ENGINES)}"
    )


def _engine_impl(version: EngineVersion) -> Any:
    """Return the engine services module for a version.

    The single indirection every routed op dispatches through. core-v2/2 makes
    the ``"2"`` branch real by importing the v2 engine here instead of raising.
    """
    if version == "1":
        from indexed.core.v1.engine import services as _v1_services

        return _v1_services
    if version == "2":
        raise EngineNotAvailableError("2")
    raise _validate_engine(version)  # pragma: no cover - unreachable, kept explicit


def _collections_base(collections_path: Optional[str]) -> Path:
    """Resolve the collections directory exactly as the v1 services do."""
    if collections_path:
        return Path(collections_path)
    from indexed.core.v1.config_models import get_default_collections_path

    return Path(get_default_collections_path())


def _existing_collection_names(collections_path: Optional[str]) -> List[str]:
    """List existing collection names (mirrors v1's manifest-based discovery)."""
    base = _collections_base(collections_path)
    if not base.is_dir():
        return []
    names: List[str] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if _INTERNAL_COLLECTION_DIR_RE.search(child.name):
            continue
        if (child / "manifest.json").is_file():
            names.append(child.name)
    return names


def _resolve_existing_engine(
    engine: Optional[str],
    collection_names: List[str],
    collections_path: Optional[str],
) -> EngineVersion:
    """Resolve the engine for an existing-collection op.

    ``engine is None`` → route to the default engine directly (no detection I/O),
    so v1's per-collection behavior (omit corrupt collections in status/inspect,
    handle corrupt collections in remove) is preserved byte-for-byte on the
    default path.

    An explicit ``engine`` is validated against every touched collection's
    detected version *before any I/O*; a conflict raises ``EngineMismatchError``.
    """
    if engine is None:
        return _DEFAULT_ENGINE

    requested = _validate_engine(engine)
    base = _collections_base(collections_path)
    for name in collection_names:
        collection_path = base / name
        if not (collection_path / "manifest.json").exists():
            # Non-existent collection: nothing to conflict with. The op's own
            # not-found handling still applies once we route.
            continue
        detected = detect_engine_version(collection_path)
        if detected != requested:
            raise EngineMismatchError(name, found=detected, requested=requested)
    return requested


# --- routed callables (byte-identical v1 signatures + ``engine``) -------------


def create(
    configs: List[Any],
    *,
    engine: Optional[str] = None,
    use_cache: bool = True,
    force: bool = False,
    phased_progress: Any = None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
    connector_factory: Any,
    cache_decorator_factory: Any = None,
) -> None:
    """Create collections with the selector-chosen engine (R3). ``engine=None``
    defaults to ``"1"``."""
    version = _validate_engine(engine or _DEFAULT_ENGINE)
    _engine_impl(version).create(
        configs,
        use_cache=use_cache,
        force=force,
        phased_progress=phased_progress,
        collections_path=collections_path,
        caches_path=caches_path,
        connector_factory=connector_factory,
        cache_decorator_factory=cache_decorator_factory,
    )


def update(
    configs: List[Any],
    phased_progress: Any = None,
    collections_path: Optional[str] = None,
    *,
    manifest_factory: Any,
    engine: Optional[str] = None,
) -> None:
    """Update collections, routing per the collection's engine (R2)."""
    names = [getattr(cfg, "name", cfg) for cfg in configs]
    version = _resolve_existing_engine(engine, names, collections_path)
    _engine_impl(version).update(
        configs,
        phased_progress=phased_progress,
        collections_path=collections_path,
        manifest_factory=manifest_factory,
    )


def clear(
    collection_names: List[str],
    collections_path: Optional[str] = None,
    *,
    engine: Optional[str] = None,
) -> None:
    """Clear (delete) collections, routing per the collection's engine (R2)."""
    version = _resolve_existing_engine(engine, collection_names, collections_path)
    _engine_impl(version).clear(collection_names, collections_path=collections_path)


def collection_exists(
    name: str,
    collections_path: Optional[str] = None,
    *,
    engine: Optional[str] = None,
) -> bool:
    """Raw on-disk existence check, routing per the collection's engine (R2)."""
    version = _resolve_existing_engine(engine, [name], collections_path)
    result: bool = _engine_impl(version).collection_exists(
        name, collections_path=collections_path
    )
    return result


def search(
    query: str,
    configs: Optional[List[Any]] = None,
    max_chunks: Optional[int] = None,
    max_docs: Optional[int] = None,
    score_threshold: Optional[float] = None,
    include_full_text: bool = False,
    include_all_chunks: bool = False,
    include_matched_chunks: bool = False,
    collections_path: Optional[str] = None,
    *,
    engine: Optional[str] = None,
) -> Dict[str, Any]:
    """Search collections, routing per the collection's engine (R2).

    ``configs=None`` (all collections) routes to the single available engine;
    the multi-engine merge lands in a later unit.
    """
    if engine is None:
        version: EngineVersion = _DEFAULT_ENGINE
    else:
        names = (
            [getattr(cfg, "name", cfg) for cfg in configs]
            if configs
            else _existing_collection_names(collections_path)
        )
        version = _resolve_existing_engine(engine, names, collections_path)
    result: Dict[str, Any] = _engine_impl(version).search(
        query,
        configs=configs,
        max_chunks=max_chunks,
        max_docs=max_docs,
        score_threshold=score_threshold,
        include_full_text=include_full_text,
        include_all_chunks=include_all_chunks,
        include_matched_chunks=include_matched_chunks,
        collections_path=collections_path,
    )
    return result


def status(
    collection_names: Optional[List[str]] = None,
    *,
    include_index_size: bool = False,
    collections_path: Optional[str] = None,
    engine: Optional[str] = None,
) -> List[Any]:
    """Collection status, routing per the collection's engine (R2)."""
    names = collection_names or []
    version = _resolve_existing_engine(engine, names, collections_path)
    result: List[Any] = _engine_impl(version).status(
        collection_names=collection_names,
        include_index_size=include_index_size,
        collections_path=collections_path,
    )
    return result


def inspect(
    collection_names: Optional[List[str]] = None,
    *,
    include_index_size: bool = False,
    collections_path: Optional[str] = None,
    engine: Optional[str] = None,
) -> List[Any]:
    """Detailed collection inspection, routing per the collection's engine (R2)."""
    names = collection_names or []
    version = _resolve_existing_engine(engine, names, collections_path)
    result: List[Any] = _engine_impl(version).inspect(
        collection_names=collection_names,
        include_index_size=include_index_size,
        collections_path=collections_path,
    )
    return result


def __getattr__(name: str) -> Any:
    """Lazily re-export the shared v1 types (mirrors the v1 facade pattern)."""
    if name in _SHARED_TYPES:
        from indexed.core.v1.engine import services

        return getattr(services, name)
    raise AttributeError(f"module 'indexed.core.engine' has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(_EXPORTS)


if TYPE_CHECKING:  # help type-checkers/IDEs see the re-exported names
    from indexed.core.v1.engine.services import (  # noqa: F401
        CollectionInfo,
        CollectionStatus,
        InspectService,
        PhasedProgressCallback,
        SearchService,
        SourceConfig,
    )


__all__ = sorted(_EXPORTS)
