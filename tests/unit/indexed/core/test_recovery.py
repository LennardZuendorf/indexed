"""Recovery of collections stranded by an interrupted atomic swap (#126).

The swap itself (``core.v2.persist.replace_dir``) is already build-aside →
rename → rename → cleanup. What these tests pin down is the RECOVERY half: a
process killed between the two renames leaves the canonical directory missing
while a complete old generation sits in ``<name>.trash-<pid>`` and a complete
new one in ``<name>.tmp-<pid>-<hex>`` — both invisible to discovery. Recovery
must put exactly one complete generation back at the canonical name, never mix
generations, and never delete what it cannot prove redundant.

Also covers the facade's diagnostic surface: an explicitly requested collection
that could not be restored fails loud with
:class:`~indexed.core.errors.CollectionRecoveryError` instead of reading as
"no such collection".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from loguru import logger

from indexed.core.engine import _existing_collection_names
from indexed.core.errors import CollectionRecoveryError
from indexed.core.recovery import QUARANTINE_DIRNAME, RecoveryOutcome, recover_stranded
from indexed.core.v2._common import discover_v2_collections

pytestmark = pytest.mark.unit

_STORAGE_FILES = ("docstore.json", "index_store.json", "default__vector_store.json")

_DEAD_PID: int | None = None


def dead_pid() -> int:
    """A pid that belonged to a finished process (so recovery may touch it).

    A real, exited process is used rather than a magic number so the liveness
    probe is exercised for real; the result is memoized per test.
    """
    global _DEAD_PID
    if _DEAD_PID is None:
        finished = subprocess.Popen([sys.executable, "-c", "pass"])
        finished.wait(timeout=30)
        _DEAD_PID = finished.pid
    return _DEAD_PID


@pytest.fixture(autouse=True)
def _reset_dead_pid() -> None:
    """Each test resolves its own dead pid (no cross-test pid reuse surprises)."""
    global _DEAD_PID
    _DEAD_PID = None


def make_generation(
    path: Path,
    *,
    payload: str,
    complete: bool = True,
    version: str | None = "2",
) -> Path:
    """Write a generation directory shaped like a persisted v2 collection.

    ``complete=False`` writes the manifest but no ``storage/`` files — the
    partial-staging case (manifest present, data files missing).
    """
    path.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"collectionName": path.name.split(".")[0]}
    if version is not None:
        manifest["version"] = version
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (path / "payload.txt").write_text(payload, encoding="utf-8")
    if complete:
        storage = path / "storage"
        storage.mkdir()
        for filename in _STORAGE_FILES:
            (storage / filename).write_text(
                json.dumps({"generation": payload}), encoding="utf-8"
            )
    return path


def _logs() -> tuple[list[str], int]:
    """Attach a capturing loguru sink; returns (messages, handler id)."""
    messages: list[str] = []
    handler = logger.add(lambda record: messages.append(record), level="DEBUG")
    return messages, handler


def test_crash_between_renames_restores_newest_complete_generation(
    tmp_path: Path,
) -> None:
    """The #126 window: canonical missing, old gen in ``.trash-``, new in ``.tmp-``."""
    base = tmp_path / "cols"
    base.mkdir()
    pid = dead_pid()
    old = make_generation(base / f"docs.trash-{pid}", payload="old")
    new = make_generation(base / f"docs.tmp-{pid}-abcdef12", payload="new")

    messages, handler = _logs()
    try:
        outcome = recover_stranded(base)
    finally:
        logger.remove(handler)

    assert (base / "docs" / "payload.txt").read_text() == "new"
    assert outcome.restored == (("docs", base / "docs"),)
    assert not old.exists() and not new.exists()
    # The superseded old generation is preserved, not deleted — and never mixed
    # into the restored collection.
    quarantined = dict(outcome.quarantined)
    assert quarantined["docs"] == base / QUARANTINE_DIRNAME / "docs" / old.name
    assert not (base / "docs" / "storage" / "stale-old.json").exists()
    # Observable: one line naming the collection and where it came from.
    assert any("restored 'docs'" in str(message) for message in messages)
    assert any("quarantined" in str(message) for message in messages)


def test_restores_old_generation_when_new_one_is_incomplete(tmp_path: Path) -> None:
    """A complete old generation beats a staging dir whose data files are missing."""
    base = tmp_path / "cols"
    base.mkdir()
    pid = dead_pid()
    make_generation(base / f"docs.trash-{pid}", payload="old")
    partial = make_generation(
        base / f"docs.tmp-{pid}-abcdef12", payload="new", complete=False
    )

    outcome = recover_stranded(base)

    assert (base / "docs" / "payload.txt").read_text() == "old"
    assert outcome.restored == (("docs", base / "docs"),)
    assert dict(outcome.quarantined)["docs"] == (
        base / QUARANTINE_DIRNAME / "docs" / partial.name
    )


def test_incomplete_generation_is_never_promoted(tmp_path: Path) -> None:
    """Only the old generation exists and it is partial: quarantine, never publish.

    A collection that never completed a build must not surface as healthy.
    """
    base = tmp_path / "cols"
    base.mkdir()
    pid = dead_pid()
    partial = make_generation(
        base / f"docs.trash-{pid}", payload="partial", complete=False
    )

    outcome = recover_stranded(base)

    assert not (base / "docs").exists()
    assert not partial.exists()
    assert outcome.restored == ()
    assert dict(outcome.quarantined)["docs"] == (
        base / QUARANTINE_DIRNAME / "docs" / partial.name
    )
    assert outcome.reason_for("docs") is not None
    assert discover_v2_collections(base) == []


def test_unpublished_staging_dir_is_quarantined_not_promoted(tmp_path: Path) -> None:
    """A ``.tmp-`` strand with no ``.trash-`` sibling means rename 1 never ran.

    An interrupted *new* collection was never published, so it must not become
    the canonical collection — but its data is preserved, not deleted.
    """
    base = tmp_path / "cols"
    base.mkdir()
    staging = make_generation(base / f"docs.tmp-{dead_pid()}-abcdef12", payload="new")

    outcome = recover_stranded(base)

    assert not (base / "docs").exists()
    assert discover_v2_collections(base) == []
    assert dict(outcome.quarantined)["docs"] == (
        base / QUARANTINE_DIRNAME / "docs" / staging.name
    )
    assert (base / QUARANTINE_DIRNAME / "docs" / staging.name / "payload.txt").is_file()
    assert "never swapped in" in (outcome.reason_for("docs") or "")


def test_partial_staging_beside_complete_collection_is_preserved(
    tmp_path: Path,
) -> None:
    """Canonical complete + stale staging: the collection stays, the strand moves."""
    base = tmp_path / "cols"
    base.mkdir()
    canonical = make_generation(base / "docs", payload="live")
    staging = make_generation(
        base / f"docs.tmp-{dead_pid()}-abcdef12", payload="draft", complete=False
    )

    outcome = recover_stranded(base)

    assert (canonical / "payload.txt").read_text() == "live"
    assert outcome.restored == ()
    assert not staging.exists()
    assert (base / QUARANTINE_DIRNAME / "docs" / staging.name / "payload.txt").is_file()


def test_complete_collection_discards_superseded_trash(tmp_path: Path) -> None:
    """Crash after rename 2 / during cleanup: finish the interrupted ``rmtree``."""
    base = tmp_path / "cols"
    base.mkdir()
    make_generation(base / "docs", payload="new")
    trash = make_generation(base / f"docs.trash-{dead_pid()}", payload="old")

    outcome = recover_stranded(base)

    assert not trash.exists()
    assert (base / "docs" / "payload.txt").read_text() == "new"
    assert outcome.discarded == (trash,)
    assert outcome.restored == ()
    # Nothing was quarantined: the trash was provably superseded.
    assert outcome.quarantined == ()


def test_corrupt_canonical_is_quarantined_for_a_complete_generation(
    tmp_path: Path,
) -> None:
    """A broken canonical dir is preserved aside; the complete copy is restored."""
    base = tmp_path / "cols"
    base.mkdir()
    make_generation(base / "docs", payload="broken", complete=False)
    trash = make_generation(base / f"docs.trash-{dead_pid()}", payload="good")

    outcome = recover_stranded(base)

    assert (base / "docs" / "payload.txt").read_text() == "good"
    assert not trash.exists()
    quarantined = base / QUARANTINE_DIRNAME / "docs" / "docs"
    assert quarantined.is_dir()
    assert (quarantined / "payload.txt").read_text() == "broken"
    assert outcome.restored == (("docs", base / "docs"),)


def test_recovery_is_idempotent(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    base.mkdir()
    pid = dead_pid()
    make_generation(base / f"docs.trash-{pid}", payload="old")
    make_generation(base / f"docs.tmp-{pid}-abcdef12", payload="new")

    first = recover_stranded(base)
    second = recover_stranded(base)

    assert first.changed is True
    assert second == RecoveryOutcome()
    assert second.changed is False


def test_recovery_only_touches_requested_names(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    base.mkdir()
    pid = dead_pid()
    make_generation(base / f"alpha.trash-{pid}", payload="old")
    make_generation(base / f"alpha.tmp-{pid}-abcdef12", payload="new")
    make_generation(base / f"beta.tmp-{pid}-abcdef12", payload="draft")

    outcome = recover_stranded(base, names=["alpha"])

    assert outcome.restored == (("alpha", base / "alpha"),)
    assert (base / f"beta.tmp-{pid}-abcdef12").is_dir()
    assert not (base / "beta").exists()


def test_live_writer_staging_dir_is_left_alone(tmp_path: Path) -> None:
    """A strand whose pid is still running belongs to an in-flight build."""
    base = tmp_path / "cols"
    base.mkdir()
    writer = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        live = make_generation(base / f"docs.tmp-{writer.pid}-abcdef12", payload="new")
        outcome = recover_stranded(base)
        assert live.is_dir()
        assert outcome.changed is False
    finally:
        writer.terminate()
        writer.wait(timeout=10)


def test_v1_generations_are_left_untouched(tmp_path: Path) -> None:
    """v1 has no ``version`` marker and is frozen: not this path's business."""
    base = tmp_path / "cols"
    base.mkdir()
    legacy = make_generation(
        base / f"docs.trash-{dead_pid()}", payload="v1", version=None
    )

    outcome = recover_stranded(base)

    assert legacy.is_dir()
    assert outcome.changed is False
    assert outcome.unrecoverable == ()


def test_quarantine_never_overwrites_an_earlier_incident(tmp_path: Path) -> None:
    base = tmp_path / "cols"
    base.mkdir()
    pid = dead_pid()
    first = make_generation(base / f"docs.trash-{pid}", payload="old")
    already = base / QUARANTINE_DIRNAME / "docs" / first.name
    make_generation(already, payload="earlier-incident")
    make_generation(base / f"docs.tmp-{pid}-abcdef12", payload="new")

    outcome = recover_stranded(base)

    assert (already / "payload.txt").read_text() == "earlier-incident"
    assert dict(outcome.quarantined)["docs"] == already.with_name(f"{first.name}-1")
    # An operator log names what happened and where it went.
    assert (already.parent / "recovery.log").is_file()


def test_both_discovery_sites_recover_before_listing(tmp_path: Path) -> None:
    """The choke points every surface goes through heal the strand themselves."""
    base = tmp_path / "cols"
    base.mkdir()
    pid = dead_pid()
    make_generation(base / f"docs.trash-{pid}", payload="old")
    make_generation(base / f"docs.tmp-{pid}-abcdef12", payload="new")

    assert discover_v2_collections(base) == ["docs"]
    assert (base / "docs" / "payload.txt").read_text() == "new"

    # Second incident, healed by the facade's own enumeration instead.
    make_generation(base / f"notes.trash-{pid}", payload="old")
    make_generation(base / f"notes.tmp-{pid}-abcdef12", payload="new")
    assert _existing_collection_names(str(base)) == ["docs", "notes"]


def test_explicit_open_of_unrecoverable_collection_fails_loud(tmp_path: Path) -> None:
    """A requested collection whose data was quarantined must not read as absent."""
    import indexed.core.engine as facade

    base = tmp_path / "cols"
    base.mkdir()
    make_generation(base / f"docs.tmp-{dead_pid()}-abcdef12", payload="new")

    with pytest.raises(CollectionRecoveryError) as excinfo:
        facade.status(collection_names=["docs"], collections_path=str(base))

    message = str(excinfo.value)
    assert "docs" in message
    assert str(base / QUARANTINE_DIRNAME / "docs") in message
    assert excinfo.value.quarantine_path == base / QUARANTINE_DIRNAME / "docs"
    # The data itself is still on disk for the operator.
    assert (base / QUARANTINE_DIRNAME / "docs").is_dir()


def test_sweep_never_raises_for_a_quarantined_collection(tmp_path: Path) -> None:
    """A listing must keep working while an unrecoverable strand is quarantined."""
    import indexed.core.engine as facade

    base = tmp_path / "cols"
    base.mkdir()
    make_generation(base / "healthy", payload="live")
    make_generation(base / f"docs.tmp-{dead_pid()}-abcdef12", payload="new")

    assert _existing_collection_names(str(base)) == ["healthy"]
    # No raise: the unrecoverable strand is quarantined, the listing survives.
    assert isinstance(facade.status(collections_path=str(base)), list)


# --- review fixes on #244: liveness is weaker than it looks -------------------


def test_non_posix_liveness_is_never_probed_and_never_swept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows has no signal-0 probe: ``os.kill`` there is ``TerminateProcess``.

    Recovery must treat liveness as unknowable on a non-POSIX platform — never
    probe (which would KILL the recorded process) and never sweep — and still
    explain the strand instead of hiding it behind "not found".
    """
    import indexed.core.recovery as recovery_module

    base = tmp_path / "cols"
    base.mkdir()
    pid = dead_pid()
    strand = make_generation(base / f"docs.tmp-{pid}-abcdef12", payload="new")

    probed: list[int] = []
    monkeypatch.setattr(recovery_module, "_POSIX", False)
    monkeypatch.setattr(
        recovery_module.os, "kill", lambda probed_pid, _sig: probed.append(probed_pid)
    )

    outcome = recover_stranded(base)

    assert probed == []  # os.kill would have terminated the recorded process
    assert strand.is_dir()
    assert outcome.changed is False
    reason = outcome.reason_for("docs")
    assert reason is not None and "cannot be probed" in reason


def test_own_pid_strand_is_an_in_flight_build_not_a_corpse(tmp_path: Path) -> None:
    """A concurrent read must not quarantine this process's own staging dir.

    In the long-lived MCP server a strand carries OUR pid while a create/update
    is in flight; sweeping it would destroy the build mid-swap.
    """
    base = tmp_path / "cols"
    base.mkdir()
    pid = os.getpid()
    staging = make_generation(base / f"docs.tmp-{pid}-abcdef12", payload="new")
    trash = make_generation(base / f"docs.trash-{pid}", payload="old")

    outcome = recover_stranded(base)

    assert staging.is_dir() and trash.is_dir()
    assert outcome.changed is False
    assert not (base / QUARANTINE_DIRNAME / "docs").exists()
    # In-flight is expected, not a failure: nothing to explain to the operator.
    assert outcome.reason_for("docs") is None


def test_strand_held_by_a_live_pid_reports_a_reason(tmp_path: Path) -> None:
    """A recycled pid is alive but will never finish: record why, never sweep."""
    import indexed.core.engine as facade

    base = tmp_path / "cols"
    base.mkdir()
    writer = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        strand = make_generation(
            base / f"docs.tmp-{writer.pid}-abcdef12", payload="new"
        )

        outcome = recover_stranded(base)

        assert strand.is_dir()
        assert outcome.changed is False
        reason = outcome.reason_for("docs")
        assert reason is not None and f"pid {writer.pid}" in reason
        # The hold is recorded durably, so an explicit open explains itself
        # instead of returning a bare "not found".
        with pytest.raises(CollectionRecoveryError) as excinfo:
            facade.status(collection_names=["docs"], collections_path=str(base))
        assert "recycled" in str(excinfo.value)
    finally:
        writer.terminate()
        writer.wait(timeout=10)


def test_unfiltered_search_explains_a_quarantined_collection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The durable marker outlives the one-shot pass that quarantined the data.

    After the strands are moved there is nothing left to detect, so only the
    marker can keep an unfiltered read from answering "no results found" for
    data sitting under ``.recovery/``.
    """
    import indexed.core.engine as facade
    import indexed.core.v1.engine.services as v1_services

    base = tmp_path / "cols"
    base.mkdir()
    make_generation(base / "healthy", payload="live", version=None, complete=False)
    make_generation(base / f"docs.tmp-{dead_pid()}-abcdef12", payload="new")
    monkeypatch.setattr(
        v1_services, "search", lambda query, **kwargs: {"healthy": {"documents": []}}
    )

    first = facade.search("q", collections_path=str(base))
    marker = base / QUARANTINE_DIRNAME / "docs" / "quarantine.json"
    assert marker.is_file()
    assert "error" in first["docs"]

    # Second read: the strand is gone, only the marker remains — and it is
    # still re-read, so the explanation does not depend on the first pass.
    second = facade.search("q", collections_path=str(base))
    assert "healthy" in second
    assert str(base / QUARANTINE_DIRNAME / "docs") in second["docs"]["error"]


# --- review round 2 on #244: a marker must not claim what was never moved ----


def test_hold_that_stops_being_stranded_leaves_no_marker(tmp_path: Path) -> None:
    """A hold moves NOTHING, so it may not promise a preserved copy.

    Two processes: one creating the collection, one reading. The reader's
    marker used to outlive the creator's abort, turning a name that never
    existed into a permanent recovery failure on every read.
    """
    import indexed.core.engine as facade
    from indexed.core.recovery import quarantine_reasons

    base = tmp_path / "cols"
    base.mkdir()
    writer = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        make_generation(base / f"docs.tmp-{writer.pid}-abcdef12", payload="new")
        with pytest.raises(CollectionRecoveryError) as held:
            facade.status(collection_names=["docs"], collections_path=str(base))
        # The hold explains itself (finding 3) but claims no preserved copy.
        assert f"pid {writer.pid}" in str(held.value)
        assert held.value.quarantine_path is None
        assert not (base / QUARANTINE_DIRNAME / "docs").exists()
    finally:
        writer.terminate()
        writer.wait(timeout=10)

    # The writer aborted and its staging directory is gone: nothing is stranded
    # any more, so the name is simply absent — never a recovery failure.
    for strand in base.glob("docs.tmp-*"):
        strand.rename(tmp_path / "gone")
    assert quarantine_reasons(base) == {}
    assert facade.status(collection_names=["docs"], collections_path=str(base)) == []


def test_incomplete_canonical_claims_no_quarantine_but_names_the_data(
    tmp_path: Path,
) -> None:
    """Repro B: nothing moved, so the error points at the canonical directory."""
    import indexed.core.engine as facade

    base = tmp_path / "cols"
    base.mkdir()
    canonical = make_generation(base / "docs", payload="broken", complete=False)
    make_generation(
        base / f"docs.tmp-{dead_pid()}-abcdef12", payload="new", complete=False
    )

    with pytest.raises(CollectionRecoveryError) as excinfo:
        facade.status(collection_names=["docs"], collections_path=str(base))

    error = excinfo.value
    assert error.quarantine_path is None
    assert error.canonical_path == canonical
    assert str(canonical) in str(error)
    assert "incomplete" in str(error)
    # The operator's data never left its place and nothing empty was invented.
    assert canonical.is_dir()
    assert not (base / QUARANTINE_DIRNAME / "docs").exists()


def test_marker_with_nothing_preserved_is_ignored_on_read(tmp_path: Path) -> None:
    """A marker written in the old, empty shape stops explaining anything."""
    from indexed.core.recovery import quarantine_reasons

    base = tmp_path / "cols"
    root = base / QUARANTINE_DIRNAME / "docs"
    root.mkdir(parents=True)
    (root / "quarantine.json").write_text(
        json.dumps({"collection": "docs", "reason": "held by pid 1", "preserved": []}),
        encoding="utf-8",
    )

    assert quarantine_reasons(base) == {}
