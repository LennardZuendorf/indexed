"""The documented search-result shape (``indexed.search/1``).

ONE contract for every machine consumer: the CLI's ``indexed search --json``
and the MCP tools ``search`` / ``search_collection`` both emit exactly this,
built by one function (``indexed.mcp.formatting.build_search_payload``).
The user-facing field reference lives in ``docs/reference/search-output.md``;
the design record in ``.spec/tech-app.md`` § Search result contract.

Design rules (issue #108/#109):

- **Document-level facts are stated once.** Collection, source type, document
  id, url and the score semantics belong to the document, not to every chunk
  of it — repeating them per hit was most of the old payload's bulk.
- **A locator is honest.** ``kind`` says what is actually known about where
  the hit sits: a line span for code, a page for paginated documents, a
  heading path for prose, or ``document`` when the source carries no
  position at all. A range is never invented to fill the field.
- **No boilerplate to strip.** Per hit the agent gets a relevance, the raw
  score, the locator and the text — nothing that has to be filtered before
  use.

Version note: bump ``SEARCH_SCHEMA`` on any incompatible change; consumers
are expected to branch on it rather than guess from the key set.
"""

from typing import List, Literal, NotRequired, TypedDict

#: Schema id emitted in every payload; consumers branch on this.
SEARCH_SCHEMA = "indexed.search/1"

#: How precisely a hit's position is known.
#: ``line_span`` > ``page`` > ``headings`` > ``document`` in precision order.
LocatorKind = Literal["line_span", "page", "headings", "document"]


class Locator(TypedDict):
    """Where a hit sits inside its document.

    ``kind`` is load-bearing: read only the keys that kind declares.
    """

    kind: LocatorKind
    # line_span only: the source file, when it differs from the document's
    # ``path`` (a hit inside one file does not repeat the path — the document
    # states it once). 1-BASED INCLUSIVE lines: what ``grep -n`` prints.
    path: NotRequired[str]
    start_line: NotRequired[int]
    end_line: NotRequired[int]
    # page only: 1-based page number for paginated (PDF/DOCX) documents.
    page: NotRequired[int]
    # headings only: the document's heading path down to the chunk.
    headings: NotRequired[List[str]]


class Hit(TypedDict):
    """One matched chunk."""

    relevance: float
    """0-1, higher is better, comparable across collections and engines."""

    score: float
    """The raw engine score; only comparable within one ``score_kind``."""

    locator: Locator
    text: str


class DocumentResult(TypedDict):
    """One matched document and the chunks of it that matched."""

    collection: str
    source_type: NotRequired[str]
    """The collection's reader type (``localFiles``, ``jira``, …); a
    collection-level fact, because a collection is fed by exactly one
    reader. Omitted when the collection's manifest does not say."""

    id: str
    path: NotRequired[str]
    """The document's source file, stated once so its hits need not repeat
    it. Present when the hits agree on one path."""

    url: NotRequired[str]
    """Where a human/agent opens the whole document. Omitted when unknown or
    when it only restates ``path`` (``file://<path>``)."""

    score_kind: str
    """``l2_squared`` (v1), ``cosine`` or ``rerank`` (v2) — what ``score``
    means for this document."""

    hits: List[Hit]


class Counts(TypedDict):
    documents: int
    hits: int


class CollectionError(TypedDict):
    collection: str
    error: str


class SearchPayload(TypedDict):
    """The whole machine payload, for both surfaces."""

    schema: str
    query: str
    counts: Counts
    collections: List[str]
    """Collections that were searched successfully."""

    collection_errors: List[CollectionError]
    """Always present, empty when nothing failed — a failed collection must
    read as "this collection failed", never as "no matches"."""

    documents: List[DocumentResult]


__all__ = [
    "SEARCH_SCHEMA",
    "CollectionError",
    "Counts",
    "DocumentResult",
    "Hit",
    "Locator",
    "LocatorKind",
    "SearchPayload",
]
