"""v2 CREATE + UPDATE paths — read + convert, embed, persist aside, swap.

CREATE (core-v2/2c) reads documents through the injected connector's
reader/converter (the shared ``protocols`` seam — exactly the pair v1's
``DocumentCollectionCreator`` drives), turns each ConvertedDocument into
pre-chunked ``TextNode``s via the adapter, then builds a LlamaIndex
``VectorStoreIndex`` with an EXPLICIT embed model and
``transformations=[embed_model]`` only — no node parser, so the pre-chunked
content is never re-split (verified: node count == chunk count). ``Settings`` is
never touched. A per-document content hash is recorded in the docstore (the
incremental-update upsert basis, tech.md "V2 on-disk layout").

UPDATE (core-v2/3) is INCREMENTAL: it loads the existing collection's storage
context into memory, rebuilds the ``ConnectorRun`` from the stored manifest (the
same ``manifest_factory``/``from_manifest`` seam v1 uses), and upserts each
incoming document keyed on ``ref_doc_id`` via the docstore's per-doc hash
(DocstoreStrategy.UPSERTS semantics): an unchanged hash SKIPS the document (no
re-embed, node ids stay stable), a changed hash deletes the old ref-doc nodes
and re-embeds, a new document is inserted. ``ConnectorRun.deletions`` are honored
via ``delete_ref_doc`` (the document becomes unfindable). Only the changed/new
set is ever embedded (R5).

Durability: both paths build into a staging dir and atomically rename-swap into
place (:func:`indexed.core.v2.persist.replace_dir`); the prior collection is
never deleted before the replacement is durably written (fixes the PR #86
delete-before-persist defect). UPDATE only READS the live collection until the
swap — it is never mutated in place.

Laziness: LlamaIndex (~1s import) and the adapter/embedding/stores are imported
FUNCTION-LOCALLY; importing this module stays cheap (CLI startup <1s).

Disk read-cache: v1's ``use_cache``/``cache_decorator_factory`` wraps the reader
in a ``CacheReaderDecorator`` backed by v1's ``DiskPersister``. Both live in
layers ``core/v2`` may not import (``connectors`` / ``core.v1``), and the
decorator is a create-time read optimization that does not change the documents
produced or the on-disk collection. So core-v2/2c reads directly from the
connector (documents are identical either way); the disk read-cache is a
DEFERRED residual — the parameters are accepted for signature parity and noted
here (see the task report).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)

from indexed.protocols import BaseConnector, SourceConfig
from indexed.protocols.models import ReaderDetails

from indexed.core.errors import CoreV2Error
from indexed.core.v2._common import collections_base, resolve_embedding_config

if TYPE_CHECKING:
    from llama_index.core.schema import TextNode

try:
    import orjson

    def _json_dumps(data: Any) -> str:
        return orjson.dumps(data, option=orjson.OPT_INDENT_2).decode("utf-8")

    def _json_loads(data: str) -> Any:
        return orjson.loads(data)
except ImportError:  # pragma: no cover - orjson is a hard dep, fallback for safety
    import json

    def _json_dumps(data: Any) -> str:
        return json.dumps(data, indent=2, ensure_ascii=False)

    def _json_loads(data: str) -> Any:
        return json.loads(data)


@runtime_checkable
class _SupportsSaveState(Protocol):
    """Optional connector capability: persist change-tracking state post-build."""

    def save_state(self, storage_path: str) -> None: ...


def create(
    configs: List[SourceConfig],
    *,
    use_cache: bool = True,
    force: bool = False,
    phased_progress: Any = None,
    collections_path: Optional[str] = None,
    caches_path: Optional[str] = None,
    connector_factory: Callable[[SourceConfig], BaseConnector],
    cache_decorator_factory: Any = None,
) -> None:
    """Create v2 collections from source configurations (facade-forwarded args).

    ``use_cache``/``cache_decorator_factory``/``caches_path`` are accepted for
    signature parity with v1's ``create`` but the disk read-cache is deferred
    (see module docstring). ``force`` needs no special handling: the build-aside
    swap already overwrites any existing collection durably.
    """
    del use_cache, caches_path, cache_decorator_factory, force  # parity-only here
    base = collections_base(collections_path)
    base.mkdir(parents=True, exist_ok=True)
    for cfg in configs:
        _create_one(cfg, base, connector_factory, phased_progress)


def _create_one(
    cfg: SourceConfig,
    base: Path,
    connector_factory: Callable[[SourceConfig], BaseConnector],
    phased_progress: Any,
) -> None:
    from indexed.core.v2.adapter import to_nodes
    from indexed.core.v2.embedding.local import build_embed_model, probe_dimension
    from indexed.core.v2.manifest import V2Manifest
    from indexed.core.v2.persist import replace_dir
    from indexed.core.v2.stores import new_storage_context, persist

    connector = connector_factory(cfg)
    reader = connector.reader
    converter = connector.converter

    if phased_progress:
        phased_progress.start_phase("Fetching Documents")
    documents = _read_documents(reader, converter)
    if phased_progress:
        phased_progress.finish_phase("Fetching Documents")

    if not documents:
        # Typed IndexedError so the service boundary's ``_wrap`` passes it through
        # with its own actionable message (not the generic "v2 create failed:").
        raise CoreV2Error(
            f"No documents found for collection '{cfg.name}'. Check that the "
            "source path exists and contains readable content."
        )

    nodes: list["TextNode"] = []
    for doc in documents:
        nodes.extend(to_nodes(doc, cfg.name))

    embed_config = resolve_embedding_config()
    embed_model = build_embed_model(embed_config)
    dimension = probe_dimension(embed_model)

    if phased_progress:
        phased_progress.start_phase("Generating Embeddings", total=len(nodes))

    # Explicit embed_model + transformations=[embed_model] ONLY: the pre-chunked
    # nodes must NOT be re-split, so no node parser is in the pipeline. Settings
    # is never read/written; as_query_engine is never called.
    from llama_index.core import VectorStoreIndex

    storage_context = new_storage_context()
    VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        embed_model=embed_model,
        transformations=[embed_model],
    )

    # Record per-document content hashes in the docstore — the basis a later
    # ``update`` compares against to SKIP unchanged documents (no re-embed) while
    # still re-embedding changed ones (core-v2/3, tech.md "V2 on-disk layout").
    for doc in documents:
        storage_context.docstore.set_document_hash(doc["id"], _document_hash(doc))

    if phased_progress:
        phased_progress.finish_phase("Generating Embeddings")

    now = datetime.now(timezone.utc).isoformat()
    last_modified = _latest_modified_time(documents, default=now)

    manifest = V2Manifest.new(
        collection_name=cfg.name,
        reader=ReaderDetails.model_validate(reader.get_reader_details()),
        embedding_model=embed_config.model_name,
        dimension=dimension,
        created_time=now,
        updated_time=now,
        last_modified_document_time=last_modified,
        number_of_documents=len(documents),
        number_of_chunks=len(nodes),
    )

    # pid FIRST (digits) so the name matches the tmp/trash discovery-exclusion
    # regex ``\.(?:tmp|trash)-\d+`` in ``_common`` and the facade — mirrors v1's
    # ``<name>.tmp-<pid>-<hex>`` convention. A bare hex prefix escapes the regex
    # ~37.5% of the time, so a create killed mid-build would leave a phantom
    # discoverable collection (core-v2/2c review, Critical).
    staging = base / f"{cfg.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        persist(storage_context, staging / "storage")
        (staging / "manifest.json").write_text(
            _json_dumps(manifest.to_disk()), encoding="utf-8"
        )
    except Exception:
        # Discard only the aside dir — the prior collection is untouched.
        import shutil

        shutil.rmtree(staging, ignore_errors=True)
        raise

    replace_dir(staging, base / cfg.name)

    # Persist change-tracker state into the FINAL dir (used by the incremental
    # update path); only when the connector supports it (files today).
    if isinstance(connector, _SupportsSaveState):
        connector.save_state(str(base / cfg.name))


def update(
    configs: List[SourceConfig],
    phased_progress: Any = None,
    collections_path: Optional[str] = None,
    *,
    manifest_factory: Callable[[Any, str], Any],
) -> None:
    """Incrementally update v2 collections (only new/changed docs re-embedded).

    Mirrors v1's ``update`` signature/semantics: per collection the
    ``manifest_factory`` rebuilds a ``ConnectorRun`` from the stored manifest,
    the reader/converter yield the source documents, and each is upserted into
    the existing index keyed on ``ref_doc_id`` (unchanged → skipped, no
    re-embed). Deletions are honored and the collection is built aside + swapped.
    """
    base = collections_base(collections_path)
    for cfg in configs:
        _update_one(cfg, base, manifest_factory, phased_progress)


def _update_one(
    cfg: SourceConfig,
    base: Path,
    manifest_factory: Callable[[Any, str], Any],
    phased_progress: Any,
) -> None:
    from indexed.core.v2.adapter import to_nodes
    from indexed.core.v2.config_models import CoreV2EmbeddingConfig
    from indexed.core.v2.embedding.local import build_embed_model
    from indexed.core.v2.manifest import V2Manifest
    from indexed.core.v2.persist import replace_dir
    from indexed.core.v2.stores import load_storage_context, persist

    collection_dir = base / cfg.name
    manifest_path = collection_dir / "manifest.json"
    if not manifest_path.is_file():
        raise CoreV2Error(
            f"Collection '{cfg.name}' does not exist. Create it before updating."
        )

    manifest = V2Manifest.from_disk(
        _json_loads(manifest_path.read_text(encoding="utf-8"))
    )

    # Rebuild the connector's reader/converter/deletions/post_run from the stored
    # manifest — the SAME source-agnostic seam v1 drives. The change-tracker
    # state is read from the LIVE collection dir; nothing is written there yet.
    run = manifest_factory(manifest, str(collection_dir))
    reader, converter = run.reader, run.converter
    deletions = list(run.deletions or [])
    post_run = run.post_run

    if phased_progress:
        phased_progress.start_phase("Fetching Documents")
    documents = _read_documents(reader, converter)
    if phased_progress:
        phased_progress.finish_phase("Fetching Documents")

    now = datetime.now(timezone.utc).isoformat()

    # Empty-body: no new/changed documents AND no deletions → timestamp-only
    # manifest bump. No index load, no embedding (v1 invariant carried over — an
    # empty update is a no-op, never a crash).
    if not documents and not deletions:
        manifest.updated_time = now
        _atomic_write(manifest_path, _json_dumps(manifest.to_disk()))
        if post_run is not None:
            post_run()
        return

    # Load the LIVE storage context fully into memory (SimpleVectorStore +
    # SimpleDocumentStore are in-memory JSON); the on-disk collection is only
    # READ here — never mutated until the atomic swap (build-aside durability).
    # The collection's OWN recorded embedding model is used (never the currently
    # configured default) so vectors stay consistent within the collection.
    embed_model = build_embed_model(
        CoreV2EmbeddingConfig(model_name=manifest.engine.embedding.model)
    )
    storage_context = load_storage_context(collection_dir / "storage", manifest)

    from llama_index.core import load_index_from_storage

    index = load_index_from_storage(storage_context, embed_model=embed_model)
    docstore = index.docstore

    # Deletions first (ConnectorRun.deletions → delete_ref_doc): the document and
    # its nodes leave BOTH the docstore and the vector store, so it becomes
    # unfindable. Deleting an absent id is a safe no-op (raise_error=False).
    for doc_id in deletions:
        index.delete_ref_doc(doc_id, delete_from_docstore=True)

    if phased_progress:
        phased_progress.start_phase("Generating Embeddings")

    # Incremental upsert keyed on ref_doc_id via the docstore's per-doc hash
    # (DocstoreStrategy.UPSERTS semantics): unchanged hash → SKIP (no re-embed,
    # node ids stay stable); changed → delete old ref-doc nodes + re-embed; new
    # → insert. ``insert_nodes`` runs no transformations, so the pre-chunked
    # node ids (``<id>::chunk_<i>``) are preserved (no re-split). Only the
    # changed/new set is ever embedded (R5).
    for doc in documents:
        doc_id = doc["id"]
        new_hash = _document_hash(doc)
        exists = docstore.get_ref_doc_info(doc_id) is not None
        if exists and docstore.get_document_hash(doc_id) == new_hash:
            continue
        if exists:
            index.delete_ref_doc(doc_id, delete_from_docstore=True)
        nodes = to_nodes(doc, cfg.name)
        if nodes:
            index.insert_nodes(nodes)
        docstore.set_document_hash(doc_id, new_hash)

    if phased_progress:
        phased_progress.finish_phase("Generating Embeddings")

    # Recompute counts from the mutated docstore (distinct source documents /
    # total chunk nodes); preserve createdTime + the engine + reader blocks.
    source_ids = {
        (node.metadata or {}).get("source_id") for node in docstore.docs.values()
    }
    source_ids.discard(None)
    manifest.updated_time = now
    manifest.last_modified_document_time = _latest_modified_time(
        documents, default=manifest.last_modified_document_time
    )
    manifest.number_of_documents = len(source_ids)
    manifest.number_of_chunks = len(docstore.docs)

    # Build-aside + atomic swap: persist the mutated storage + manifest into a
    # pid-first staging dir (``.tmp-<pid>-<hex>`` — excluded from discovery) and
    # rename-swap it into place. The prior collection is never deleted before
    # the replacement is durably written (PR #86 delete-before-persist defect).
    staging = base / f"{cfg.name}.tmp-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        persist(storage_context, staging / "storage")
        (staging / "manifest.json").write_text(
            _json_dumps(manifest.to_disk()), encoding="utf-8"
        )
    except Exception:
        import shutil

        shutil.rmtree(staging, ignore_errors=True)
        raise

    replace_dir(staging, collection_dir)

    # post_run (files: persist the new change-tracker state) runs AFTER a
    # successful swap so the state lands in the final dir and reflects the
    # now-current source tree — v1 runs its post_run after a successful update
    # too. A post_run failure here leaves a durable, correct collection (only the
    # change-tracker sidecar is stale → the next update re-scans, still correct).
    if post_run is not None:
        post_run()


def _document_hash(doc: dict[str, Any]) -> str:
    """Stable content hash over a document's ordered chunk texts (upsert basis).

    Keyed on chunk ``indexedData`` ONLY, so a metadata-only change (e.g. a new
    ``modifiedTime`` with identical content) does NOT force a re-embed — exactly
    the "only new/changed docs re-embedded" behavior R5 requires.
    """
    chunks = doc.get("chunks") or []
    payload = "\n".join(str(chunk.get("indexedData", "")) for chunk in chunks)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file + atomic ``os.replace``.

    Used only by the empty-body timestamp bump: the manifest is rewritten in one
    atomic step so a crash can never leave a half-written manifest on disk.
    """
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _read_documents(reader: Any, converter: Any) -> list[dict[str, Any]]:
    """Read + convert every source document into on-disk ConvertedDocument dicts.

    Mirrors ``DocumentCollectionCreator.__read_documents`` (minus the disk
    persistence): today's converters return the dict arm of the protocol union.
    """
    documents: list[dict[str, Any]] = []
    for raw in reader.read_all_documents():
        for converted in converter.convert(raw):
            assert isinstance(converted, dict)
            documents.append(converted)
    return documents


def _latest_modified_time(documents: list[dict[str, Any]], *, default: str) -> str:
    """Max ``modifiedTime`` across documents (ISO 8601), or ``default`` if none parse."""
    latest: Optional[datetime] = None
    for doc in documents:
        raw = doc.get("modifiedTime")
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw)
        except (TypeError, ValueError):
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest.isoformat() if latest is not None else default


__all__ = ["create", "update"]
