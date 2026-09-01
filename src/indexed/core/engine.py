"""Version-dispatching core engine facade (core-v2/1).

The app (CLI/MCP) imports collection/search/inspect operations and the shared
models from ``indexed.core.engine`` — never from ``core.v1.engine`` (or a future
``core.v2.engine``) directly. This facade re-exports the exact 13-name v1 surface
with identical signatures and adds a thin per-collection routing layer:

- **create** chooses the engine from an already-resolved selector (R3) for a
  genuinely new collection name.
- **any op touching an existing collection** — ``create`` included — resolves
  the engine FROM the collection's on-disk ``version`` marker (R2); an explicit
  conflicting ``engine`` raises ``EngineMismatchError`` before any I/O.

Only v1 exists today: unmarked and ``version: "1"`` collections route to v1;
``--engine v2`` (``engine="2"``) is detected and fails cleanly until a later unit
implements it. Resolution stays lazy — no heavy imports at module top, mirroring
the v1 facade — so CLI startup stays <1s and no LlamaIndex import happens here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from indexed.config.errors import ConfigurationError
from indexed.core.errors import (
    EngineMismatchError,
    UnknownEngineVersionError,
)
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

# Same 13-name surface as ``core.v1.engine._EXPORTS`` (asserted equal in tests).
_EXPORTS = _SHARED_TYPES | _ROUTED

_DEFAULT_ENGINE: EngineVersion = "1"
_SUPPORTED_ENGINES = ("1", "2")

# Non-collection dirs excluded from discovery: transient build-aside/rollback
# dirs the durable-create path leaves on disk (``.tmp-``/``.trash-``, exactly as
# v1 does) AND a migration's retained ``<name>.v1-backup`` (a complete v1
# collection kept until ``--purge-backup``) — otherwise the backup would surface
# as a phantom, duplicating the migrated collection's hits. Kept byte-identical
# to ``core.v2._common._INTERNAL_COLLECTION_DIR_RE`` so both discovery sites agree.
_INTERNAL_COLLECTION_DIR_RE = re.compile(r"\.(?:tmp|trash)-\d+|\.v1-backup$")


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

    The single indirection every routed op dispatches through. core-v2/2c makes
    the ``"2"`` branch real by importing the v2 engine services here (a
    function-local import — the v2 services module itself keeps LlamaIndex
    imports function-local, so this stays cheap and CLI startup stays <1s).
    """
    if version == "1":
        from indexed.core.v1.engine import services as _v1_services

        return _v1_services
    if version == "2":
        from indexed.core.v2 import services as _v2_services

        return _v2_services
    # ``version`` is a validated ``EngineVersion`` before it reaches here, so this
    # branch is unreachable — raise an explicit error rather than ``raise <str>``
    # (which would itself be a ``TypeError``) to make the invariant obvious.
    raise ConfigurationError(  # pragma: no cover - unreachable, kept explicit
        f"No engine implementation registered for version {version!r}"
    )


def _collections_base(collections_path: Optional[str]) -> Path:
    """Resolve the collections directory exactly as the v1 services do."""
    if collections_path:
        return Path(collections_path)
    from indexed.core.v1.config_models import get_default_collections_path

    return Path(get_default_collections_path())


def _existing_collection_names(collections_path: Optional[str]) -> List[str]:
    """List existing collection names for engine detection.

    This intentionally mirrors v1's manifest-based discovery + the
    ``_INTERNAL_COLLECTION_DIR_RE`` tmp/trash exclusion (see
    ``search_service``/``inspect_service._discover_collections``). v1 exposes
    only *private* ``_discover_collections`` methods on the service classes, so
    there is no public helper to delegate to without instantiating a service; the
    small reimplementation here is a deliberate residual for a future
    consolidation, not a new cross-layer dependency.
    """
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
    """Resolve the engine for an existing-collection op — manifest-authoritative
    on BOTH the default and the explicit path (R2).

    For every touched collection whose ``manifest.json`` exists, the on-disk
    ``version`` marker is read:

    - A readable manifest with an *unknown* marker raises
      ``UnknownEngineVersionError`` (R1: fail loud — default OR explicit path,
      never a silent v1 fallback), leaving the collection untouched.
    - A missing/corrupt/unreadable manifest is *tolerated*: detection raises a
      collection-level ``ValueError`` which is swallowed here so v1's own
      handling of corrupt collections is preserved byte-for-byte (status/inspect
      omit them; remove deletes them) — the R6 concern, handled without
      sacrificing R1.

    With an explicit ``engine`` a readable marker that disagrees raises
    ``EngineMismatchError`` before any op I/O. On the default path the detected
    version is returned when the readable collections agree, else the default
    engine when none carry a readable marker.
    """
    requested: Optional[EngineVersion] = (
        _validate_engine(engine) if engine is not None else None
    )
    base = _collections_base(collections_path)
    detected_versions: set[EngineVersion] = set()
    for name in collection_names:
        collection_path = base / name
        if not (collection_path / "manifest.json").exists():
            # Non-existent collection: nothing to detect/conflict with. The op's
            # own not-found handling still applies once we route.
            continue
        try:
            detected = detect_engine_version(collection_path)
        except UnknownEngineVersionError:
            # Readable manifest, unsupported marker → fail loud on either path.
            raise
        except ValueError:
            # Missing/corrupt/unreadable manifest → fall through to v1's own
            # corrupt-collection handling. Do not raise from the facade (R6).
            continue
        if requested is not None and detected != requested:
            raise EngineMismatchError(name, found=detected, requested=requested)
        detected_versions.add(detected)

    if requested is not None:
        return requested
    if len(detected_versions) == 1:
        return next(iter(detected_versions))
    # No readable marker among the touched collections, or (unreachable while
    # only v1 exists) a mixed v1/v2 set — the multi-engine split/merge lands in
    # core-v2/2. Route to the default engine for now.
    return _DEFAULT_ENGINE


# --- per-engine grouping for list-all / mixed-engine ops (core-v2/2c) ---------


def _group_names_by_engine(
    collection_names: List[str],
    collections_path: Optional[str],
) -> "dict[EngineVersion, List[str]]":
    """Split requested names by their on-disk engine, preserving request order.

    Same per-name detection semantics as ``_resolve_existing_engine`` on the
    default path (R2/R6/R1):

    - readable ``version`` marker → that engine's group;
    - missing/corrupt/unreadable manifest → the DEFAULT engine's group (so v1's
      own not-found/corrupt handling still applies — status/inspect omit them,
      clear deletes them);
    - readable *unknown* marker → ``UnknownEngineVersionError`` (fail loud).

    Group insertion order follows first appearance, so concatenated results keep
    a stable order.
    """
    base = _collections_base(collections_path)
    groups: "dict[EngineVersion, List[str]]" = {}
    for name in collection_names:
        collection_path = base / name
        if not (collection_path / "manifest.json").exists():
            version: EngineVersion = _DEFAULT_ENGINE
        else:
            try:
                version = detect_engine_version(collection_path)
            except UnknownEngineVersionError:
                raise
            except ValueError:
                version = _DEFAULT_ENGINE
        groups.setdefault(version, []).append(name)
    return groups


def _coerce_status(version: EngineVersion, raw: Any) -> Any:
    """v1 returns ``CollectionStatus`` objects already; v2 returns field-keyed
    dicts — build the shared dataclass from them (the facade may import v1)."""
    if version != "2":
        return raw
    from indexed.core.v1.engine.services import CollectionStatus

    return [CollectionStatus(**d) for d in raw]


def _coerce_info(version: EngineVersion, raw: Any) -> Any:
    """As ``_coerce_status`` but for the detailed ``CollectionInfo`` surface."""
    if version != "2":
        return raw
    from indexed.core.v1.engine.services import CollectionInfo

    return [CollectionInfo(**d) for d in raw]


def _configs_for_group(
    configs: Optional[List[Any]], group_names: List[str]
) -> List[Any]:
    """The per-engine subset of ``configs`` for a search group.

    With explicit ``configs`` → the configs whose collection is in this group.
    With ``configs is None`` (all collections) → minimal stub configs (as v1's
    own auto-discovery builds), so each engine searches ONLY its own group and
    never auto-discovers the other engine's collections.
    """
    if configs is not None:
        wanted = set(group_names)
        return [cfg for cfg in configs if getattr(cfg, "name", cfg) in wanted]
    from indexed.core.v1.engine.services import SourceConfig

    return [
        SourceConfig(name=name, type="localFiles", base_url_or_path="", indexer=None)
        for name in group_names
    ]


# --- engine-aware diagnostics (R13) -------------------------------------------


@dataclass(frozen=True)
class EngineDescriptor:
    """Engine identity for one collection — the R13 diagnostics view.

    A lightweight, engine-agnostic record the app layer renders in
    inspect/status output so a user can always tell which engine owns which
    collection. Built by the FACADE (which may read a v2 manifest lazily); the
    CLI imports it from ``indexed.core.engine``, never from ``core.v2`` directly.
    ``embedding_*``/``vector_store`` are populated for v2 (from the manifest
    engine block) and best-effort for v1.
    """

    name: str
    engine_version: str  # "1" | "2"
    embedding_model: Optional[str] = None
    embedding_provider: Optional[str] = None
    vector_store: Optional[str] = None


def engine_descriptors(
    collection_names: Optional[List[str]] = None,
    *,
    collections_path: Optional[str] = None,
) -> List[EngineDescriptor]:
    """Per-collection engine identity for diagnostics (R13).

    For each readable collection returns its engine version and — for v2 — the
    recorded embedding model/provider and vector store (read from the v2
    manifest engine block via a lazy ``core.v2`` import; no LlamaIndex). v1
    collections report ``engine_version="1"`` with best-effort model/store from
    the v1 manifest (``vector_store="faiss"``; the indexer name as the model).

    Collections the facade can't classify — missing/corrupt manifest, or an
    unknown ``version`` marker — are OMITTED (matching v1 inspect/status). This
    is a DISPLAY helper only, so it never fails loud: the operational ops
    (search/inspect/status/update/clear) already reject unknown markers via
    ``_group_names_by_engine``/``_resolve_existing_engine``.
    """
    base = _collections_base(collections_path)
    names = collection_names or _existing_collection_names(collections_path)
    out: List[EngineDescriptor] = []
    for name in names:
        collection_path = base / name
        if not (collection_path / "manifest.json").exists():
            continue
        try:
            version = detect_engine_version(collection_path)
        except (ValueError, UnknownEngineVersionError):
            # Corrupt/unreadable or unknown marker → omit (display never crashes).
            continue
        descriptor = (
            _v2_descriptor(name, collection_path)
            if version == "2"
            else _v1_descriptor(name, collection_path)
        )
        if descriptor is not None:
            out.append(descriptor)
    return out


def _v2_descriptor(name: str, collection_path: Path) -> Optional[EngineDescriptor]:
    """Read the v2 manifest engine block (lazy ``core.v2`` import, no LlamaIndex)."""
    from indexed.core.v2.manifest import V2Manifest

    try:
        raw = json.loads(
            (collection_path / "manifest.json").read_text(encoding="utf-8")
        )
        manifest = V2Manifest.from_disk(raw)
    except Exception:
        return None
    return EngineDescriptor(
        name=name,
        engine_version="2",
        embedding_model=manifest.engine.embedding.model,
        embedding_provider=manifest.engine.embedding.provider,
        vector_store=manifest.engine.vector_store,
    )


def _v1_descriptor(name: str, collection_path: Path) -> EngineDescriptor:
    """Best-effort v1 identity (do not over-invest — key requirement is v1 vs v2).

    v1 always embeds with FAISS + sentence-transformers; the manifest's first
    indexer name is the closest thing v1 records to an embedding-model id.
    """
    model: Optional[str] = None
    try:
        raw = json.loads(
            (collection_path / "manifest.json").read_text(encoding="utf-8")
        )
        indexers = raw.get("indexers") or []
        if indexers and isinstance(indexers[0], dict):
            model = indexers[0].get("name")
    except Exception:
        model = None
    return EngineDescriptor(
        name=name,
        engine_version="1",
        embedding_model=model,
        embedding_provider=None,
        vector_store="faiss",
    )


# --- migration (v1 -> v2; facade-exposed so the CLI never imports core.v2) ----


def migrate(
    name: str,
    *,
    collections_path: Optional[str] = None,
    dry_run: bool = False,
    from_source: bool = False,
    purge_backup: bool = False,
    manifest_factory: Any = None,
) -> Any:
    """Migrate a v1 collection to v2 (R7).

    Exposed THROUGH the facade so the CLI ``migrate`` command imports only
    ``indexed.core.engine`` (above-facade rule) — the service impl lives in
    ``indexed.core.v2.migration`` (import-legal under ``core/v2``). Migration is
    always a v1->v2 build operation (offline by default, or ``--from-source`` via
    the supplied ``manifest_factory``); the service confirms the source IS a v1
    collection and fails loud otherwise (``CoreV2Error``). Returns a
    ``MigrationResult`` the CLI renders (counts, target model/store, backup path).
    """
    from indexed.core.v2 import migration

    return migration.migrate(
        name,
        collections_path=collections_path,
        dry_run=dry_run,
        from_source=from_source,
        purge_backup=purge_backup,
        manifest_factory=manifest_factory,
    )


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
    """Create collections with the selector-chosen engine (R3/R2). A name that
    already exists on disk is resolved like the other routed ops: the manifest
    ``version`` is authoritative, and an explicit conflicting ``engine`` raises
    ``EngineMismatchError`` before any I/O. ``engine=None`` defaults to ``"1"``
    only for names with no existing collection."""
    names = [getattr(cfg, "name", cfg) for cfg in configs]
    version = _resolve_existing_engine(engine, names, collections_path)
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
    """Raw on-disk existence probe — engine-agnostic on the default path.

    Existence is a filesystem question answered identically by either engine, so
    ``engine=None`` routes straight to the default engine WITHOUT detection: it
    must never fail loud (e.g. on a readable unknown marker) — a corrupt or
    future-versioned collection still "exists". An explicit ``engine`` is still
    validated against the collection's marker for consistency with the other ops.
    """
    if engine is None:
        version: EngineVersion = _DEFAULT_ENGINE
    else:
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
    rerank: Optional[bool] = None,
) -> Dict[str, Any]:
    """Search collections, routing per the collection's engine (R2).

    ``configs=None`` (all collections) enumerates on-disk collections. A mixed
    v1/v2 set is split per engine and the per-collection result dicts are MERGED
    (union of collection-keyed dicts, each in its engine's native score units;
    cross-engine ranking is core-v2/6). An explicit conflicting ``engine`` still
    raises ``EngineMismatchError`` before any I/O. ``rerank`` overrides
    ``[core.v2.rerank] enabled`` for this call; it is forwarded only when
    routing to the v2 impl — v1 has no rerank concept and no such param.
    """

    def _run(version: EngineVersion, cfgs: Optional[List[Any]]) -> Dict[str, Any]:
        rerank_kwargs = (
            {"rerank": rerank} if version == "2" and rerank is not None else {}
        )
        out: Dict[str, Any] = _engine_impl(version).search(
            query,
            configs=cfgs,
            max_chunks=max_chunks,
            max_docs=max_docs,
            score_threshold=score_threshold,
            include_full_text=include_full_text,
            include_all_chunks=include_all_chunks,
            include_matched_chunks=include_matched_chunks,
            collections_path=collections_path,
            **rerank_kwargs,
        )
        return out

    names = (
        [getattr(cfg, "name", cfg) for cfg in configs]
        if configs
        else _existing_collection_names(collections_path)
    )
    if engine is not None:
        return _run(_resolve_existing_engine(engine, names, collections_path), configs)

    groups = _group_names_by_engine(names, collections_path)
    if len(groups) <= 1:
        return _run(next(iter(groups), _DEFAULT_ENGINE), configs)

    merged: Dict[str, Any] = {}
    for grp_version, grp_names in groups.items():
        merged.update(_run(grp_version, _configs_for_group(configs, grp_names)))
    return merged


def status(
    collection_names: Optional[List[str]] = None,
    *,
    include_index_size: bool = False,
    collections_path: Optional[str] = None,
    engine: Optional[str] = None,
) -> List[Any]:
    """Collection status, routing/merging per the collection's engine (R2)."""

    def _run(version: EngineVersion, names: Optional[List[str]]) -> Any:
        return _coerce_status(
            version,
            _engine_impl(version).status(
                collection_names=names,
                include_index_size=include_index_size,
                collections_path=collections_path,
            ),
        )

    resolved = collection_names or _existing_collection_names(collections_path)
    if engine is not None:
        return _run(
            _resolve_existing_engine(engine, resolved, collections_path),
            collection_names,
        )

    groups = _group_names_by_engine(resolved, collections_path)
    if len(groups) <= 1:
        return _run(next(iter(groups), _DEFAULT_ENGINE), collection_names)

    out: List[Any] = []
    for grp_version, grp_names in groups.items():
        out.extend(_run(grp_version, grp_names))
    return out


def inspect(
    collection_names: Optional[List[str]] = None,
    *,
    include_index_size: bool = False,
    collections_path: Optional[str] = None,
    engine: Optional[str] = None,
) -> List[Any]:
    """Detailed collection inspection, routing/merging per engine (R2)."""

    def _run(version: EngineVersion, names: Optional[List[str]]) -> Any:
        return _coerce_info(
            version,
            _engine_impl(version).inspect(
                collection_names=names,
                include_index_size=include_index_size,
                collections_path=collections_path,
            ),
        )

    resolved = collection_names or _existing_collection_names(collections_path)
    if engine is not None:
        return _run(
            _resolve_existing_engine(engine, resolved, collections_path),
            collection_names,
        )

    groups = _group_names_by_engine(resolved, collections_path)
    if len(groups) <= 1:
        return _run(next(iter(groups), _DEFAULT_ENGINE), collection_names)

    out: List[Any] = []
    for grp_version, grp_names in groups.items():
        out.extend(_run(grp_version, grp_names))
    return out


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
