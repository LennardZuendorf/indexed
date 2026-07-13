"""Shared incremental-update query construction for Jira/Confluence connectors.

Both build a `created >= cutoff OR <updated_field> >= cutoff` date filter from a
collection's `lastModifiedDocumentTime`, joined onto the stored query. Kept in
one place so the cutoff math and the empty-base-query guard (R6.5) can't diverge
across the two connectors (AGENTS.md: "shared guard helpers, not duplicated blocks").
"""

import re
from datetime import datetime, timedelta

# Trailing sort clause both JQL and CQL support. A boolean clause can never
# follow ``ORDER BY``, so the incremental date filter must be spliced into the
# WHERE part with the sort re-appended.
_ORDER_BY_RE = re.compile(r"\bORDER\s+BY\b", re.IGNORECASE)


def _quoted_spans(text: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` spans (end exclusive) of quoted string literals.

    Handles both single- and double-quoted JQL/CQL literals with backslash
    escaping, so an ``ORDER BY`` occurring inside a literal value (e.g.
    ``text ~ "please order by date"``) is never mistaken for the trailing
    sort-clause boundary.

    A quote character flanked by word characters on both sides (e.g. the
    apostrophe in ``don't`` or ``reallyz's``) is never treated as an opening
    delimiter: it is almost certainly a contraction/possessive, not a
    literal boundary. Naively pairing ANY two same-char quotes would let an
    unrelated pair of such apostrophes span across real query text -
    including a genuine trailing ``ORDER BY`` - and mis-classify it as
    "inside a literal" (worse than not being quote-aware at all). Skipping
    word-internal quote characters when deciding whether to *open* a span
    degrades safely: real, properly word-bounded literals (preceded/followed
    by whitespace, operators, or start/end of string) are unaffected, while
    ambiguous/odd apostrophe usage never swallows real query structure.
    An opening quote with no matching close by end-of-string yields no span
    at all for that region (its tail is treated as unquoted), which is also
    the safe behavior.
    """
    spans: list[tuple[int, int]] = []
    quote_char: str | None = None
    start = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote_char is None:
            if ch in ("'", '"'):
                before = text[i - 1] if i > 0 else ""
                after = text[i + 1] if i + 1 < n else ""
                if before.isalnum() and after.isalnum():
                    # Word-internal apostrophe/quote (contraction or
                    # possessive) - not a literal delimiter, skip it.
                    i += 1
                    continue
                quote_char = ch
                start = i
        elif ch == "\\":
            i += 2
            continue
        elif ch == quote_char:
            spans.append((start, i + 1))
            quote_char = None
        i += 1
    return spans


def _is_quoted(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def cutoff_date(last_modified_document_time: str) -> str:
    """Incremental cutoff = the collection's last-modified time minus one day."""
    return (
        (datetime.fromisoformat(last_modified_document_time) - timedelta(days=1))
        .date()
        .isoformat()
    )


def incremental_query(
    base_query: str | None, cutoff: str, *, updated_field: str
) -> str:
    """Join a stored query with a ``created/<updated_field> >= cutoff`` date filter.

    Joined with ``AND`` only when a non-empty base query exists, so an empty
    stored query never yields a malformed leading-``AND`` clause (R6.5).
    A trailing ``ORDER BY`` sort clause is preserved: the date filter is spliced
    into the WHERE part and the sort re-appended, since a boolean clause cannot
    legally follow ``ORDER BY`` in JQL/CQL.
    ``updated_field`` is ``updated`` for Jira JQL, ``lastModified`` for Confluence CQL.
    """
    date_filter = f'(created >= "{cutoff}" OR {updated_field} >= "{cutoff}")'
    base = (base_query or "").strip()
    if not base:
        return date_filter

    # A valid query carries at most one (trailing) ORDER BY; take the last
    # top-level (unquoted) match so neither a literal "order by" inside a
    # quoted WHERE value nor one inside a WHERE value in general is mistaken
    # for the sort-clause boundary.
    spans = _quoted_spans(base)
    matches = [
        m for m in _ORDER_BY_RE.finditer(base) if not _is_quoted(m.start(), spans)
    ]
    if not matches:
        return f"{base} AND {date_filter}"

    split_at = matches[-1].start()
    where_part = base[:split_at].strip()
    order_by = base[split_at:].strip()
    if where_part:
        return f"{where_part} AND {date_filter} {order_by}"
    return f"{date_filter} {order_by}"
