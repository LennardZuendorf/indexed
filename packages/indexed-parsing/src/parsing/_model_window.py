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
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from loguru import logger

# Must match `SentenceEmbedder`'s default model name
# (core.v1.engine.indexes.embeddings.sentence_embeder.SentenceEmbedder).
DEFAULT_TOKENIZER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# The model's real max_seq_length (from its `sentence_bert_config.json`) —
# NOT the underlying BERT tokenizer's own `model_max_length` (512). Must be
# kept in sync with `SentenceEmbedder.max_seq_length` for the default model.
DEFAULT_MODEL_MAX_SEQ_LENGTH = 256


@lru_cache(maxsize=1)
def _get_tokenizer() -> Any:
    """Lazily load the default model's tokenizer (heavy; cached for process lifetime)."""
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(DEFAULT_TOKENIZER_MODEL, local_files_only=True)


def count_tokens(text: str) -> int:
    """Return the real token count of *text* under the default embedding tokenizer.

    Falls back to a conservative character estimate if the tokenizer can't be
    loaded (e.g. offline with no cached model) so parsing never crashes.
    """
    if not text:
        return 0
    try:
        return len(_get_tokenizer().encode(text, add_special_tokens=False))
    except Exception:
        logger.opt(exception=True).warning(
            "Tokenizer unavailable for {}; falling back to char-count "
            "estimate (bug A1 may resurface if chunkers stay on this path)",
            DEFAULT_TOKENIZER_MODEL,
        )
        return len(text) // 3 + 1


def effective_max_tokens(requested: int) -> int:
    """Clamp a requested chunk-size budget to the real model window (bug A4)."""
    return min(requested, DEFAULT_MODEL_MAX_SEQ_LENGTH)


def get_markdown_chunker() -> Any:
    """Build the token-aware chunker for Docling documents (markdown / rich docs).

    Uses docling's ``HybridChunker`` wired to the default embedding model's own
    tokenizer, capped at its real ``max_seq_length`` — this is the token-aware
    chunker the ``DoclingParser`` docstring already claimed but the code never
    used (bug A1). Falls back to the old heading-only ``HierarchicalChunker``
    if the tokenizer can't be loaded, so parsing still degrades gracefully
    rather than crashing.
    """
    try:
        from docling_core.transforms.chunker import HybridChunker
        from docling_core.transforms.chunker.tokenizer.huggingface import (
            HuggingFaceTokenizer,
        )

        tokenizer = HuggingFaceTokenizer(
            tokenizer=_get_tokenizer(), max_tokens=DEFAULT_MODEL_MAX_SEQ_LENGTH
        )
        return HybridChunker(tokenizer=tokenizer)
    except Exception:
        logger.opt(exception=True).warning(
            "Token-aware HybridChunker unavailable (tokenizer failed to "
            "load); falling back to unbounded HierarchicalChunker — "
            "markdown chunks may exceed the model window (bug A1)"
        )
        from docling_core.transforms.chunker import HierarchicalChunker

        return HierarchicalChunker()
