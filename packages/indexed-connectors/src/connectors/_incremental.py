"""Shared incremental-update query construction for Jira/Confluence connectors.

Both build a `created >= cutoff OR <updated_field> >= cutoff` date filter from a
collection's `lastModifiedDocumentTime`, joined onto the stored query. Kept in
one place so the cutoff math and the empty-base-query guard (R6.5) can't diverge
across the two connectors (AGENTS.md: "shared guard helpers, not duplicated blocks").
"""

from datetime import datetime, timedelta


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
    ``updated_field`` is ``updated`` for Jira JQL, ``lastModified`` for Confluence CQL.
    """
    date_filter = f'(created >= "{cutoff}" OR {updated_field} >= "{cutoff}")'
    base = (base_query or "").strip()
    return f"{base} AND {date_filter}" if base else date_filter
