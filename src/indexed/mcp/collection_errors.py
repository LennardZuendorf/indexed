"""One answer for "``status()`` could not resolve this collection" (#112/#125).

``status()`` omits collections whose manifest is unreadable, so an empty status is
ambiguous: the name may be unknown, or the collection may be present and unusable.
Answering "not found" in the second case sends an agent hunting a typo when the
index is what needs rebuilding, so probe the disk before choosing the message.
"""

from __future__ import annotations

from typing import Any, Dict

from indexed.cli.errors import MCPError, mcp_error_envelope
from indexed.core.engine import collection_exists as svc_collection_exists


def unresolvable_collection_error(
    collection: str, collections_path: str, missing: str
) -> Dict[str, Any]:
    """Envelope for a collection ``status()`` could not resolve.

    ``missing`` is the caller's existing "not found" text, kept verbatim so each
    surface keeps the wording its clients already match on.
    """
    if svc_collection_exists(collection, collections_path=collections_path):
        return mcp_error_envelope(
            MCPError(
                f"Collection '{collection}' exists on disk but has no usable index: "
                "its manifest is unreadable, or it has no indexers yet. Re-create it "
                "with --force, or re-run indexing for it, then retry."
            )
        )
    return {"error": missing}
