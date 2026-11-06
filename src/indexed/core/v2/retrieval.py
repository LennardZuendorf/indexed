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

import contextlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, List, Optional

from loguru import logger

from indexed.core.v2._common import (
    collections_base,
    discover_v2_collections,
    resolve_rerank_config,
    resolve_search_config,
)
from indexed.utils import git_meta

if TYPE_CHECKING:
    from llama_index.core.base.embeddings.base import BaseEmbedding
    from llama_index.core.schema import NodeWithScore

    from indexed.core.v2.config_models import CoreV2RerankConfig
    from indexed.core.v2.manifest import V2Manifest
    from indexed.protocols import SourceConfig

# Upper bound on retrieved chunks so doc-grouping isn't starved by one dominant
# document filling the top-k (v1 bug A5). Brute-force cosine at <100k chunks is
# cheap, so a larger fetch just bounds the worst case.
_OVERFETCH_CEILING = 10_000

# Readers whose ``source_id`` is a path under ``basePath`` — the only ones a git
# pathspec can be derived for (both spellings exist in the wild).
_FILES_READER_TYPES = frozenset({"localFiles", "files"})

# Why a requested ``changed_since`` filter was not applied. A skipped filter is
# NEVER silent: the collection's result carries these in ``gitFilter`` so the
# CLI and MCP surfaces can say "these rows are unfiltered" (#279 review).
_FILTER_NOT_FILES = "not-a-files-collection"
_FILTER_NO_REPO = "no-git-repository"
_FILTER_UNKNOWN_REF = "unknown-ref"

# Reported as ``scoreKind`` when the git-signal re-rank has blended the raw
# cosine score into a ranked one (#144) — mirrors ``RERANK_SCORE_KIND``: once the
# score is no longer a pure cosine, the manifest's kind no longer describes it.
GIT_RERANK_SCORE_KIND = "git-rerank"

# Candidates scored per collection. Git facts cost one blame + one rev-list per
# distinct document, so the window bounds subprocess work on a broad candidate
# set (``fetch_k`` can reach ``_OVERFETCH_CEILING``); candidates beyond it keep
# their cosine score and their relative order behind the scored ones.
_GIT_RERANK_WINDOW = 50

_SECONDS_PER_DAY = 86_400.0


@dataclass(frozen=True)
class GitRerankOptions:
    """Weights for the opt-in git-signal re-rank (#144), from ``[core.v1.search]``.

    Query-time only: every input is derived from git on each search, so nothing
    is persisted and a re-index is never required. The score blend is
    ``cosine + recency_weight*recency + churn_weight*churn + author_weight*author``
    with each signal in ``[0, 1]``; a signal git cannot answer contributes
    NOTHING (no fabricated value), and a chunk with no answerable signal at all
    keeps its cosine score untouched.
    """

    recency_weight: float = 0.10
    churn_weight: float = 0.05
    # A name/email substring; ``None`` (the default) disables ownership entirely.
    author: Optional[str] = None
    author_weight: float = 0.05
    # Half-life of the recency decay: a line touched this long ago scores 0.5.
    half_life_days: float = 30.0
    # Churn window and the commit count that saturates the churn signal.
    churn_window_days: int = 90
    churn_cap: int = 20


@dataclass
class _GitContext:
    """One collection's repo, resolved once per search (never cached globally)."""

    repo: str
    base_path: str
    commits: Dict[str, Optional[Dict[str, str]]] = field(default_factory=dict)
    # Per-path blame, memoized for the same reason as ``commits``: a multi-chunk
    # document pays ONE ``git blame``, not one per matched chunk.
    blames: Dict[str, Optional[List[Optional[Dict[str, Any]]]]] = field(
        default_factory=dict
    )
    # Churn input, memoized per path for the same reason: one ``rev-list`` per
    # candidate document, never one per chunk.
    churn: Dict[str, Optional[int]] = field(default_factory=dict)

    def relative(self, source_id: str) -> str:
        return git_meta.repo_relative(self.repo, self.base_path, source_id)

    def is_changed(self, node: Any, changed: FrozenSet[str]) -> bool:
        source_id = (node.metadata or {}).get("source_id")
        return source_id is not None and self.relative(str(source_id)) in changed

    def last_commit(self, source_id: str) -> Optional[Dict[str, str]]:
        """Memoized per (repo, path): at most one ``git log`` per admitted doc."""
        if source_id not in self.commits:
            self.commits[source_id] = git_meta.last_commit(
                self.repo, self.relative(source_id)
            )
        return self.commits[source_id]

    def blame_lines(self, source_id: str) -> Optional[List[Optional[Dict[str, Any]]]]:
        """Memoized per (repo, path): at most one ``git blame`` per admitted doc."""
        if source_id not in self.blames:
            self.blames[source_id] = git_meta.blame_lines(
                self.repo, self.relative(source_id)
            )
        return self.blames[source_id]

    def commits_since(self, source_id: str, since_epoch: int) -> Optional[int]:
        """Memoized per (repo, path): one ``rev-list --count`` per candidate doc."""
        if source_id not in self.churn:
            self.churn[source_id] = git_meta.recent_commit_count(
                self.repo, self.relative(source_id), since_epoch
            )
        return self.churn[source_id]


def _git_context(manifest: "V2Manifest") -> Optional[_GitContext]:
    """Git context for a files collection, or ``None`` when it can't be resolved.

    A non-files reader, a missing ``basePath`` or a non-repo all resolve to
    ``None``: both query-time git options are files-collections-only by design.
    """
    if manifest.reader.type not in _FILES_READER_TYPES:
        return None
    base_path = (manifest.reader.model_extra or {}).get("basePath")
    if not isinstance(base_path, str) or not base_path:
        return None
    repo = git_meta.repo_toplevel(base_path)
    if repo is None:
        return None
    return _GitContext(repo=repo, base_path=base_path)


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
    changed_since: Optional[str] = None,
    git_provenance: Optional[bool] = None,
    git_line_blame: Optional[bool] = None,
    git_rerank: Optional[GitRerankOptions] = None,
) -> Dict[str, Any]:
    """Search v2 collections; return ``{collection: per-collection-result}``.

    ``configs=None`` discovers all on-disk v2 collections. Matches v1's
    ``search`` signature/defaults so the facade can route to it unchanged.
    ``rerank``, when not ``None``, overrides ``[core.v2.rerank] enabled`` for
    this call only (CLI ``--rerank``/``--no-rerank``, R2) without touching the
    stored config. ``changed_since`` keeps only nodes whose file changed since
    that git ref (uncommitted work included); ``git_provenance`` attaches the
    last-touching commit per result document. ``git_line_blame`` additionally
    attributes each matched chunk to the commit that last touched the lines it
    covers, for chunks whose parser recorded a line span. ``git_rerank``
    (``None`` = off, no git work at all) re-ranks the candidate chunks by git
    recency/churn/ownership before grouping, blending those signals into the
    score. All four apply to files collections only and are no-ops when git
    can't answer (#60/#144/#146).
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
                changed_since=changed_since,
                git_provenance=git_provenance,
                git_line_blame=git_line_blame,
                git_rerank=git_rerank,
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
    never touched (retriever-only contract). Construction and inference are
    wrapped so a raw HF-Hub/transformers stdout write (issue #186) can't
    corrupt ``--simple-output`` JSON — it lands on stderr instead.
    """
    from llama_index.core.postprocessor import SentenceTransformerRerank

    with contextlib.redirect_stdout(sys.stderr):
        reranker = SentenceTransformerRerank(
            model=rerank_cfg.model, top_n=rerank_cfg.top_n
        )
        return reranker.postprocess_nodes(nodes_with_scores, query_str=query)


def _recency_score(
    touch: Dict[str, Any], now_epoch: float, half_life_days: float
) -> float:
    """Exponential decay on the chunk's newest touch: 1.0 now, 0.5 in one half-life.

    A working-tree line is the freshest possible touch (1.0) and has no epoch.
    A missing/zero epoch scores 0.0 — an old commit is a real answer, but an
    unknown one must not look fresh.
    """
    if touch.get("uncommitted"):
        return 1.0
    epoch = touch.get("epoch")
    if not isinstance(epoch, int) or epoch <= 0 or half_life_days <= 0:
        return 0.0
    age_days = max(0.0, (now_epoch - epoch) / _SECONDS_PER_DAY)
    return 0.5 ** (age_days / half_life_days)


def _author_matches(touch: Dict[str, Any], author: str) -> bool:
    """True when the touching commit's author name or email contains ``author``."""
    wanted = author.strip().lower()
    if not wanted:
        return False
    return (
        wanted in str(touch.get("author", "")).lower()
        or wanted in str(touch.get("email", "")).lower()
    )


def _signal_boost(
    git_ctx: _GitContext,
    source_id: str,
    meta: Dict[str, Any],
    options: GitRerankOptions,
    now_epoch: float,
) -> Optional[float]:
    """The additive git boost for one candidate chunk, or ``None`` if unknowable.

    Recency and ownership come from the chunk's line span (falling back to the
    document's newest line when the chunk recorded no span); churn is the
    document's commit count inside the churn window, which is the chunk's own
    history too — a chunk cannot outlive the file it lives in. Each signal
    contributes only when git ANSWERED it; ``None`` means no signal at all, so
    the caller leaves the cosine score exactly as it was.
    """
    since = int(now_epoch - options.churn_window_days * _SECONDS_PER_DAY)
    touch = git_meta.newest_touch(
        git_ctx.blame_lines(source_id), meta.get("start_line"), meta.get("end_line")
    )
    churn_count = git_ctx.commits_since(source_id, since)
    if touch is None and churn_count is None:
        return None

    boost = 0.0
    if touch is not None:
        boost += options.recency_weight * _recency_score(
            touch, now_epoch, options.half_life_days
        )
        if options.author and _author_matches(touch, options.author):
            boost += options.author_weight
    if churn_count is not None:
        cap = max(options.churn_cap, 1)
        boost += options.churn_weight * min(churn_count / cap, 1.0)
    return boost


def _apply_git_rerank(
    nodes_with_scores: List["NodeWithScore"],
    git_ctx: "_GitContext",
    options: GitRerankOptions,
    now_epoch: Optional[float] = None,
) -> tuple[List["NodeWithScore"], int]:
    """Blend git signals into the candidate scores, then reorder (#144).

    Runs AFTER retrieval and BEFORE document grouping/output — and BEFORE the
    cross-encoder when that is enabled, so the cross-encoder keeps ownership of
    the final score and the git blend only decides which candidates reach its
    ``top_n``. Git facts feed SCORING only — never the embedding, never the
    vector store, nothing persisted. Only the first ``_GIT_RERANK_WINDOW``
    candidates are scored (the cost bound), and the sort is stable, so equal
    blends keep their retrieval order. Returns ``(ordered_nodes, scored)`` where
    ``scored`` counts the candidates that got a real git answer.
    """
    now = time.time() if now_epoch is None else now_epoch
    window = nodes_with_scores[:_GIT_RERANK_WINDOW]
    tail = nodes_with_scores[_GIT_RERANK_WINDOW:]
    rescored: List["NodeWithScore"] = []
    scored = 0
    for nws in window:
        meta = nws.node.metadata or {}
        source_id = meta.get("source_id")
        boost = (
            _signal_boost(git_ctx, str(source_id), meta, options, now)
            if source_id is not None
            else None
        )
        if boost is None:
            rescored.append(nws)
            continue
        scored += 1
        base = float(nws.score) if nws.score is not None else 0.0
        rescored.append(nws.model_copy(update={"score": base + boost}))
    rescored.sort(key=lambda nws: float(nws.score or 0.0), reverse=True)
    return rescored + tail, scored


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
    changed_since: Optional[str],
    git_provenance: Optional[bool],
    git_line_blame: Optional[bool],
    git_rerank: Optional[GitRerankOptions],
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

    # Query-time git awareness: ONE repo resolution per collection shared by all
    # four options, and a git problem skips the feature rather than emptying
    # results — but the skip is REPORTED in ``gitFilter``/``gitRerank``, never a
    # silent unfiltered or unranked set.
    git_ctx = (
        _git_context(manifest)
        if (
            changed_since is not None
            or git_provenance
            or git_line_blame
            or git_rerank is not None
        )
        else None
    )

    # Git-signal re-rank (#144): after retrieval/threshold (cosine space) and
    # before grouping, so the ORDER the groupers see is the ranked one. It runs
    # BEFORE the cross-encoder when that is enabled, so the cross-encoder still
    # owns the final score: the git pass only decides which candidates reach
    # its ``top_n`` (it cannot, and does not, survive as a blended score there).
    git_rerank_status: Optional[Dict[str, Any]] = None
    if git_rerank is not None:
        if manifest.reader.type not in _FILES_READER_TYPES:
            git_rerank_status = _rerank_not_applied(name, _FILTER_NOT_FILES)
        elif git_ctx is None:
            git_rerank_status = _rerank_not_applied(name, _FILTER_NO_REPO)
        else:
            nodes_with_scores, scored = _apply_git_rerank(
                nodes_with_scores, git_ctx, git_rerank
            )
            git_rerank_status = {"applied": True, "scored": scored}

    if rerank_cfg.enabled:
        nodes_with_scores = _apply_rerank(nodes_with_scores, query, rerank_cfg)

    git_filter: Optional[Dict[str, Any]] = None
    if changed_since is not None:
        if manifest.reader.type not in _FILES_READER_TYPES:
            git_filter = _filter_not_applied(name, changed_since, _FILTER_NOT_FILES)
        elif git_ctx is None:
            git_filter = _filter_not_applied(name, changed_since, _FILTER_NO_REPO)
        else:
            changed = git_meta.changed_paths(git_ctx.repo, changed_since)
            if changed is None:
                git_filter = _filter_not_applied(
                    name, changed_since, _FILTER_UNKNOWN_REF
                )
            else:
                # Before grouping, so max_docs is filled by survivors, not starved.
                nodes_with_scores = [
                    nws
                    for nws in nodes_with_scores
                    if git_ctx.is_changed(nws.node, changed)
                ]
                git_filter = {"ref": changed_since, "applied": True}

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
        git_context=git_ctx if git_provenance else None,
        line_git_context=git_ctx if git_line_blame else None,
    )
    # Reranking REPLACES each NodeWithScore.score with a cross-encoder
    # relevance, so the manifest's cosine score_kind no longer describes it
    # (PR #158 review #8) — report the distinct rerank kind instead. The git
    # re-rank likewise replaces cosine with a blended score (#144), but only
    # when it actually scored something.
    if rerank_cfg.enabled:
        score_kind = RERANK_SCORE_KIND
    elif git_rerank_status is not None and git_rerank_status.get("scored"):
        score_kind = GIT_RERANK_SCORE_KIND
    else:
        score_kind = manifest.engine.score_kind
    out: Dict[str, Any] = {
        "collectionName": name,
        "indexerName": manifest.engine.embedding.model,
        "scoreKind": score_kind,
        "results": results,
    }
    if git_filter is not None:
        # Present only when ``changed_since`` was requested: the caller can then
        # tell a filtered result set from a skipped filter instead of guessing.
        out["gitFilter"] = git_filter
    if git_rerank_status is not None:
        out["gitRerank"] = git_rerank_status
    return out


def _filter_not_applied(name: str, ref: str, reason: str) -> Dict[str, Any]:
    """``gitFilter`` status for a requested filter this collection can't honour.

    Logged at WARNING (a visible degrade, not a debug whisper) and carried into
    the result so ``mcp/formatting.py`` / the CLI renderers can name both the
    collection and the ref (#279 review, finding 1).
    """
    logger.warning(
        f"changed_since={ref!r} was not applied to collection {name!r} ({reason}); "
        "its results are unfiltered"
    )
    return {"ref": ref, "applied": False, "reason": reason}


def _rerank_not_applied(name: str, reason: str) -> Dict[str, Any]:
    """``gitRerank`` status for a requested re-rank this collection can't honour.

    Same visible-degrade rule as ``gitFilter`` (#279 review, finding 1): a
    requested re-rank that could not run is announced at WARNING and carried
    into the result, so the CLI and MCP can say "these rows are unranked".
    """
    logger.warning(
        f"git re-ranking was not applied to collection {name!r} ({reason}); "
        "its results are ordered by similarity only"
    )
    return {"applied": False, "reason": reason}


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
    git_context: Optional[_GitContext] = None,
    line_git_context: Optional[_GitContext] = None,
) -> List[Dict[str, Any]]:
    """Group ranked chunk nodes into documents (v1 ``__build_results`` semantics).

    New documents are admitted up to ``max_docs`` (never blocked by the chunk
    cap — that would reintroduce A5's starvation); enrichment chunks for an
    already-admitted document are capped by ``max_chunks``. When requested,
    ``text``/``allChunks`` are attached ON FIRST ADMISSION of a document (v1
    attaches them the same way), reconstructed from ``docs_by_source``.
    ``git_context`` likewise attaches the document's last-touching commit as
    ``entry["git"]`` on first admission, and only when git answered.
    ``line_git_context`` adds ``chunk["git"]`` — the commit that last touched
    that chunk's own line span — whenever the chunk carries ``start_line``/
    ``end_line`` metadata and blame can answer for that span.
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
            if git_context is not None:
                provenance = git_context.last_commit(str(source_id))
                if provenance is not None:
                    entry["git"] = provenance
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

        # Only ADMITTED chunks pay for blame: the memoized per-path call is
        # bounded by admitted documents (≤ max_docs), not by fetched nodes or
        # matched chunks. The dict is already in the result list, so mutating
        # it here still lands in the output.
        if line_git_context is not None:
            line_git = _line_provenance(line_git_context, str(source_id), meta)
            if line_git is not None:
                chunk["git"] = line_git

    return list(result.values())


def _line_provenance(
    git_context: _GitContext, source_id: str, meta: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """The commit that last touched this chunk's own line span, or ``None``.

    Only chunks whose parser recorded the span (``start_line``/``end_line``,
    0-based, inclusive — see ``parsing/code_chunker.py``) can be attributed
    line-by-line; anything else stays absent rather than borrowing the
    document's whole-file commit. Blame is memoized per path in
    ``_GitContext``, so the cost is one call per admitted document.
    """
    start_line = meta.get("start_line")
    end_line = meta.get("end_line")
    if not isinstance(start_line, int) or not isinstance(end_line, int):
        return None
    return git_meta.resolve_range(
        git_context.blame_lines(source_id), start_line, end_line
    )


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


__all__ = ["GIT_RERANK_SCORE_KIND", "GitRerankOptions", "search"]
