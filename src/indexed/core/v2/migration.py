"""v1 -> v2 migration service (core-v2/4, R7).

Converts an existing v1 collection into a v2 collection on EXPLICIT request. The
default path is OFFLINE: it re-embeds from the v1 collection's stored
``documents/<id>.json`` chunk text (``indexedData``) with the v2 embed model —
no source or network access (v1 chunks are <=256 tokens, within any target
model's window). ``--from-source`` instead re-reads the live source through the
connector's ``from_manifest`` seam (the same seam ``update`` uses), via a
caller-supplied ``manifest_factory``.

Durability (R7 core): the v2 collection is built ASIDE into a staging dir and
VALIDATED (counts + a retriever-only probe search) BEFORE anything the user owns
is touched. Only then is the original v1 directory RENAMED to ``<name>.v1-backup``
(preserving it byte-for-byte) and the staging dir renamed into ``<name>``. If the
final swap fails, the backup is renamed back (rollback restores the v1 dir
byte-identical) and the staging dir is discarded. The v1 backup is kept until
``--purge-backup``. ``--dry-run`` computes the report and makes ZERO file changes.

Layering: v1 is FROZEN and never imported here (``core/v2 -> core.v1`` is
forbidden); migration READS the v1 on-disk layout directly (``manifest.json`` +
``documents/<id>.json``), which is data, not v1 code. Engine detection reuses the
facade-level ``indexed.core.versioning`` (``core.versioning``, not ``core.v1``).
LlamaIndex (~1s import) is imported function-locally, so importing this module
stays cheap (CLI startup <1s); ``Settings`` is never touched and the probe search
is retriever-only.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional

from indexed.core.errors import CoreV2Error
from indexed.core.v2._common import collections_base, resolve_embedding_config
from indexed.core.v2.ingestion import (
    _document_hash,
    _json_dumps,
    _json_loads,
    _latest_modified_time,
    _read_documents,
)


@dataclass(frozen=True)
class MigrationResult:
    """Outcome of a migration (the CLI renders it; tests assert on it).

    ``action`` is one of ``"migrate"`` (a v1->v2 conversion happened),
    ``"dry-run"`` (report only, no file changes), or ``"purge-backup"`` (a
    standalone backup cleanup on an already-migrated collection).
    """

    name: str
    action: str
    dry_run: bool
    from_source: bool
    number_of_documents: int
    number_of_chunks: int
    embedding_model: str
    vector_store: str
    backup_path: Optional[str]
    backup_purged: bool
    validated: bool
    probe_query: Optional[str] = None


def migrate(
    name: str,
    *,
    collections_path: Optional[str] = None,
    dry_run: bool = False,
    from_source: bool = False,
    purge_backup: bool = False,
    manifest_factory: Optional[Callable[[Any, str], Any]] = None,
) -> MigrationResult:
    """Migrate the v1 collection ``name`` to v2 (R7). See the module docstring.

    Raises :class:`~indexed.core.errors.CoreV2Error` (a typed ``IndexedError``)
    when the collection is missing, is already v2 (nothing to migrate), a stale
    backup blocks the swap, ``--from-source`` is requested without a
    ``manifest_factory``, or validation fails. On a validation failure the v1
    collection is left fully intact and no partial v2 collection survives.
    """
    from indexed.core.versioning import detect_engine_version

    base = collections_base(collections_path)
    collection_dir = base / name
    manifest_path = collection_dir / "manifest.json"
    backup_dir = base / f"{name}.v1-backup"

    if not manifest_path.is_file():
        raise CoreV2Error(
            f"Collection '{name}' does not exist; nothing to migrate. "
            "Create it first, or check the collection name."
        )

    # detect_engine_version fails loud (UnknownEngineVersionError) on an
    # unsupported marker, leaving the collection untouched (R1); a v2 marker
    # means there is nothing to migrate.
    version = detect_engine_version(collection_dir)
    if version == "2":
        if purge_backup:
            if backup_dir.is_dir():
                # Standalone cleanup: the collection was already migrated in a
                # prior run — drop its retained v1 backup (this is the only path
                # that can purge a backup once <name> itself is v2). Best-effort
                # rmtree, consistent with the post-migrate purge below.
                shutil.rmtree(backup_dir, ignore_errors=True)
                return MigrationResult(
                    name=name,
                    action="purge-backup",
                    dry_run=False,
                    from_source=from_source,
                    number_of_documents=0,
                    number_of_chunks=0,
                    embedding_model=resolve_embedding_config().model_name,
                    vector_store="simple",
                    backup_path=None,
                    backup_purged=True,
                    validated=False,
                )
            # --purge-backup on an already-v2 collection with NO backup: a
            # dedicated message, not the misleading "already a v2 collection;
            # nothing to migrate" (which implies a migration was expected).
            raise CoreV2Error(
                f"No backup to purge for '{name}'; there is no "
                f"'{backup_dir.name}' directory."
            )
        raise CoreV2Error(
            f"Collection '{name}' is already a v2 collection; nothing to migrate."
        )

    if from_source and manifest_factory is None:
        raise CoreV2Error(
            "--from-source requires a manifest_factory to rebuild the connector; "
            "none was supplied."
        )

    v1_raw = _json_loads(manifest_path.read_text(encoding="utf-8"))
    reader_block = v1_raw.get("reader") or {}
    created_time = v1_raw.get("createdTime")
    last_modified_default = v1_raw.get("lastModifiedDocumentTime")
    v1_doc_count = v1_raw.get("numberOfDocuments")

    # Gather the documents to (re-)embed: OFFLINE from the stored ConvertedDocument
    # dicts, or a FULL re-read from the live source (--from-source).
    if from_source:
        # Guaranteed non-None by the --from-source guard above; assert narrows it
        # for the type checker.
        assert manifest_factory is not None
        documents = _read_documents_from_source(v1_raw, manifest_factory)
    else:
        documents = _load_v1_documents(collection_dir)

    number_of_documents = len(documents)
    number_of_chunks = sum(len(doc.get("chunks") or []) for doc in documents)
    embed_config = resolve_embedding_config()
    embedding_model = embed_config.model_name

    if dry_run:
        # ZERO file changes: report the counts + target model/store and return.
        return MigrationResult(
            name=name,
            action="dry-run",
            dry_run=True,
            from_source=from_source,
            number_of_documents=number_of_documents,
            number_of_chunks=number_of_chunks,
            embedding_model=embedding_model,
            vector_store="simple",
            backup_path=None,
            backup_purged=False,
            validated=False,
        )

    if not documents:
        raise CoreV2Error(
            f"No documents found to migrate for collection '{name}'. The v1 "
            "collection has no stored documents to re-embed."
        )

    if backup_dir.exists():
        raise CoreV2Error(
            f"A backup already exists at '{backup_dir.name}'. Remove it "
            f"(indexed index migrate {name} --purge-backup) or move it aside "
            "before migrating."
        )

    # Build the v2 collection ASIDE (pid-first staging name, excluded from
    # discovery) and VALIDATE it before touching anything the user owns.
    staging = base / f"{name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        built_docs, built_chunks = _build_v2_staging(
            staging,
            name,
            documents,
            reader_block,
            created_time,
            last_modified_default,
            embed_config,
        )
        probe_query = _probe_query_from(documents)
        _validate_migration(
            base,
            staging.name,
            from_source=from_source,
            v1_doc_count=v1_doc_count,
            built_docs=built_docs,
            built_chunks=built_chunks,
            probe_query=probe_query,
        )
    except Exception:
        # Validation/build failed → discard staging; the v1 collection was never
        # touched and remains fully usable (R7 scenario 2).
        shutil.rmtree(staging, ignore_errors=True)
        raise

    # Backup + atomic swap. Rename (not copy) preserves the v1 dir byte-for-byte.
    os.rename(collection_dir, backup_dir)
    try:
        _swap(staging, collection_dir)
    except Exception:
        # Swap failed after the backup rename → roll the original back into place
        # (byte-identical) and discard the staging dir (R7 scenario 5).
        os.rename(backup_dir, collection_dir)
        shutil.rmtree(staging, ignore_errors=True)
        raise

    backup_purged = False
    backup_path: Optional[str] = str(backup_dir)
    if purge_backup:
        shutil.rmtree(backup_dir, ignore_errors=True)
        backup_purged = True
        backup_path = None

    return MigrationResult(
        name=name,
        action="migrate",
        dry_run=False,
        from_source=from_source,
        number_of_documents=built_docs,
        number_of_chunks=built_chunks,
        embedding_model=embedding_model,
        vector_store="simple",
        backup_path=backup_path,
        backup_purged=backup_purged,
        validated=True,
        probe_query=probe_query,
    )


def _swap(staging: Path, dest: Path) -> None:
    """Rename the built staging dir into ``dest`` (the final swap step).

    Isolated as a named helper so the durability contract (rollback on swap
    failure) is directly testable — a test patches this to raise and asserts the
    v1 backup is renamed back byte-identical.
    """
    os.rename(staging, dest)


def _load_v1_documents(collection_dir: Path) -> List[dict[str, Any]]:
    """Read every stored ``documents/<id>.json`` as a ConvertedDocument dict.

    This is the OFFLINE source of truth: the v1 collection's persisted chunk
    text, re-embedded as-is (no source access, no re-chunking). Sorted by
    filename for deterministic order.
    """
    docs_dir = collection_dir / "documents"
    if not docs_dir.is_dir():
        return []
    documents: List[dict[str, Any]] = []
    for doc_file in sorted(docs_dir.glob("*.json")):
        try:
            raw = _json_loads(doc_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CoreV2Error(
                f"Could not read stored document '{doc_file.name}' while "
                f"migrating: {exc}"
            ) from exc
        if isinstance(raw, dict):
            documents.append(raw)
    return documents


def _read_documents_from_source(
    v1_raw: dict[str, Any], manifest_factory: Callable[[Any, str], Any]
) -> List[dict[str, Any]]:
    """Re-read the FULL corpus from the live source via ``manifest_factory``.

    Builds a ``protocols.Manifest`` from the v1 manifest and hands it to the
    caller's ``manifest_factory`` (the ``from_manifest`` seam ``update`` uses).
    A throwaway ``storage_path`` (no ``state.json``) is passed so change-tracking
    connectors yield the WHOLE corpus, not an incremental slice — migration must
    rebuild the entire collection, not just what changed since the v1 state.
    """
    from indexed.protocols import Manifest

    manifest = Manifest.from_disk(v1_raw)
    tmp_state = tempfile.mkdtemp(prefix="indexed-migrate-")
    try:
        run = manifest_factory(manifest, tmp_state)
        return _read_documents(run.reader, run.converter)
    finally:
        shutil.rmtree(tmp_state, ignore_errors=True)


def _build_v2_staging(
    staging: Path,
    name: str,
    documents: List[dict[str, Any]],
    reader_block: dict[str, Any],
    created_time: Optional[str],
    last_modified_default: Optional[str],
    embed_config: Any,
) -> tuple[int, int]:
    """Embed ``documents`` and persist a complete v2 collection into ``staging``.

    Mirrors ``ingestion._create_one`` (explicit embed model,
    ``transformations=[embed_model]`` only so pre-chunked nodes are never
    re-split, per-doc content hashes recorded as the upsert basis) but sources
    documents from the caller instead of a live connector. The v1 ``reader``
    block is REUSED verbatim so a future v2 ``update``'s ``from_manifest``
    dispatch keeps working; ``createdTime`` is preserved. Returns
    ``(number_of_documents, number_of_chunks)``.
    """
    from llama_index.core import VectorStoreIndex

    from indexed.core.v2.adapter import to_nodes
    from indexed.core.v2.embedding.local import build_embed_model, probe_dimension
    from indexed.core.v2.manifest import V2Manifest
    from indexed.core.v2.stores import new_storage_context, persist
    from indexed.protocols.models import ReaderDetails

    nodes: list[Any] = []
    for doc in documents:
        nodes.extend(to_nodes(doc, name))

    embed_model = build_embed_model(embed_config)
    dimension = probe_dimension(embed_model)

    storage_context = new_storage_context()
    VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        transformations=[embed_model],
    )
    for doc in documents:
        storage_context.docstore.set_document_hash(doc["id"], _document_hash(doc))

    now = datetime.now(timezone.utc).isoformat()
    last_modified = _latest_modified_time(
        documents, default=last_modified_default or now
    )

    manifest = V2Manifest.new(
        collection_name=name,
        reader=ReaderDetails.model_validate(reader_block or {"type": "unknown"}),
        embedding_model=embed_config.model_name,
        dimension=dimension,
        created_time=created_time or now,
        updated_time=now,
        last_modified_document_time=last_modified,
        number_of_documents=len(documents),
        number_of_chunks=len(nodes),
    )

    persist(storage_context, staging / "storage")
    (staging / "manifest.json").write_text(
        _json_dumps(manifest.to_disk()), encoding="utf-8"
    )
    return len(documents), len(nodes)


def _validate_migration(
    base: Path,
    staged_name: str,
    *,
    from_source: bool,
    v1_doc_count: Any,
    built_docs: int,
    built_chunks: int,
    probe_query: str,
) -> None:
    """Assert the staged v2 collection is complete + searchable (before the swap).

    - The manifest counts must be internally consistent (``built_chunks`` node
      count is non-negative and matches what was embedded);
    - OFFLINE: the doc count must equal the v1 manifest's (re-embedding stored
      documents must neither drop nor add any); ``--from-source`` reflects the
      live source, so equality with the frozen v1 count is not required (only a
      non-empty, searchable result);
    - a retriever-only probe search on the staged collection must return results.

    Any failure raises :class:`~indexed.core.errors.CoreV2Error`; the caller then
    discards the staging dir with the v1 collection untouched.
    """
    if built_docs <= 0 or built_chunks <= 0:
        raise CoreV2Error(
            "Migration validation failed: the staged v2 collection has no "
            f"documents/chunks (documents={built_docs}, chunks={built_chunks})."
        )
    if not from_source and isinstance(v1_doc_count, int) and built_docs != v1_doc_count:
        raise CoreV2Error(
            "Migration validation failed: document count mismatch "
            f"(v1 recorded {v1_doc_count}, v2 built {built_docs})."
        )
    if not _probe_search(base, staged_name, probe_query):
        raise CoreV2Error(
            "Migration validation failed: a probe search on the migrated v2 "
            "collection returned no results."
        )


def _probe_search(base: Path, staged_name: str, query: str) -> bool:
    """Retriever-only probe against the staged collection (loads + retrieves).

    Reuses the tested ``retrieval.search`` path with an EXPLICIT config naming
    the staging dir (explicit configs bypass tmp/trash discovery exclusion), so
    the probe exercises the real load-from-manifest + store-dispatch + retriever
    flow. A load failure surfaces as a per-collection ``{"error": ...}`` entry,
    which is raised as a validation failure.
    """
    from indexed.core.v2 import retrieval
    from indexed.protocols import SourceConfig

    cfg = SourceConfig(name=staged_name, type="localFiles", base_url_or_path="")
    result = retrieval.search(query, configs=[cfg], collections_path=str(base))
    entry = result.get(staged_name) or {}
    if "error" in entry:
        raise CoreV2Error(f"Migration validation probe search failed: {entry['error']}")
    return bool(entry.get("results"))


def _probe_query_from(documents: List[dict[str, Any]]) -> str:
    """Derive a probe query from the corpus (first non-empty chunk text).

    The retriever returns up to k nodes regardless of similarity, so any query
    over a non-empty collection yields results; deriving it from real content
    keeps the probe meaningful. Falls back to a constant if no chunk text exists.
    """
    for doc in documents:
        for chunk in doc.get("chunks") or []:
            text = str(chunk.get("indexedData", "")).strip()
            if text:
                return text[:200]
    return "probe"


__all__ = ["MigrationResult", "migrate"]
