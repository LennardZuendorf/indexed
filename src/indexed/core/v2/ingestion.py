"""v2 CREATE path — read + convert documents, embed, persist aside, swap (core-v2/2c).

Reads documents through the injected connector's reader/converter (the shared
``protocols`` seam — exactly the pair v1's ``DocumentCollectionCreator`` drives),
turns each ConvertedDocument into pre-chunked ``TextNode``s via the adapter, then
builds a LlamaIndex ``VectorStoreIndex`` with an EXPLICIT embed model and
``transformations=[embed_model]`` only — no node parser, so the pre-chunked
content is never re-split (verified: node count == chunk count). ``Settings`` is
never touched.

Durability: the collection is built into a staging dir and atomically
rename-swapped into place (:func:`indexed.core.v2.persist.replace_dir`); the
prior collection is never deleted before the replacement is durably written.

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
except ImportError:  # pragma: no cover - orjson is a hard dep, fallback for safety
    import json

    def _json_dumps(data: Any) -> str:
        return json.dumps(data, indent=2, ensure_ascii=False)


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

    # Persist change-tracker state into the FINAL dir (needed by core-v2/3
    # update); only when the connector supports it (files today).
    if isinstance(connector, _SupportsSaveState):
        connector.save_state(str(base / cfg.name))


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


__all__ = ["create"]
