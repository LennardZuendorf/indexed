"""Core-engine error types for version detection and routing (core-v2/1).

All inherit the project's :class:`~indexed.config.errors.IndexedError` (via the
:class:`CoreError` base) so the existing CLI exit-code mapping and MCP error
envelopes keep working unchanged.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from indexed.config.errors import IndexedError


class CoreError(IndexedError):
    """Base for core-engine detection/routing errors."""


class EngineMismatchError(CoreError):
    """An explicit engine selector conflicts with a collection's detected engine.

    Raised before any I/O so a mismatched ``--engine`` can never touch a
    collection built by a different engine.
    """

    def __init__(self, collection: str, *, found: str, requested: str) -> None:
        self.collection = collection
        self.found = found
        self.requested = requested
        super().__init__(
            f"Collection '{collection}' is a v{found} collection "
            f"but engine v{requested} was requested. "
            f"Re-run without --engine, use --engine v{found}, or migrate it: "
            f"indexed index migrate {collection}"
        )


class UnknownEngineVersionError(CoreError):
    """A manifest's ``version`` marker is an unsupported value.

    Fails loud (R1) and leaves the collection untouched.
    """

    def __init__(
        self,
        *,
        found: object,
        path: object | None = None,
        supported: Sequence[str] = ("1", "2"),
    ) -> None:
        self.found = found
        self.path = path
        self.supported = tuple(supported)
        location = f" at '{path}'" if path is not None else ""
        supported_str = ", ".join(self.supported)
        super().__init__(
            f"Collection manifest{location} declares unknown engine version "
            f"{found!r}. Supported versions: {supported_str}. "
            f"The collection was not modified."
        )


class EngineNotAvailableError(CoreError):
    """A requested engine version exists in the routing contract but has no
    implementation yet (v2 arrives in a later core-v2 unit)."""

    def __init__(self, version: str) -> None:
        self.version = version
        super().__init__(
            f"The v{version} engine is not yet available; it arrives in a later "
            f"unit of the core-v2 feature. Use --engine v1 (the default)."
        )


class CoreV2Error(CoreError):
    """A core.v2 engine operation failed.

    Wraps upstream (LlamaIndex) exceptions at the v2 service boundary, which
    have no stable hierarchy (tech.md §Errors), so every failure still inherits
    :class:`~indexed.config.errors.IndexedError` (CLI exit codes + MCP
    envelopes keep working).
    """


class UpdateNotSupportedError(CoreV2Error):
    """``update`` on a v2 collection — deferred to core-v2/3.

    v2 incremental update is not implemented in the create/search MVP; re-create
    the collection to refresh it for now. Raised (never a crash) so the CLI
    surfaces an actionable message.
    """

    def __init__(self) -> None:
        super().__init__(
            "v2 incremental update arrives in core-v2/3; re-create the "
            "collection to refresh it for now (indexed index create "
            "--engine v2 ...)."
        )


class UnknownVectorStoreError(CoreError):
    """A v2 collection records a vector store this installation can't load.

    Raised by :func:`indexed.core.v2.stores.load_storage_context` when the
    manifest's ``engine.vectorStore`` is not one this build supports. The
    engine fails loud (R9) and NEVER silently substitutes another store, so a
    collection built for a future store is never mis-read as ``simple``.
    """

    def __init__(self, store: object, *, known: Iterable[str]) -> None:
        self.store = store
        self.known = tuple(known)
        known_str = ", ".join(sorted(self.known))
        super().__init__(
            f"Collection manifest records vector store {store!r}, which this "
            f"installation cannot load. Supported stores: {known_str}. "
            f"The collection was not modified."
        )


__all__ = [
    "CoreError",
    "CoreV2Error",
    "EngineMismatchError",
    "UnknownEngineVersionError",
    "EngineNotAvailableError",
    "UnknownVectorStoreError",
    "UpdateNotSupportedError",
]
