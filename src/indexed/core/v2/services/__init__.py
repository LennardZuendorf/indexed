"""v2 engine service surface (core-v2/2c).

Exposes the same 7 operation names the version-dispatching facade
(``indexed.core.engine._engine_impl``) calls on an engine —
``create, update, clear, collection_exists, search, status, inspect`` — with
signatures matching v1's services (v1-surface-map §1). LlamaIndex is imported
only inside ``ingestion``/``retrieval`` (function-local there), so importing
this module — which is exactly what ``_engine_impl("2")`` does — stays cheap
and never pulls LlamaIndex at module top.

``status``/``inspect`` return field-keyed **dicts** (RESOLVED design): the
shared ``CollectionStatus``/``CollectionInfo`` dataclasses live under
``core.v1`` (frozen) which ``core/v2`` may not import, so the FACADE constructs
them from these dicts. All LlamaIndex exceptions are wrapped at this boundary
into ``IndexedError`` subtypes (``CoreV2Error``); upstream has no stable
exception hierarchy (tech.md §Errors).
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from loguru import logger

from indexed.config.errors import IndexedError
from indexed.core.errors import CoreV2Error
from indexed.core.v2._common import collections_base, discover_v2_collections

# ── exception boundary ────────────────────────────────────────────────────


@contextmanager
def _wrap(operation: str) -> Iterator[None]:
    """Re-raise any upstream (LlamaIndex) failure as a ``CoreV2Error``.

    Project errors (``IndexedError`` subtypes — e.g. ``UnknownVectorStoreError``)
    pass through unchanged so their actionable messages/exit codes survive.
    """
    try:
        yield
    except IndexedError:
        raise
    except Exception as exc:
        raise CoreV2Error(f"v2 {operation} failed: {exc}") from exc


# ── create / search (thin wrappers over ingestion / retrieval) ─────────────


def create(
    configs: List[Any],
    *,
    use_cache: bool = True,
    force: bool = False,
    phased_progress: Any = None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
    connector_factory: Any,
    cache_decorator_factory: Any = None,
) -> None:
    from indexed.core.v2 import ingestion

    with _wrap("create"):
        ingestion.create(
            configs,
            use_cache=use_cache,
            force=force,
            phased_progress=phased_progress,
            collections_path=collections_path,
            caches_path=caches_path,
            connector_factory=connector_factory,
            cache_decorator_factory=cache_decorator_factory,
        )


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
) -> Dict[str, Any]:
    from indexed.core.v2 import retrieval

    with _wrap("search"):
        return retrieval.search(
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


# ── update (incremental; core-v2/3) ────────────────────────────────────────


def update(
    configs: List[Any],
    phased_progress: Any = None,
    collections_path: Optional[str] = None,
    *,
    manifest_factory: Any = None,
) -> None:
    """Incrementally update v2 collections (only new/changed docs re-embedded).

    Thin wrapper over :func:`indexed.core.v2.ingestion.update`; all LlamaIndex
    exceptions are wrapped at this boundary into ``CoreV2Error`` (typed
    ``IndexedError``s pass through with their actionable messages).
    """
    from indexed.core.v2 import ingestion

    with _wrap("update"):
        ingestion.update(
            configs,
            phased_progress=phased_progress,
            collections_path=collections_path,
            manifest_factory=manifest_factory,
        )


# ── clear / collection_exists (filesystem ops) ─────────────────────────────


def clear(collection_names: List[str], collections_path: Optional[str] = None) -> None:
    """Delete v2 collection directories by name."""
    import shutil

    base = collections_base(collections_path)
    for name in collection_names:
        target = base / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            if target.exists():
                logger.warning(f"clear: directory not fully removed: {str(target)!r}")


def collection_exists(name: str, collections_path: Optional[str] = None) -> bool:
    """True when a v2 collection dir with a ``manifest.json`` is present."""
    base = collections_base(collections_path)
    coll = base / name
    return coll.is_dir() and (coll / "manifest.json").is_file()


# ── status / inspect (field-keyed dicts; facade builds the dataclasses) ────


def status(
    collection_names: Optional[List[str]] = None,
    *,
    include_index_size: bool = False,
    collections_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Per-collection ``CollectionStatus``-shaped dicts (OMITs unreadable ones)."""
    del include_index_size  # v2 vector-count sizing lands with R13 display (2d)
    base = collections_base(collections_path)
    names = collection_names or discover_v2_collections(base)
    out: List[Dict[str, Any]] = []
    for name in names:
        manifest = _read_manifest(base, name)
        if manifest is None:
            continue
        out.append(
            {
                "name": name,
                "number_of_documents": manifest.number_of_documents,
                "number_of_chunks": manifest.number_of_chunks,
                "updated_time": manifest.updated_time,
                "last_modified_document_time": manifest.last_modified_document_time,
                # The v2 embedding model stands in for v1's indexer list: it is
                # the closest analog and — crucially for R4 surface parity — the
                # CLI search path skips any collection whose ``indexers`` is empty
                # (search.py builds its per-collection SourceConfig from
                # ``indexers[0]``). A one-element list keeps ``search --collection
                # <v2>`` working exactly like v1.
                "indexers": [manifest.engine.embedding.model],
                "index_size": None,
                "source_type": manifest.reader.type,
                "relative_path": _relative_path(base / name),
                "disk_size_bytes": _dir_size(base / name),
            }
        )
    return out


def inspect(
    collection_names: Optional[List[str]] = None,
    *,
    include_index_size: bool = False,
    collections_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Per-collection ``CollectionInfo``-shaped dicts (OMITs unreadable ones)."""
    del include_index_size
    base = collections_base(collections_path)
    names = collection_names or discover_v2_collections(base)
    out: List[Dict[str, Any]] = []
    for name in names:
        manifest = _read_manifest(base, name)
        if manifest is None:
            continue
        out.append(
            {
                "name": name,
                "source_type": manifest.reader.type,
                "number_of_documents": manifest.number_of_documents,
                "number_of_chunks": manifest.number_of_chunks,
                "relative_path": _relative_path(base / name),
                "disk_size_bytes": _dir_size(base / name),
                "index_size_bytes": None,
                "created_time": manifest.created_time,
                "updated_time": manifest.updated_time,
                "last_modified_document_time": manifest.last_modified_document_time,
                # See ``status`` — the embedding model is v2's indexer analog.
                "indexers": [manifest.engine.embedding.model],
            }
        )
    return out


# ── helpers ────────────────────────────────────────────────────────────────


def _read_manifest(base: Path, name: str) -> Any:
    """Load a v2 manifest, or ``None`` (logged + omitted) when unreadable.

    Mirrors v1 inspect/status: a missing/corrupt/non-v2 manifest is OMITTED,
    never zero-filled.
    """
    from indexed.core.v2.manifest import V2Manifest

    manifest_path = base / name / "manifest.json"
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        return V2Manifest.from_disk(raw)
    except Exception as exc:
        logger.error(f"Error reading v2 manifest for collection {name}: {exc}")
        return None


def _relative_path(abs_path: Path) -> str:
    try:
        return os.path.relpath(abs_path, start=os.getcwd())
    except ValueError:  # pragma: no cover - different drive on Windows
        return str(abs_path)


def _dir_size(base_dir: Path) -> int:
    total = 0
    for path in base_dir.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    return total


__all__ = [
    "clear",
    "collection_exists",
    "create",
    "inspect",
    "search",
    "status",
    "update",
]
