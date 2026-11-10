"""Tests for the honest diagnostics channel.

The acceptance bar is negative as much as positive: the channel must report the
two facts the index can prove, and must stay completely silent for everything
else — including a file full of type errors and lint violations, which the index
has no business judging (issue #241).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from indexed.lsp.diagnostics import (
    DIAGNOSTIC_SOURCE,
    NOT_IN_COLLECTION,
    SEVERITY_INFORMATION,
    STALE,
    build_diagnostics,
)
from indexed.utils.fingerprint import file_fingerprint

pytestmark = pytest.mark.unit

STATUS = SimpleNamespace(name="probe", source_type="localFiles")

#: Deliberately broken Python and lint-bait: the index has no opinion about any
#: of it, so a diagnostics channel that reports it is fabricating.
BROKEN_SOURCE = """import os
x: int = "not an int"
def f(  # missing body, unused args, star imports, shadowed builtins
    a, b, a=None
):
    return undefined_name
"""

HEALTHY_SOURCE = """def alpha():
    return 1
"""


class FakeBackend:
    """A backend whose index record for a path is whatever the test says."""

    def __init__(
        self,
        *,
        owning: Optional[Any] = STATUS,
        digests: Optional[dict[str, Optional[str]]] = None,
        raises: Optional[Exception] = None,
    ) -> None:
        self.owning = owning
        self.digests = digests or {}
        self.raises = raises
        self.digest_queries: list[tuple[str, str]] = []
        self.owner_queries: list[str] = []

    def collection_for_path(self, path: str) -> Optional[Any]:
        self.owner_queries.append(path)
        return self.owning

    def indexed_digest(self, collection: str, path: str) -> Optional[str]:
        self.digest_queries.append((collection, path))
        if self.raises is not None:
            raise self.raises
        return self.digests.get(path)


def _write(tmp_path: Path, text: str, name: str = "sample.py") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_stale_file_yields_exactly_one_diagnostic_with_a_measured_range(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, HEALTHY_SOURCE)
    backend = FakeBackend(digests={str(path): "0000000000000000"})

    diagnostics = build_diagnostics(backend, path.as_uri())

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic["code"] == STALE
    assert diagnostic["source"] == DIAGNOSTIC_SOURCE
    assert diagnostic["severity"] == SEVERITY_INFORMATION
    # A real file-level range, counted from the file itself: 2 lines, trailing
    # newline, so the exclusive end is line 2 column 0.
    assert diagnostic["range"] == {
        "start": {"line": 0, "character": 0},
        "end": {"line": 2, "character": 0},
    }
    assert "`probe` collection" in diagnostic["message"]
    assert "indexed index update probe" in diagnostic["message"]
    # The lookup asked about the owning collection, by the real path.
    assert backend.digest_queries == [("probe", str(path))]


def test_uncollected_file_yields_exactly_one_diagnostic(tmp_path: Path) -> None:
    path = _write(tmp_path, HEALTHY_SOURCE)
    backend = FakeBackend(owning=None)

    diagnostics = build_diagnostics(backend, path.as_uri())

    assert len(diagnostics) == 1
    assert diagnostics[0]["code"] == NOT_IN_COLLECTION
    assert diagnostics[0]["severity"] == SEVERITY_INFORMATION
    assert diagnostics[0]["range"]["end"] == {"line": 2, "character": 0}
    # No collection owns it, so there is no index record to consult.
    assert backend.digest_queries == []


def test_healthy_file_yields_an_empty_diagnostics_array(tmp_path: Path) -> None:
    path = _write(tmp_path, HEALTHY_SOURCE)
    fingerprint = file_fingerprint(str(path))
    assert fingerprint is not None
    backend = FakeBackend(digests={str(path): fingerprint[0]})

    assert build_diagnostics(backend, path.as_uri()) == []


def test_a_type_or_lint_condition_never_produces_a_diagnostic(tmp_path: Path) -> None:
    """The whole point of #241: no type checking, no linting, ever."""
    path = _write(tmp_path, BROKEN_SOURCE)
    fingerprint = file_fingerprint(str(path))
    assert fingerprint is not None
    backend = FakeBackend(digests={str(path): fingerprint[0]})

    assert build_diagnostics(backend, path.as_uri()) == []


def test_no_recorded_fingerprint_is_unknown_not_stale(tmp_path: Path) -> None:
    """No state entry (never indexed, or excluded from the run) is silence."""
    path = _write(tmp_path, HEALTHY_SOURCE)
    backend = FakeBackend(digests={})

    assert build_diagnostics(backend, path.as_uri()) == []


def test_a_file_outside_every_collection_is_reported_even_when_dirty(
    tmp_path: Path,
) -> None:
    """The two codes are independent: no owner means no staleness question."""
    path = _write(tmp_path, BROKEN_SOURCE)
    backend = FakeBackend(owning=None, digests={str(path): "deadbeef"})

    diagnostics = build_diagnostics(backend, path.as_uri())

    assert [d["code"] for d in diagnostics] == [NOT_IN_COLLECTION]


@pytest.mark.parametrize(
    "uri",
    [
        "jira://PROJ-1",
        "confluence://spaces/ENG/pages/1",
        "file:///nonexistent/never/on/disk.py",
    ],
)
def test_remote_and_missing_documents_yield_nothing(tmp_path: Path, uri: str) -> None:
    """No local text means no measurable range, so nothing is published."""
    backend = FakeBackend(digests={"/nonexistent/never/on/disk.py": "deadbeef"})

    assert build_diagnostics(backend, uri) == []


def test_an_unreadable_file_yields_nothing(tmp_path: Path) -> None:
    path = _write(tmp_path, HEALTHY_SOURCE)
    path.chmod(0o000)
    try:
        assert build_diagnostics(FakeBackend(), path.as_uri()) == []
    finally:
        path.chmod(0o600)


def test_a_failing_index_read_yields_nothing_and_never_raises(tmp_path: Path) -> None:
    """A server that dies mid-diagnostics loses the editor's whole session."""
    path = _write(tmp_path, HEALTHY_SOURCE)
    backend = FakeBackend(raises=RuntimeError("state.json is on fire"))

    with pytest.raises(RuntimeError):
        # The module itself propagates; the *server* is what swallows it (see
        # test_server.py::test_a_failing_diagnostics_check_does_not_kill_the_session).
        build_diagnostics(backend, path.as_uri())
