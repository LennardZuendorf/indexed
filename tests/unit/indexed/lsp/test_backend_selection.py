"""The LSP honours a workspace definition's selection (#344, slice 4).

Filtering happens inside the cached status snapshot, so ownership
(``workspace/symbol``), hover and diagnostics all see the same scope as the CLI
without a second enumeration.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from indexed.lsp.backend import STATUS_TTL_SECONDS, KnowledgeBackend

pytestmark = pytest.mark.unit


def _status(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        source_type="localFiles",
        indexers=["indexer_FAISS"],
        updated_time="2026-11-02T09:00:00+00:00",
    )


class Recorder:
    def __init__(self, statuses: List[Any]) -> None:
        self.statuses = statuses
        self.calls = 0

    def __call__(self, *args: Any, **kwargs: Any) -> List[Any]:
        self.calls += 1
        return self.statuses


def test_statuses_filter_to_the_selected_names(tmp_path) -> None:
    status_fn = Recorder([_status("docs"), _status("code"), _status("notes")])
    backend = KnowledgeBackend(
        str(tmp_path), status_fn=status_fn, selected_names=("code", "docs")
    )

    assert [status.name for status in backend.statuses()] == ["docs", "code"]
    # A collection outside the selection is invisible to every consumer.
    assert backend.status_for("notes") is None
    assert backend.status_for("docs") is not None


def test_the_filter_is_applied_to_the_cached_snapshot(tmp_path) -> None:
    """One enumeration serves every scoped read inside the TTL."""
    now = [0.0]
    status_fn = Recorder([_status("docs"), _status("notes")])
    backend = KnowledgeBackend(
        str(tmp_path),
        status_fn=status_fn,
        selected_names=["docs"],
        clock=lambda: now[0],
    )

    backend.statuses()
    now[0] = STATUS_TTL_SECONDS / 2
    backend.statuses()

    assert status_fn.calls == 1


def test_no_selection_leaves_statuses_unfiltered(tmp_path) -> None:
    """R4: a workspace without a definition loses nothing."""
    status_fn = Recorder([_status("docs"), _status("notes")])
    backend = KnowledgeBackend(str(tmp_path), status_fn=status_fn)

    assert [status.name for status in backend.statuses()] == ["docs", "notes"]
    assert backend.status_for("notes") is not None
