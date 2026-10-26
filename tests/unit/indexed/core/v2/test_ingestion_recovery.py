"""End-to-end recovery of a v2 create whose swap was killed (#126).

``core.v2.persist.replace_dir`` is already build-aside → rename → rename. These
tests exercise what happens AFTER a process dies between the two renames: no
canonical directory, both generations stranded under names discovery skips.
Recovery must restore exactly one complete collection before the next
discovery/search — and an interrupted *new* collection must never appear.

The in-process case is driven through the real ``ingestion.create`` swap; the
subprocess case is a real hard kill (``os._exit``) inside ``replace_dir``, so no
``finally``/rollback/cleanup runs. An in-process interruption leaves strands
carrying the *test's own* pid, which recovery correctly refuses to touch as an
in-flight write — so those cases re-brand the strands onto a finished pid before
the recovery read (see ``_rebrand_as_finished``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from indexed.core.v2 import ingestion, retrieval
from indexed.core.v2._common import discover_v2_collections
from indexed.protocols import SourceConfig
from tests.unit.indexed.core.v2._engine_helpers import (
    make_connector_factory,
    make_doc,
    mock_embedding,
)

pytestmark = pytest.mark.unit

_OLD_DOC = "penguin migration antarctic coastline survey"
_NEW_DOC = "unicorn caldera volcanic soil sulfur"


def _cfg(name: str) -> SourceConfig:
    return SourceConfig(name=name, type="localFiles", base_url_or_path="/corpus")


def _create(cols: Path, name: str, docs: list[dict]) -> None:
    with mock_embedding(embed_dim=8):
        ingestion.create(
            [_cfg(name)],
            use_cache=False,
            connector_factory=make_connector_factory(docs),
            collections_path=str(cols),
        )


def _docstore_text(cols: Path, name: str) -> str:
    return (cols / name / "storage" / "docstore.json").read_text(encoding="utf-8")


def _finished_pid() -> int:
    """A pid that belonged to a process which has exited."""
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait(timeout=30)
    return finished.pid


def _rebrand_as_finished(cols: Path, name: str) -> None:
    """Re-point an IN-PROCESS crash's strands at a finished pid.

    The ``KeyboardInterrupt`` above is raised in this process, so the stranded
    directories carry OUR pid — which recovery must treat as an in-flight write
    of its own (the long-lived MCP server case) and never sweep. A real
    ``SIGKILL`` kills the writer, so the next read runs under a DIFFERENT pid;
    re-branding the strands with a finished pid reproduces exactly that.
    """
    pid = _finished_pid()
    ours = (f"{name}.tmp-{os.getpid()}", f"{name}.trash-{os.getpid()}")
    for child in list(cols.iterdir()):
        if child.name.startswith(ours):
            child.rename(cols / child.name.replace(str(os.getpid()), str(pid), 1))


def test_kill_between_renames_is_recovered_on_next_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The #126 window, end to end through the real swap.

    A second create renames the old generation aside and is killed before the
    new one lands: the canonical path is gone, both generations are stranded.
    The next search — which discovers collections first — must see the newest
    complete generation, not nothing.
    """
    cols = tmp_path / "cols"
    _create(cols, "docs", [make_doc("old", [_OLD_DOC])])

    real_rename = os.rename
    calls = {"n": 0}

    def kill_after_first_rename(src: str, dst: str) -> None:
        calls["n"] += 1
        real_rename(src, dst)
        if calls["n"] == 1:
            # BaseException: bypasses replace_dir's rollback and create's
            # staging cleanup, exactly like SIGKILL.
            raise KeyboardInterrupt("killed between the two renames")

    monkeypatch.setattr(os, "rename", kill_after_first_rename)
    try:
        with pytest.raises(KeyboardInterrupt):
            _create(cols, "docs", [make_doc("new", [_NEW_DOC])])
    finally:
        monkeypatch.setattr(os, "rename", real_rename)

    # The crash window: no canonical collection, both generations on disk.
    assert not (cols / "docs").exists()
    stranded = sorted(p.name for p in cols.iterdir())
    assert any(name.startswith("docs.trash-") for name in stranded), stranded
    assert any(name.startswith("docs.tmp-") for name in stranded), stranded

    _rebrand_as_finished(cols, "docs")
    # Recovery runs inside discovery, before any collection is opened.
    assert discover_v2_collections(cols) == ["docs"]

    # Exactly one generation is canonical — the newest (complete) one.
    docstore = _docstore_text(cols, "docs")
    assert "unicorn" in docstore
    assert "penguin" not in docstore
    # The superseded generation is preserved for inspection, never mixed in.
    quarantined = [
        p
        for p in (cols / ".recovery" / "docs").iterdir()
        if p.is_dir() and p.name.startswith("docs.trash-")
    ]
    assert len(quarantined) == 1
    assert "penguin" in (quarantined[0] / "storage" / "docstore.json").read_text(
        encoding="utf-8"
    )
    assert not any(".trash-" in name for name in (p.name for p in cols.iterdir()))


def test_recovered_collection_is_searchable(tmp_path: Path) -> None:
    """Restoration happens before discovery, so a plain search finds the data."""
    cols = tmp_path / "cols"
    _create(cols, "docs", [make_doc("old", [_OLD_DOC])])

    real_rename = os.rename
    calls = {"n": 0}

    def kill_after_first_rename(src: str, dst: str) -> None:
        calls["n"] += 1
        real_rename(src, dst)
        if calls["n"] == 1:
            raise KeyboardInterrupt("killed between the two renames")

    os.rename = kill_after_first_rename  # noqa: SIM115 - restored below
    try:
        with pytest.raises(KeyboardInterrupt):
            _create(cols, "docs", [make_doc("new", [_NEW_DOC])])
    finally:
        os.rename = real_rename

    assert not (cols / "docs").exists()
    _rebrand_as_finished(cols, "docs")
    with mock_embedding(embed_dim=8):
        results = retrieval.search("unicorn caldera", collections_path=str(cols))

    assert set(results) == {"docs"}
    assert {hit["id"] for hit in results["docs"]["results"]} == {"new"}


_SUBPROCESS_KILL = """
import os
import sys
from pathlib import Path

from indexed.core.v2.persist import replace_dir

base = Path(sys.argv[1])
dest = base / "docs"
staging = base / f"docs.tmp-{os.getpid()}-abcdef12"
(base / "gen_new").rename(staging)

real_rename = os.rename
calls = {"n": 0}


def killer(src, dst):
    calls["n"] += 1
    real_rename(src, dst)
    if calls["n"] == 1:
        os._exit(9)  # no finally, no rollback, no cleanup


os.rename = killer
replace_dir(staging, dest)
raise SystemExit("the kill did not fire")
"""


def test_hard_killed_subprocess_leaves_a_recoverable_collection(tmp_path: Path) -> None:
    """A real ``os._exit`` between the renames, recovered by the next read."""
    cols = tmp_path / "cols"
    _create(cols, "docs", [make_doc("old", [_OLD_DOC])])
    # Stage a complete newer generation for the subprocess to swap in.
    _create(cols, "gen_new", [make_doc("new", [_NEW_DOC])])

    script = tmp_path / "kill_swap.py"
    script.write_text(_SUBPROCESS_KILL, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(script), str(cols)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 9, completed.stderr
    assert not (cols / "docs").exists()
    assert any(p.name.startswith("docs.trash-") for p in cols.iterdir())

    # The dead writer's pid is in the strand name; recovery still owns it.
    assert discover_v2_collections(cols) == ["docs"]
    docstore = _docstore_text(cols, "docs")
    assert "unicorn" in docstore
    shutil.rmtree(cols / "gen_new", ignore_errors=True)


def test_interrupted_new_collection_never_becomes_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A killed create of a NEW name leaves only staging: not a collection."""
    cols = tmp_path / "cols"

    def kill_before_swap(staging, dest):  # noqa: ANN001
        raise KeyboardInterrupt("killed before the swap")

    monkeypatch.setattr("indexed.core.v2.persist.replace_dir", kill_before_swap)
    with pytest.raises(KeyboardInterrupt):
        _create(cols, "docs", [make_doc("new", [_NEW_DOC])])
    monkeypatch.undo()

    _rebrand_as_finished(cols, "docs")
    assert discover_v2_collections(cols) == []
    # Preserved, not published and not deleted.
    quarantined = list((cols / ".recovery" / "docs").rglob("manifest.json"))
    assert len(quarantined) == 1
    assert json.loads(quarantined[0].read_text())["collectionName"] == "docs"
