"""Native HuggingFaceEmbedding factory + dimension probe for core.v2 (core-v2/2b).

The embed model built here is injected EXPLICITLY everywhere (ingestion /
retrieval pass it per call) — LlamaIndex's ``Settings`` global is never read or
written (tech.md "No global state").

Laziness (tech.md): ``llama_index.embeddings.huggingface`` imports torch and
sentence-transformers at module top, so the integration import lives INSIDE
``build_embed_model``; importing this module stays cheap (keeps ``indexed
--help`` <1s). Only a ``TYPE_CHECKING`` import of the typed ``BaseEmbedding``
base (from the ``py.typed`` core package) sits at module level, for annotations.

Offline / shared-cache handling (R8/R12 — the landmine): the integration
defaults ``cache_folder`` to LlamaIndex's OWN cache dir
(``~/.cache/llama_index``), NOT the HuggingFace hub cache where v1 already
stored the model — so left to its default it MISSES the cached model and hits
the network (empirically verified: it then re-creates a raw mean-pooling model
and attempts a download). We therefore always pass ``cache_folder`` = the HF
hub cache (v1's shared cache, resolved exactly like ``model_manager``), and add
``local_files_only=True`` when the model is already cached so no etag/revision
network probe fires. Proven by a socket-guarded test: a cached model loads and
embeds with zero outbound connections.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llama_index.core.base.embeddings.base import BaseEmbedding

    from indexed.core.v2.config_models import CoreV2EmbeddingConfig

# One short string embedded once to discover the vector dimension at create
# time — LlamaIndex exposes no dimension API (tech.md "Dimension discovery").
PROBE_STRING = "probe"

_ST_ORG = "sentence-transformers"


def _hf_hub_cache_dir() -> Path:
    """The active HuggingFace Hub cache dir (v1's shared cache).

    Same resolution v1's ``model_manager`` uses (``HF_HUB_CACHE`` >
    ``HF_HOME/hub`` > ``~/.cache/huggingface/hub``) so v2 reuses the exact cache
    v1 populated — no re-download, identical vectors. Replicated (not imported)
    because ``core.v2`` may not import ``core.v1``.
    """
    if env := os.environ.get("HF_HUB_CACHE"):
        return Path(env)
    hf_home = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
    return Path(hf_home) / "hub"


def _is_model_cached(model_name: str) -> bool:
    """True when ``model_name`` is already in the HF hub cache (pure path check).

    Mirrors ``model_manager.is_model_cached`` exactly (so it agrees with the
    suite's ``model_available`` gate) without importing ``core.v1`` or any heavy
    library.
    """
    repo_id = model_name if "/" in model_name else f"{_ST_ORG}/{model_name}"
    model_dir = _hf_hub_cache_dir() / f"models--{repo_id.replace('/', '--')}"
    snapshots = model_dir / "snapshots"
    if not snapshots.is_dir():
        return False
    return any(s.is_dir() and any(s.iterdir()) for s in snapshots.iterdir())


def build_embed_model(config: "CoreV2EmbeddingConfig") -> "BaseEmbedding":
    """Build the native embedding for ``config`` (v1's model, 1:1 vectors).

    ``model_name`` is passed EXPLICITLY (the integration's own default is a
    different model); ``normalize=True`` matches v1's unit-normalized vectors;
    ``cache_folder`` is pinned to the shared HF hub cache. See the module
    docstring for the offline/shared-cache handling.
    """
    # Function-local: importing the integration pulls torch +
    # sentence-transformers in at module top (tech.md laziness contract).
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    # ``local_files_only`` is forwarded (via the integration's ``**model_kwargs``)
    # to SentenceTransformer. Cached → ``True`` forbids the etag/revision network
    # probe (offline, R8/R12). Not cached → ``False`` (the default) lets a first
    # run download into the shared cache. Passing the bool unconditionally is
    # equivalent to conditionally omitting it and keeps ty's kwargs check clean.
    return HuggingFaceEmbedding(
        model_name=config.model_name,
        embed_batch_size=config.batch_size,
        normalize=True,
        cache_folder=str(_hf_hub_cache_dir()),
        local_files_only=_is_model_cached(config.model_name),
    )


def probe_dimension(embed_model: "BaseEmbedding") -> int:
    """Return the embedding dimension by embedding one probe string.

    Recorded as ``engine.embedding.dimension`` at create time by core-v2/2c
    (384 for the default all-MiniLM-L6-v2 model).
    """
    return len(embed_model.get_text_embedding(PROBE_STRING))


__all__ = ["PROBE_STRING", "build_embed_model", "probe_dimension"]
