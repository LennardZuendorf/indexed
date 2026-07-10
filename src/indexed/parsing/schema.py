"""Data models for the parsing module.

Framework-free dataclasses used as the universal output format for all parsers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import xxhash


@dataclass(frozen=True)
class ParsedChunk:
    """A single chunk produced by a parser.

    Attributes:
        text: Raw content of the chunk.
        contextualized_text: Content prefixed with heading/path context —
            this is what should be embedded.
        metadata: Arbitrary metadata (headings, page numbers, language, …).
        source_type: Indicates how this chunk was produced.
        content_hash: xxhash of ``text`` for deduplication / change detection.
    """

    text: str
    contextualized_text: str
    metadata: dict[str, object] = field(default_factory=dict)
    source_type: Literal["document", "code", "plaintext"] = "plaintext"
    content_hash: str = ""

    def __post_init__(self) -> None:  # noqa: D105 – dunder
        if not self.content_hash:
            object.__setattr__(
                self, "content_hash", xxhash.xxh64(self.text.encode()).hexdigest()
            )


@dataclass
class ParsedDocument:
    """Result of parsing a single file.

    Attributes:
        file_path: Original file path (absolute or relative, as supplied).
        chunks: Ordered list of parsed chunks.
        metadata: File-level metadata (format, size, modified_time, …).
    """

    file_path: str
    chunks: list[ParsedChunk] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
