"""v2 SEARCH path — retriever-only, cosine scores (core-v2/2c).

Loads each target v2 collection's ``StorageContext`` (store dispatched from its
manifest), rebuilds the ``VectorStoreIndex``, and retrieves with an EXPLICIT
embed model via ``index.as_retriever(...).retrieve(query)`` — NEVER
``as_query_engine()`` and NEVER touching ``Settings``, so the retrieval path
never resolves an LLM (proven by a Settings-guard test). Each returned
``NodeWithScore.score`` is a cosine similarity (higher-is-better); results are
mapped into the EXACT v1 result-dict shape so the existing CLI/MCP formatters
work unchanged.

Per-collection failures are captured as ``{"error": ...}`` entries (never
raised), exactly like v1's ``SearchService``. LlamaIndex imports are
function-local (CLI startup <1s).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

from indexed.core.v2._common import (
    collections_base,
    discover_v2_collections,
    resolve_search_config,
)

if TYPE_CHECKING:
    from llama_index.core.base.embeddings.base import BaseEmbedding
    from llama_index.core.schema import NodeWithScore

    from indexed.protocols import SourceConfig

# Upper bound on retrieved chunks so doc-grouping isn't starved by one dominant
# document filling the top-k (v1 bug A5). Brute-force cosine at <100k chunks is
# cheap, so a larger fetch just bounds the worst case.
_OVERFETCH_CEILING = 10_000


def search(
    query: str,
    configs: Optional[List["SourceConfig"]] = None,
    max_chunks: Optional[int] = None,
    max_docs: Optional[int] = None,
    score_threshold: Optional[float] = None,
    include_full_text: bool = False,
    include_all_chunks: bool = False,
    include_matched_chunks: bool = False,
    collections_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Search v2 collections; return ``{collection: per-collection-result}``.

    ``configs=None`` discovers all on-disk v2 collections. Matches v1's
    ``search`` signature/defaults so the facade can route to it unchanged.
    """
    if max_docs is None:
        max_docs = resolve_search_config().max_docs
    if max_chunks is None:
        max_chunks = max_docs * 3

    base = collections_base(collections_path)
    if configs is None:
        names = discover_v2_collections(base)
    else:
        names = [cfg.name for cfg in configs]

    # One embed model per distinct model name, reused across collections.
    embed_cache: Dict[str, "BaseEmbedding"] = {}
    results: Dict[str, Any] = {}
    for name in names:
        try:
            results[name] = _search_one(
                base,
                name,
                query,
                max_docs=max_docs,
                max_chunks=max_chunks,
                score_threshold=score_threshold,
                include_matched_chunks=include_matched_chunks,
                embed_cache=embed_cache,
            )
        except Exception as exc:  # per-collection failure never aborts the rest
            logger.error(f"Error searching v2 collection {name}: {exc}")
            results[name] = {"error": str(exc)}
    return results


def _get_embed_model(
    model_name: str, embed_cache: Dict[str, "BaseEmbedding"]
) -> "BaseEmbedding":
    if model_name not in embed_cache:
        from indexed.core.v2.config_models import CoreV2EmbeddingConfig
        from indexed.core.v2.embedding.local import build_embed_model

        embed_cache[model_name] = build_embed_model(
            CoreV2EmbeddingConfig(model_name=model_name)
        )
    return embed_cache[model_name]


def _search_one(
    base: Path,
    name: str,
    query: str,
    *,
    max_docs: int,
    max_chunks: int,
    score_threshold: Optional[float],
    include_matched_chunks: bool,
    embed_cache: Dict[str, "BaseEmbedding"],
) -> Dict[str, Any]:
    from llama_index.core import load_index_from_storage

    from indexed.core.v2.manifest import V2Manifest
    from indexed.core.v2.stores import load_storage_context

    collection_dir = base / name
    raw = json.loads((collection_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest = V2Manifest.from_disk(raw)

    embed_model = _get_embed_model(manifest.engine.embedding.model, embed_cache)
    storage_context = load_storage_context(collection_dir / "storage", manifest)
    index = load_index_from_storage(storage_context, embed_model=embed_model)

    node_count = len(index.docstore.docs)
    fetch_k = max(max_chunks, min(node_count, _OVERFETCH_CEILING)) if node_count else 1
    fetch_k = max(fetch_k, 1)

    retriever = index.as_retriever(similarity_top_k=fetch_k, embed_model=embed_model)
    nodes_with_scores: List["NodeWithScore"] = retriever.retrieve(query)

    if score_threshold is not None:
        nodes_with_scores = [
            nws
            for nws in nodes_with_scores
            if (nws.score if nws.score is not None else 0.0) >= score_threshold
        ]

    results = _group_by_document(
        nodes_with_scores,
        max_docs=max_docs,
        max_chunks=max_chunks,
        include_matched_chunks=include_matched_chunks,
    )
    return {
        "collectionName": name,
        "indexerName": manifest.engine.embedding.model,
        "results": results,
    }


def _group_by_document(
    nodes_with_scores: List["NodeWithScore"],
    *,
    max_docs: int,
    max_chunks: int,
    include_matched_chunks: bool,
) -> List[Dict[str, Any]]:
    """Group ranked chunk nodes into documents (v1 ``__build_results`` semantics).

    New documents are admitted up to ``max_docs`` (never blocked by the chunk
    cap — that would reintroduce A5's starvation); enrichment chunks for an
    already-admitted document are capped by ``max_chunks``.
    """
    result: Dict[str, Dict[str, Any]] = {}
    total_chunks = 0

    for nws in nodes_with_scores:
        if len(result) >= max_docs and total_chunks >= max_chunks:
            break

        node = nws.node
        meta = dict(node.metadata or {})
        source_id = meta.get("source_id") or node.node_id
        url = meta.get("url", "")
        chunk = {
            "chunkNumber": meta.get("chunk_number", 0),
            "score": float(nws.score) if nws.score is not None else 0.0,
        }
        if include_matched_chunks:
            chunk["content"] = {"indexedData": node.get_content()}

        if source_id not in result:
            if len(result) >= max_docs:
                continue
            result[source_id] = {
                "id": source_id,
                "url": url,
                "path": url,
                "matchedChunks": [chunk],
            }
            total_chunks += 1
        else:
            if total_chunks >= max_chunks:
                continue
            result[source_id]["matchedChunks"].append(chunk)
            total_chunks += 1

    return list(result.values())


__all__ = ["search"]
