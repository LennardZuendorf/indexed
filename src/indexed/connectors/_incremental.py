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
