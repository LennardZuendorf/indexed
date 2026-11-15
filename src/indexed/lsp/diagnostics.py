"""Diagnostics that report only facts the index can prove.

A diagnostics channel is a promise about *problems*, and the index has no
opinion about types, lint rules or style. So this module reports exactly two
things, both read from metadata the index already wrote itself:

* **the file belongs to no collection** — ``backend.collection_for_path`` says
  no collection's source root contains it, so `indexed` search can never
  return it;
* **the file changed after it was indexed** — the collection's last indexing
  run recorded a different content fingerprint for it than the file has now
  (``<collection>/state.json`` → ``file_hashes``, the same value the change
  tracker compares against).

Everything the metadata cannot prove is silence: unknown is not "healthy", and
unknown is emphatically not "broken". That is the whole contract of issue #241
— a diagnostics channel that fabricates warnings is worse than none.

Two consequences worth stating, because they are what keep this honest:

* There is no severity above Information. Neither fact is an error or a lint
  warning; painting a file red for either would be the fabrication the issue
  forbids.
* A file the last run did not cover (no ``state.json`` — never indexed, or
  migrated from v1 — or no entry for this path) yields **no** diagnostic. The
  index simply has no opinion about it.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from indexed.utils.fingerprint import file_fingerprint

from .backend import KnowledgeBackend
from .resolver import document_range
from .results import uri_to_path

#: Shown next to every message from this server, so an editor can attribute it.
DIAGNOSTIC_SOURCE = "indexed"

#: LSP ``DiagnosticSeverity.Information``. Nothing here is an error or a
#: warning — see the module docstring.
SEVERITY_INFORMATION = 3

#: Code for "no collection covers this file".
NOT_IN_COLLECTION = "not-in-any-collection"

#: Code for "the index holds a different version of this file".
STALE = "index-stale"

Diagnostic = Dict[str, Any]


def build_diagnostics(backend: KnowledgeBackend, uri: str) -> List[Diagnostic]:
    """The diagnostics that are actually true for ``uri`` right now.

    Returns at most one diagnostic per code (two in total, and only if the file
    is somehow both — which the two conditions make impossible in practice:
    a file no collection owns has no index entry to be stale). An empty list is
    the normal, healthy answer and is what clears a previously published
    diagnostic.
    """
    path = uri_to_path(uri)
    if path is None or not os.path.isfile(path):
        # A remote Jira/Confluence URI or a buffer with no file behind it: there
        # is nothing to measure a range from, so there is nothing to report.
        return []
    span = document_range(path)
    if span is None:
        # Unreadable: even the file-level range would be invented.
        return []

    status = backend.collection_for_path(path)
    if status is None:
        return [
            _diagnostic(
                span,
                NOT_IN_COLLECTION,
                "This file is not part of any indexed collection, so `indexed` "
                "search cannot return it.",
            )
        ]

    collection = str(getattr(status, "name", "") or "")
    if not _is_stale(backend, collection, path):
        return []
    return [
        _diagnostic(
            span,
            STALE,
            f"The `{collection}` collection indexed a different version of this "
            f"file. Run `indexed index update {collection}` to refresh it.",
        )
    ]


def _is_stale(backend: KnowledgeBackend, collection: str, path: str) -> bool:
    """True only when the index's own recorded fingerprint disagrees with the file.

    Both sides come from ``utils.fingerprint``, so this answers the same
    question ``indexed index update`` answers — never a second, laxer notion of
    "changed".
    """
    recorded = backend.indexed_digest(collection, path)
    if recorded is None:
        return False  # no recorded fingerprint: unknown, which is not stale
    current = file_fingerprint(path)
    if current is None:
        return False
    return recorded != current[0]


def _diagnostic(span: Dict[str, Any], code: str, message: str) -> Diagnostic:
    """One file-level diagnostic over a range measured from the real file."""
    return {
        "range": span,
        "severity": SEVERITY_INFORMATION,
        "source": DIAGNOSTIC_SOURCE,
        "code": code,
        "message": message,
    }


__all__ = [
    "DIAGNOSTIC_SOURCE",
    "NOT_IN_COLLECTION",
    "SEVERITY_INFORMATION",
    "STALE",
    "build_diagnostics",
]
