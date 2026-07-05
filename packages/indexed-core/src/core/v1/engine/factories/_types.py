"""Shared DI factory type aliases for the update path.

Leaf module: imports only DiskPersister (persisters) and the reader/converter
protocols — both downward — so it never re-introduces a services<->factories cycle.
"""

from collections.abc import Callable

from protocols import DocumentConverter, DocumentReader

from core.v1.engine.persisters.disk_persister import DiskPersister

ManifestConnectorFactory = Callable[[dict], tuple[DocumentReader, DocumentConverter]]

LocalFilesUpdateFactory = Callable[
    [dict, str, DiskPersister],
    tuple[DocumentReader, DocumentConverter, list[str], Callable[[], None] | None],
]
