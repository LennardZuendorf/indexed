"""SimpleVectorStore construction + manifest-dispatched LOAD (core-v2/2b).

Two entry points: :func:`new_storage_context` builds a fresh StorageContext
(SimpleVectorStore + default doc/index stores) for CREATE; :func:`load_storage_context`
loads a persisted one, dispatching on the manifest's recorded
``engine.vectorStore``. An unknown store id fails loud
(:class:`~indexed.core.errors.UnknownVectorStoreError`, R9) — the engine NEVER
silently substitutes ``simple`` for a store it can't load, so a collection built
for a future store is never mis-read.

Laziness: ``llama_index.core`` costs ~1.0–1.4 s to import (tech.md) — every
LlamaIndex import lives inside a function body. Only a ``TYPE_CHECKING`` import
sits at module level, for annotations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from indexed.core.errors import UnknownVectorStoreError

if TYPE_CHECKING:
    from pathlib import Path

    from llama_index.core import StorageContext

    from indexed.core.v2.manifest import V2Manifest


def known_vector_stores() -> frozenset[str]:
    """Vector-store ids this installation can construct and load.

    ``simple`` (SimpleVectorStore) is the only store this feature ships; the
    manifest's ``vectorStore`` field is the seam for future stores (tech.md —
    no ``[core.v2.storage]`` config knob until a second store exists).
    """
    return frozenset({"simple"})


def new_storage_context() -> "StorageContext":
    """A fresh StorageContext for CREATE (SimpleVectorStore + default stores)."""
    from llama_index.core import StorageContext
    from llama_index.core.vector_stores.simple import SimpleVectorStore

    return StorageContext.from_defaults(vector_store=SimpleVectorStore())


def load_storage_context(
    persist_dir: "Path", manifest: "V2Manifest"
) -> "StorageContext":
    """Load a persisted StorageContext, dispatching on the recorded store (R9).

    ``simple`` → ``StorageContext.from_defaults(persist_dir=...)`` (reads
    ``storage/{docstore,index_store,default__vector_store}.json``). Any other
    recorded store → :class:`~indexed.core.errors.UnknownVectorStoreError`,
    raised BEFORE any I/O or heavy import — fail loud, never a silent fallback.
    """
    store = manifest.engine.vector_store
    if store not in known_vector_stores():
        raise UnknownVectorStoreError(store, known=known_vector_stores())

    from llama_index.core import StorageContext

    return StorageContext.from_defaults(persist_dir=str(persist_dir))


def persist(storage_context: "StorageContext", storage_dir: "Path") -> None:
    """Persist ``storage_context`` into ``storage_dir`` (the ``storage/`` subdir).

    Thin wrapper centralizing the on-disk convention; core-v2/2c owns the
    build-aside staging + atomic rename-swap around it.
    """
    storage_context.persist(persist_dir=str(storage_dir))


__all__ = [
    "known_vector_stores",
    "load_storage_context",
    "new_storage_context",
    "persist",
]
