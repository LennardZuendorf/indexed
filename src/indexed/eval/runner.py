"""Run the pinned eval set against a real collection (issue #204).

Two things make the numbers trustworthy rather than decorative:

1. **The corpus is pinned and hashed.** ``eval/corpus/`` ships in the repo and
   ``eval/corpus.json`` carries a sha256 per file plus a tree hash; the report
   names the revision it measured, so two reports are only comparable when the
   tree hash matches.
2. **The retrieval configuration is pinned in the report.** Engine, embedding
   model, score kind, rerank toggle, top-k and max-docs land next to the numbers
   — a model or knob change shows up as configuration, not as an unexplained
   metric drift.

The collection is built into a throwaway directory by default, so a run never
touches ``~/.indexed`` and needs no credentials and no network beyond the local
embedding-model cache.
"""

from __future__ import annotations

import importlib.metadata
import os
import platform
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from indexed.eval.adapter import (
    hits_from_engine_result,
    document_ranking,
    ranking_detail,
)
from indexed.eval.cases import (
    DEFAULT_CASES_PATH,
    DEFAULT_CORPUS_DIR,
    DEFAULT_CORPUS_MANIFEST,
    Case,
    CaseSet,
    EvalDataError,
    corpus_revision,
    load_case_set,
)
from indexed.eval.metrics import aggregate, score_case
from indexed.eval.runtime_config import evaluation_config, source_environment

REPORT_SCHEMA = "indexed.eval.report.v1"
DEFAULT_COLLECTION = "eval-corpus"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_RERANKER = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass(frozen=True)
class RunConfig:
    """The retrieval configuration a report is measured under.

    Every knob is pinned and recorded: ``rerank`` defaults to ``False`` rather
    than "whatever the ambient config says", because an ambient toggle would move
    the numbers while the report still claimed rerank was off.
    """

    collection: str = DEFAULT_COLLECTION
    engine: str = "2"
    top_k: int = 5
    max_docs: int = 10
    rerank: bool = False
    embedding_model: str = DEFAULT_MODEL
    embedding_batch_size: int = 32
    score_threshold: float = 0.0
    reranker_model: str = DEFAULT_RERANKER
    reranker_top_n: int = 10

    def __post_init__(self) -> None:
        """Reject unsupported engine settings and unreachable hit-rate cutoffs."""
        if self.engine == "1" and self.rerank:
            raise ValueError("rerank is only supported by engine '2'")
        if self.engine == "1" and self.embedding_model != DEFAULT_MODEL:
            raise ValueError("engine '1' uses the fixed eval source embedding model")
        if self.top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {self.top_k}")
        if self.max_docs < self.top_k:
            raise ValueError(
                f"max_docs ({self.max_docs}) must be >= top_k ({self.top_k}) — "
                "hit-rate@k is unreachable beyond the returned documents"
            )
        if self.engine not in {"1", "2"}:
            raise ValueError(f"engine must be '1' or '2', got {self.engine!r}")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "collection": self.collection,
            "engine": self.engine,
            "top_k": self.top_k,
            "max_docs": self.max_docs,
            "rerank": self.rerank,
        }


def _files_connector_factory(corpus_dir: Path):
    """Real files connector over the pinned corpus (lazy, like composition.py)."""
    from indexed.connectors.files.connector import FileSystemConnector

    return lambda _config: FileSystemConnector(path=str(corpus_dir))


def build_collection(
    corpus_dir: Path,
    collections_path: Path,
    config: RunConfig,
    *,
    connector_factory: Any = None,
) -> None:
    """Build the eval collection from the pinned corpus, using the facade."""
    from indexed.core import engine
    from indexed.protocols.models import SourceConfig

    source = SourceConfig(
        name=config.collection, type="localFiles", base_url_or_path=str(corpus_dir)
    )
    factory = connector_factory or _files_connector_factory(corpus_dir)
    engine.create(
        [source],
        engine=config.engine,
        use_cache=False,
        collections_path=str(collections_path),
        connector_factory=factory,
    )


def _hf_cache_dir() -> Path:
    """Resolve the Hub cache using HF_HUB_CACHE, HF_HOME, then the home default."""
    explicit = os.environ.get("HF_HUB_CACHE")
    if explicit:
        return Path(explicit)
    home = os.environ.get("HF_HOME")
    if home:
        return Path(home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _model_cache_hint(model: str, *, engine: str = "2") -> Dict[str, Any]:
    """Where the embedding weights come from — recorded so drift is visible.

    Repo-ID loaders require a main reference, config and weights. V1 instead
    loads its selected snapshot path directly and supports orphan snapshots.
    """
    cache = _hf_cache_dir()
    repo_id = model if "/" in model else f"sentence-transformers/{model}"
    slug = "models--" + repo_id.replace("/", "--")
    snapshots = cache / slug / "snapshots"
    weights: List[str] = []
    selected = None
    reference = cache / slug / "refs" / "main"
    if reference.is_file():
        snapshot = snapshots / reference.read_text().strip()
        if snapshot.is_dir():
            selected = snapshot
    elif engine == "1" and snapshots.is_dir():
        selected = next(
            (
                snapshot
                for snapshot in sorted(snapshots.iterdir())
                if snapshot.is_dir()
                and any(
                    (snapshot / name).is_file()
                    for name in ("model.safetensors", "pytorch_model.bin")
                )
            ),
            None,
        )
    if selected is not None and (engine == "1" or (selected / "config.json").is_file()):
        weights = [
            name
            for name in ("model.safetensors", "pytorch_model.bin")
            if (selected / name).is_file()
        ]
    return {
        "cache_dir": str(cache),
        "present": bool(weights),
        "weights": sorted(set(weights)),
        "selected_snapshot": selected.name if selected and weights else None,
        "snapshot_path": str(selected) if selected and weights else None,
    }


def _environment() -> Dict[str, Any]:
    """Record interpreter, platform, installed version and measured source provenance."""
    try:
        version = importlib.metadata.version("indexed-sh")
    except importlib.metadata.PackageNotFoundError:  # pragma: no cover - dev tree
        version = "unknown"
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "indexed_version": version,
        **source_environment(),
    }


def _search_one(
    query: str, collections_path: Path, config: RunConfig
) -> Dict[str, Any]:
    """Search the isolated collection with the pinned retrieval settings."""
    from indexed.core import engine

    return engine.search(
        query,
        configs=None,
        max_docs=config.max_docs,
        include_matched_chunks=True,
        collections_path=str(collections_path),
        rerank=config.rerank,
        score_threshold=(
            config.score_threshold
            if config.engine == "2" or config.score_threshold > 0
            else None
        ),
    )


def _case_record(
    case: Case,
    result: Dict[str, Any],
    config: RunConfig,
    elapsed_ms: float,
) -> Dict[str, Any]:
    """Score one facade response and attach judgments, timing and ranking evidence."""
    hits, error = hits_from_engine_result(result, collection=config.collection)
    ranking = document_ranking(hits)
    record = score_case(
        case_id=case.id,
        query=case.query,
        ranked_doc_ids=ranking,
        relevant=[doc.lower() for doc in case.relevant],
        distractors=[doc.lower() for doc in case.distractors],
        k=config.top_k,
        error=error,
    )
    record.update(
        {
            "provenance": case.provenance,
            "rationale": case.rationale,
            "answered_by": case.answered_by,
            "elapsed_ms": round(elapsed_ms, 3),
            "ranking": ranking_detail(hits, top_k=config.max_docs),
        }
    )
    return record


def run_eval(
    *,
    cases_path: Optional[Path] = None,
    corpus_dir: Optional[Path] = None,
    corpus_manifest: Optional[Path] = None,
    collections_path: Optional[Path] = None,
    config: Optional[RunConfig] = None,
    verify_corpus: bool = True,
    connector_factory: Any = None,
) -> Dict[str, Any]:
    """Build the pinned corpus, run every case, return the report dict."""
    config = config or RunConfig()
    cases_path = Path(cases_path) if cases_path else DEFAULT_CASES_PATH
    corpus_dir = Path(corpus_dir) if corpus_dir else DEFAULT_CORPUS_DIR
    corpus_manifest = (
        Path(corpus_manifest) if corpus_manifest else DEFAULT_CORPUS_MANIFEST
    )

    case_set: CaseSet = load_case_set(cases_path)
    revision = corpus_revision(corpus_dir, corpus_manifest, verify=verify_corpus)
    if case_set.corpus_id != revision["corpus_id"]:
        raise EvalDataError(f"{cases_path}: corpus_id does not match {corpus_manifest}")
    names = {entry["path"].lower() for entry in revision["files"]}
    for case in case_set.cases:
        for field in ("relevant", "distractors"):
            unknown = set(doc.lower() for doc in getattr(case, field)) - names
            if unknown:
                raise EvalDataError(
                    f"{cases_path}: {case.id} {field} documents are not in corpus: {sorted(unknown)}"
                )

    owns_collections = collections_path is None
    workdir: Optional[Path] = None
    if collections_path is None:
        workdir = Path(tempfile.mkdtemp(prefix="indexed-eval-"))
        collections_path = workdir / "collections"
    else:
        collections_path = Path(collections_path)
    collections_path.mkdir(parents=True, exist_ok=True)

    try:
        with evaluation_config(config) as applied_config:
            build_collection(
                corpus_dir,
                collections_path,
                config,
                connector_factory=connector_factory,
            )

            records: List[Dict[str, Any]] = []
            embedding_model = ""
            score_kind = ""
            for case in case_set.cases:
                started = time.perf_counter()
                result = _search_one(case.query, collections_path, config)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                record = _case_record(case, result, config, elapsed_ms)
                records.append(record)
                if not record["error"]:
                    payload = result[config.collection]
                    if config.engine == "2":
                        embedding_model = embedding_model or payload.get(
                            "indexerName", ""
                        )
                    score_kind = score_kind or payload.get("scoreKind", "")
    finally:
        if owns_collections and workdir is not None:
            shutil.rmtree(workdir, ignore_errors=True)

    metrics = aggregate(records, config.top_k)
    failures = [
        {"id": record["id"], "error": record["error"]}
        for record in records
        if record["error"]
    ]
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_set": {
            "path": str(cases_path),
            "sha256": case_set.sha256,
            "description": case_set.description,
            "cases": len(case_set.cases),
        },
        "corpus": revision,
        "config": {
            **applied_config,
            "embedding_model": embedding_model or applied_config["embedding_model"],
            "score_kind": score_kind,
        },
        "environment": {
            **_environment(),
            "embedding_model_cache": _model_cache_hint(
                embedding_model or applied_config["embedding_model"],
                engine=config.engine,
            ),
            **(
                {
                    "reranker_model_cache": _model_cache_hint(
                        applied_config["reranker_model"]
                    )
                }
                if config.rerank
                else {}
            ),
        },
        "metrics": metrics,
        "failures": failures,
        "queries": records,
    }
