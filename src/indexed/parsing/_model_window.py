"""Real token-window helpers shared by the chunkers in this package.

Chunkers must never emit a chunk that tokenizes to more than the embedding
model's real window — see the chunk-size invariant in
``.spec/tech-core.md``. The embedder that owns the
authoritative value (``core.v1...SentenceEmbedder.max_seq_length``) lives in
the core engine package, which this package must not import (see this
package's ``CLAUDE.md``: "MUST NOT import core engine"). So this module loads
the *tokenizer* for the default embedding model directly — a third-party ML
dependency, exactly like the Docling/tree-sitter imports elsewhere in this
package, not "core engine" code — and hardcodes that model's known
``max_seq_length``. This constant MUST be kept in sync with
``SentenceEmbedder``'s default model.

First run on a clean machine: the tokenizer lives in the same HF repository as
the embedding model, but parsing happens BEFORE the embedder that would
download it, so a cache-only load misses. One tokenizer-only download follows;
when that is impossible too, the failure is cached and logged ONCE at WARNING.
The full contract is in ``.spec/tech-parsing.md`` § Token window.
"""

from __future__ import annotations

import os
import threading
import time
from functools import lru_cache
from typing import Any

from loguru import logger

from indexed.utils.logger import enforce_third_party_policy

# Must match `SentenceEmbedder`'s default model name
# (core.v1.engine.indexes.embeddings.sentence_embeder.SentenceEmbedder).
DEFAULT_TOKENIZER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# The model's real max_seq_length (from its `sentence_bert_config.json`) — NOT
# the underlying BERT tokenizer's own `model_max_length` (512). Must be kept
# in sync with `SentenceEmbedder.max_seq_length` for the default model.
DEFAULT_MODEL_MAX_SEQ_LENGTH = 256

_OFFLINE_ENV_VARS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
_OFFLINE_TRUTHY = frozenset({"1", "true", "yes", "on"})

# A concurrent first import of ``transformers`` leaves one thread looking at a
# half-initialised module ("cannot import name 'AutoTokenizer'", issue #335:
# a search racing the watcher catch-up). Serialise our own first import and
# give the other thread one more chance before declaring the install broken.
_IMPORT_LOCK = threading.Lock()
_IMPORT_RETRY_SECONDS = 0.1


def _hub_offline() -> bool:
    """True when the environment forbids Hub network access (both HF vars)."""
    env = (os.environ.get(var, "") for var in _OFFLINE_ENV_VARS)
    return any(value.strip().lower() in _OFFLINE_TRUTHY for value in env)


def _import_auto_tokenizer() -> Any:
    """Import ``AutoTokenizer``, retrying once on ``ImportError`` (issue #335)."""
    with _IMPORT_LOCK:
        try:
            from transformers import AutoTokenizer
        except ImportError:
            # Another thread was first-importing ``transformers``: by the time
            # it finishes, the same import succeeds (a missing package fails
            # again and keeps its own error).
            time.sleep(_IMPORT_RETRY_SECONDS)
            from transformers import AutoTokenizer

    # This import is often the process's FIRST Hub user, so re-assert the
    # single-sink policy here or the Hub notice prints twice (#211).
    enforce_third_party_policy("huggingface_hub")
    return AutoTokenizer


def _load_tokenizer() -> Any:
    """Load the tokenizer from the cache, else download it once (see module)."""
    AutoTokenizer = _import_auto_tokenizer()

    try:
        return AutoTokenizer.from_pretrained(
            DEFAULT_TOKENIZER_MODEL, local_files_only=True
        )
    except Exception:
        if _hub_offline():
            raise
        logger.info("Downloading tokenizer for {} (one-time)", DEFAULT_TOKENIZER_MODEL)
        return AutoTokenizer.from_pretrained(DEFAULT_TOKENIZER_MODEL)


def prewarm_tokenizer() -> bool:
    """Load the tokenizer on the calling thread; return whether it is usable.

    The MCP server warms this before starting watcher threads: the process's
    first ``transformers`` import then finishes on one thread instead of racing
    a search, which used to cache the degraded ``None`` for the whole process
    (issue #335).
    """
    return _get_tokenizer() is not None


@lru_cache(maxsize=1)
def _get_tokenizer() -> Any | None:
    """Load the tokenizer once per process; ``None`` when unavailable.

    The ``None`` is cached on purpose: without it every chunk retried the load
    and logged its own traceback — 40+ stack dumps on a clean first run.
    """
    try:
        return _load_tokenizer()
    except ImportError as exc:
        # `_load_tokenizer` already retried once, so this is not the
        # first-import race (#335): `transformers` itself cannot be imported.
        # The model is irrelevant here, so don't send the user to `indexed init`.
        logger.warning(
            "Tokenizer for {} unavailable ({}); chunks fall back to a"
            " character-count estimate. `transformers` failed to import;"
            " the model cache is not the cause.",
            DEFAULT_TOKENIZER_MODEL,
            type(exc).__name__,
        )
        logger.debug("Tokenizer load failed: {}", exc)
        return None
    except Exception as exc:
        logger.warning(
            "Tokenizer for {} unavailable ({}); chunks fall back to a character-count"
            " estimate. Run `indexed init` to download the model up front.",
            DEFAULT_TOKENIZER_MODEL,
            type(exc).__name__,
        )
        logger.debug("Tokenizer load failed: {}", exc)
        return None


def count_tokens(text: str) -> int:
    """Real token count of *text*, or a char-based estimate without a tokenizer."""
    if not text:
        return 0
    tokenizer = _get_tokenizer()
    if tokenizer is None:
        return len(text) // 3 + 1
    return len(tokenizer.encode(text, add_special_tokens=False))


def effective_max_tokens(requested: int) -> int:
    """Clamp a requested chunk-size budget to the real model window (bug A4)."""
    return min(requested, DEFAULT_MODEL_MAX_SEQ_LENGTH)


def get_markdown_chunker() -> Any:
    """Build the token-aware chunker for Docling documents (markdown / rich docs).

    ``HybridChunker`` wired to the default model's own tokenizer and capped at
    its real ``max_seq_length`` — the token-aware chunker this package always
    claimed but never used (bug A1). Without a tokenizer it degrades to the
    heading-only ``HierarchicalChunker``; ``_get_tokenizer`` logged why.
    """
    tokenizer = _get_tokenizer()
    if tokenizer is not None:
        try:
            from docling_core.transforms.chunker import HybridChunker
            from docling_core.transforms.chunker.tokenizer.huggingface import (
                HuggingFaceTokenizer,
            )

            hf_tokenizer = HuggingFaceTokenizer(
                tokenizer=tokenizer, max_tokens=DEFAULT_MODEL_MAX_SEQ_LENGTH
            )
            return HybridChunker(tokenizer=hf_tokenizer)
        except Exception as exc:
            logger.debug(
                "HybridChunker unavailable ({}); using HierarchicalChunker",
                type(exc).__name__,
            )

    from docling_core.transforms.chunker import HierarchicalChunker

    return HierarchicalChunker()
