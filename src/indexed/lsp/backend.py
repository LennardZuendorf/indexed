"""The engine seam the LSP server talks to.

One place where the server is wired to ``indexed.core.engine``: collection
status, collection-ownership of a source file, and one-collection search. The
server itself takes a backend, so its dispatch is testable without an engine,
an embedding model or a FAISS index.

Cost discipline: a language server is called while a human types. ``statuses()``
enumerates every collection's manifest, so it is cached for a short window, and
a hover/definition request searches the ONE collection that owns the file
instead of every collection on disk.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, get_args

from indexed.protocols.models import SourceConfig

#: Derived once from the SourceConfig Literal so the set stays in sync with the
#: model (same derivation as ``indexed.mcp.tools``).
_ALLOWED_SOURCE_TYPES: frozenset[str] = frozenset(
    get_args(SourceConfig.model_fields["type"].annotation)
)

#: How long a status snapshot is reused. Long enough that a burst of keystrokes
#: reads manifests once, short enough that a reindex shows up promptly.
STATUS_TTL_SECONDS = 2.0


class KnowledgeBackend:
    """Collections, ownership and search, resolved from the core facade."""

    def __init__(
        self,
        collections_path: str,
        *,
        search_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        status_fn: Optional[Callable[..., List[Any]]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.collections_path = str(collections_path)
        self._search_fn = search_fn
        self._status_fn = status_fn
        self._clock = clock
        self._statuses: Optional[List[Any]] = None
        self._statuses_at = 0.0
        self._base_paths: Dict[str, Tuple[Optional[str], float]] = {}
        self._hash_cache: Dict[
            str, Tuple[Tuple[int, int], Optional[Dict[str, str]]]
        ] = {}

    # -- engine accessors (lazy so `indexed lsp` startup stays cheap) ---------

    @property
    def search_fn(self) -> Callable[..., Dict[str, Any]]:
        if self._search_fn is None:
            from indexed.core.engine import search as engine_search

            self._search_fn = engine_search
        return self._search_fn

    @property
    def status_fn(self) -> Callable[..., List[Any]]:
        if self._status_fn is None:
            from indexed.core.engine import status as engine_status

            self._status_fn = engine_status
        return self._status_fn

    # -- collections ---------------------------------------------------------

    def statuses(self) -> List[Any]:
        """Every readable collection's status, cached for ``STATUS_TTL_SECONDS``."""
        now = self._clock()
        if self._statuses is not None and now - self._statuses_at < STATUS_TTL_SECONDS:
            return self._statuses
        self._statuses = list(self.status_fn(collections_path=self.collections_path))
        self._statuses_at = now
        return self._statuses

    def status_for(self, name: str) -> Optional[Any]:
        """One collection's status, without refreshing the whole snapshot."""
        for status in self.statuses():
            if getattr(status, "name", None) == name:
                return status
        return None

    def base_path(self, collection: str) -> Optional[str]:
        """The absolute source root of a collection, from its manifest ``reader``.

        Returns ``None`` for sources that have no filesystem root (Jira,
        Confluence, Outline) or an unreadable manifest — the caller then simply
        cannot claim ownership of a local file. Cached like ``statuses()``: a
        manifest that appears (or is repointed) after startup must not stay
        invisible until the editor restarts.
        """
        now = self._clock()
        cached = self._base_paths.get(collection)
        if cached is not None and now - cached[1] < STATUS_TTL_SECONDS:
            return cached[0]
        base: Optional[str] = None
        manifest_path = Path(self.collections_path) / collection / "manifest.json"
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        reader = raw.get("reader") if isinstance(raw, dict) else None
        candidate = reader.get("basePath") if isinstance(reader, dict) else None
        if isinstance(candidate, str) and candidate:
            base = os.path.normpath(os.path.abspath(candidate))
        self._base_paths[collection] = (base, now)
        return base

    def indexed_digest(self, collection: str, path: str) -> Optional[str]:
        """The content digest the last indexing run recorded for ``path``.

        Read from the change tracker's ``state.json`` beside the collection
        manifest, which the file connector rewrites after every index/update
        run. It is the *only* per-file fact about the index that can be read
        without loading the store, and it is exactly what the indexer itself
        compares against (``utils.fingerprint.file_fingerprint``), so the LSP
        and the indexer can never disagree about a file.

        ``None`` means **unknown** — no state file (never indexed, or migrated
        from v1), an unreadable manifest, or a file the run did not cover — and
        a caller must treat it as "no opinion", never as "unchanged".
        """
        hashes = self._recorded_hashes(collection)
        if hashes is None:
            return None
        base = self.base_path(collection)
        if not base:
            return None
        target = os.path.normpath(os.path.abspath(path))
        digest = hashes.get(os.path.relpath(target, base))
        return digest if isinstance(digest, str) else None

    def _recorded_hashes(self, collection: str) -> Optional[Dict[str, str]]:
        """``state.json``'s ``file_hashes``, cached against its own mtime+size.

        Parsed once per version of the file: a state file lists every indexed
        file, and a burst of saves must not re-parse it per keystroke. Keyed on
        ``(st_mtime_ns, st_size)`` so a reindex is picked up immediately instead
        of after a timer.
        """
        state_path = Path(self.collections_path) / collection / "state.json"
        try:
            stat = state_path.stat()
        except OSError:
            return None
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = self._hash_cache.get(collection)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        hashes: Optional[Dict[str, str]] = None
        try:
            raw = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = None
        if isinstance(raw, dict):
            candidate = raw.get("file_hashes")
            if isinstance(candidate, dict):
                hashes = {
                    key: value
                    for key, value in candidate.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
        self._hash_cache[collection] = (stamp, hashes)
        return hashes

    def collection_for_path(self, path: str) -> Optional[Any]:
        """The collection whose source root contains ``path`` (longest match wins)."""
        target = os.path.normpath(os.path.abspath(path))
        best: Optional[Any] = None
        best_len = -1
        for status in self.statuses():
            base = self.base_path(getattr(status, "name", ""))
            if not base:
                continue
            if target == base or target.startswith(base + os.sep):
                if len(base) > best_len:
                    best, best_len = status, len(base)
        return best

    # -- search --------------------------------------------------------------

    def search(
        self,
        query: str,
        collection: Optional[str] = None,
        *,
        max_docs: int = 10,
        max_chunks: int = 30,
    ) -> Dict[str, Any]:
        """Run one semantic search, optionally scoped to a single collection.

        ``configs=None`` would enumerate and recover EVERY collection on every
        call; a named collection is resolved through its status instead, which
        is both cheaper and keeps a half-recovered collection out of the path
        of a keystroke (issue #126).
        """
        configs = None
        if collection is not None:
            status = self.status_for(collection)
            if status is None:
                return {}
            configs = [self._source_config(status)]
        return self.search_fn(
            query,
            configs=configs,
            max_docs=max_docs,
            max_chunks=max_chunks,
            include_matched_chunks=True,
            collections_path=self.collections_path,
        )

    @staticmethod
    def _source_config(status: Any) -> SourceConfig:
        raw_type = getattr(status, "source_type", None)
        # Search consumes only name/indexer, but the field is a Literal — keep an
        # unrecognised on-disk type from raising at the model boundary.
        source_type = raw_type if raw_type in _ALLOWED_SOURCE_TYPES else "localFiles"
        indexers = getattr(status, "indexers", None) or []
        return SourceConfig(
            name=getattr(status, "name", ""),
            type=source_type,
            base_url_or_path="",
            indexer=indexers[0] if indexers else None,
        )


__all__ = ["STATUS_TTL_SECONDS", "KnowledgeBackend"]
