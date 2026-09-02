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

``include_full_text``/``include_all_chunks`` match v1's result shape (R4 parity):
v2 has no on-disk ``documents/<id>.json``, so both are reconstructed from the
docstore nodes of each matched document (grouped by ``source_id``, ordered by
``chunk_number``) — ``text`` = the chunk contents concatenated, ``allChunks`` =
every chunk of the matched document (not only the matched ones), each in v1's
``{"indexedData": ...}`` shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from loguru import logger

from indexed.core.v2._common import (
    collections_base,
    discover_v2_collections,
    resolve_rerank_config,
    resolve_search_config,
)

if TYPE_CHECKING:
    from llama_index.core.base.embeddings.base import BaseEmbedding
    from llama_index.core.schema import NodeWithScore

    from indexed.core.v2.config_models import CoreV2RerankConfig
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
    rerank: Optional[bool] = None,
) -> Dict[str, Any]:
    """Search v2 collections; return ``{collection: per-collection-result}``.

    ``configs=None`` discovers all on-disk v2 collections. Matches v1's
    ``search`` signature/defaults so the facade can route to it unchanged.
    ``rerank``, when not ``None``, overrides ``[core.v2.rerank] enabled`` for
    this call only (CLI ``--rerank``/``--no-rerank``, R2) without touching the
    stored config.
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

    # Resolve the (opt-in) rerank config ONCE per search — same for every
    # collection. Disabled by default: no CrossEncoder is imported or loaded
    # unless ``[core.v2.rerank] enabled=true`` (R10, zero cost when off).
    rerank_cfg = resolve_rerank_config()
    if rerank is not None:
        # Per-call override (immutable update — never mutates the shared,
        # possibly-cached config instance).
        rerank_cfg = rerank_cfg.model_copy(update={"enabled": rerank})

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
                include_full_text=include_full_text,
                include_all_chunks=include_all_chunks,
                embed_cache=embed_cache,
                rerank_cfg=rerank_cfg,
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


def _apply_rerank(
    nodes_with_scores: List["NodeWithScore"],
    query: str,
    rerank_cfg: "CoreV2RerankConfig",
) -> List["NodeWithScore"]:
    """Rerank retrieved nodes with a cross-encoder, keeping ``top_n`` (R10).

    Imports are FUNCTION-LOCAL and reached ONLY when rerank is enabled, so a
    disabled search never imports ``SentenceTransformerRerank`` or the
    ``CrossEncoder`` it loads (zero cost, proven by a lazy-import probe). The
    postprocessor is passed the query and nodes EXPLICITLY — ``Settings`` is
    never touched (retriever-only contract).
    """
    from llama_index.core.postprocessor import SentenceTransformerRerank

    reranker = SentenceTransformerRerank(model=rerank_cfg.model, top_n=rerank_cfg.top_n)
    return reranker.postprocess_nodes(nodes_with_scores, query_str=query)


def _search_one(
    base: Path,
    name: str,
    query: str,
    *,
    max_docs: int,
    max_chunks: int,
    score_threshold: Optional[float],
    include_matched_chunks: bool,
    include_full_text: bool,
    include_all_chunks: bool,
    embed_cache: Dict[str, "BaseEmbedding"],
    rerank_cfg: "CoreV2RerankConfig",
) -> Dict[str, Any]:
    from llama_index.core import load_index_from_storage

    from indexed.core.v2.manifest import RERANK_SCORE_KIND, V2Manifest
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
        # Threshold is a COSINE cutoff (the retriever's score kind), so it is
        # applied to the vector-similarity scores BEFORE any rerank replaces
        # them with cross-encoder scores.
        nodes_with_scores = [
            nws
            for nws in nodes_with_scores
            if (nws.score if nws.score is not None else 0.0) >= score_threshold
        ]

    if rerank_cfg.enabled:
        nodes_with_scores = _apply_rerank(nodes_with_scores, query, rerank_cfg)

    # Full-text/all-chunks reconstruction needs every chunk of a matched doc,
    # not just the retrieved ones — grouped from the docstore by source_id
    # (only built when requested, so the common path pays nothing).
    docs_by_source = (
        _docs_by_source(index) if (include_full_text or include_all_chunks) else None
    )

    results = _group_by_document(
        nodes_with_scores,
        max_docs=max_docs,
        max_chunks=max_chunks,
        include_matched_chunks=include_matched_chunks,
        include_full_text=include_full_text,
        include_all_chunks=include_all_chunks,
        docs_by_source=docs_by_source,
    )
    # Reranking REPLACES each NodeWithScore.score with a cross-encoder
    # relevance, so the manifest's cosine score_kind no longer describes it
    # (PR #158 review #8) — report the distinct rerank kind instead.
    score_kind = RERANK_SCORE_KIND if rerank_cfg.enabled else manifest.engine.score_kind
    return {
        "collectionName": name,
        "indexerName": manifest.engine.embedding.model,
        "scoreKind": score_kind,
        "results": results,
    }


def _docs_by_source(index: Any) -> Dict[str, List[Any]]:
    """Group every docstore node by ``source_id``, ordered by ``chunk_number``.

    The basis for reconstructing v1's ``text``/``allChunks`` (v2 keeps no
    ``documents/<id>.json``, so the docstore nodes are the source of truth).
    """
    grouped: Dict[str, List[Any]] = {}
    for node in index.docstore.docs.values():
        meta = node.metadata or {}
        source_id = meta.get("source_id")
        if source_id is None:
            continue
        grouped.setdefault(source_id, []).append(node)
    for nodes in grouped.values():
        nodes.sort(key=lambda n: (n.metadata or {}).get("chunk_number", 0))
    return grouped


def _group_by_document(
    nodes_with_scores: List["NodeWithScore"],
    *,
    max_docs: int,
    max_chunks: int,
    include_matched_chunks: bool,
    include_full_text: bool = False,
    include_all_chunks: bool = False,
    docs_by_source: Optional[Dict[str, List[Any]]] = None,
) -> List[Dict[str, Any]]:
    """Group ranked chunk nodes into documents (v1 ``__build_results`` semantics).

    New documents are admitted up to ``max_docs`` (never blocked by the chunk
    cap — that would reintroduce A5's starvation); enrichment chunks for an
    already-admitted document are capped by ``max_chunks``. When requested,
    ``text``/``allChunks`` are attached ON FIRST ADMISSION of a document (v1
    attaches them the same way), reconstructed from ``docs_by_source``.
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
            entry: Dict[str, Any] = {
                "id": source_id,
                "url": url,
                "path": url,
                "matchedChunks": [chunk],
            }
            _attach_document_content(
                entry,
                source_id,
                docs_by_source,
                include_full_text=include_full_text,
                include_all_chunks=include_all_chunks,
            )
            result[source_id] = entry
            total_chunks += 1
        else:
            if total_chunks >= max_chunks:
                continue
            result[source_id]["matchedChunks"].append(chunk)
            total_chunks += 1

    return list(result.values())


def _attach_document_content(
    entry: Dict[str, Any],
    source_id: str,
    docs_by_source: Optional[Dict[str, List[Any]]],
    *,
    include_full_text: bool,
    include_all_chunks: bool,
) -> None:
    """Attach v1-shaped ``text``/``allChunks`` for a matched document (R4 parity).

    ``text`` = the document's chunk contents concatenated (v2 keeps no original
    full-text blob); ``allChunks`` = every chunk of the document (all chunks,
    not only the matched ones) in v1's on-disk chunk shape.
    """
    if not (include_full_text or include_all_chunks) or docs_by_source is None:
        return
    nodes = docs_by_source.get(source_id, [])
    if include_full_text:
        entry["text"] = "\n".join(n.get_content() for n in nodes)
    if include_all_chunks:
        entry["allChunks"] = [_chunk_dict(n) for n in nodes]


def _chunk_dict(node: Any) -> Dict[str, Any]:
    """One v1-shaped ``allChunks`` element from a docstore node.

    v1's ``allChunks`` are the on-disk ConvertedDocument chunk dicts:
    ``{"indexedData": <text>}`` plus a ``metadata`` key only when the chunk
    carried its own metadata (``Chunk.to_disk`` drops ``None``). The adapter
    merged that original per-chunk metadata INTO the node alongside the
    engine-owned keys, so we recover it by stripping ``RESERVED_METADATA_KEYS``.
    """
    from indexed.core.v2.adapter import RESERVED_METADATA_KEYS

    chunk: Dict[str, Any] = {"indexedData": node.get_content()}
    original = {
        k: v
        for k, v in (node.metadata or {}).items()
        if k not in RESERVED_METADATA_KEYS
    }
    if original:
        chunk["metadata"] = original
    return chunk


__all__ = ["search"]
