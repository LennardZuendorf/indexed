"""The source-facing projection of a manifest's ``reader`` block (#108).

Both engines share the ``reader`` block byte-for-byte (see ``V2Manifest``), so
this one allowlist projection is the single place that decides which reader
fields are safe and meaningful to *show* a user.

Why an allowlist rather than "everything minus secrets": the reader block is
where every connector dumps its own config knobs (``includePatterns``,
``collectionIds``, ``projectKeys``, …). Copying it wholesale would make the
inspect output — and any JSON consumer of it — silently track every connector
change, and would put fields nobody promised into a machine contract. Three
named keys are the contract; anything else the reader carries is not.

Mapping (all camelCase, as the connectors write them):

- ``source_path``  ← ``basePath`` (files)
- ``source_url``   ← first present of ``baseUrl``, ``graphqlUrl``, ``host``
- ``source_query`` ← ``query`` (Jira JQL and Confluence CQL both use it)

Missing, ``None``, empty, or non-text values project to ``None``.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

#: The JSON/CLI-facing key for each reader field, in display order.
SOURCE_KEYS: tuple[str, ...] = ("source_path", "source_url", "source_query")

_URL_KEYS: tuple[str, ...] = ("baseUrl", "graphqlUrl", "host")


def _as_text(value: Any) -> Optional[str]:
    """A storable text value, or ``None`` — never ``"[object Object]"``."""
    if isinstance(value, str):
        return value.strip() or None
    # A numeric baseUrl/query is odd but harmless to show; containers are not.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _first_text(reader: Mapping[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        text = _as_text(reader.get(key))
        if text is not None:
            return text
    return None


def source_metadata(reader: Optional[Mapping[str, Any]]) -> dict[str, Optional[str]]:
    """Project a manifest ``reader`` block onto the three source-facing keys.

    Returns a dict with exactly ``source_path``, ``source_url`` and
    ``source_query`` (each ``Optional[str]``). Never raises: a missing reader
    block, a non-mapping one, or a garbage value all degrade to ``None`` — a
    display field must not be able to fail an inspect.
    """
    block: Mapping[str, Any] = reader if isinstance(reader, Mapping) else {}
    return {
        "source_path": _as_text(block.get("basePath")),
        "source_url": _first_text(block, *_URL_KEYS),
        "source_query": _as_text(block.get("query")),
    }


__all__ = ["SOURCE_KEYS", "source_metadata"]
