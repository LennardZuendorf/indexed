"""Unit tests for the opt-in collection watcher (`index watch`).

The loop is exercised with an injected clock/sleep so a burst is deterministic
and instant; the signature tests run against a real temporary tree so the
gitignore/excluded-dir behaviour is proven, not asserted.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app
from indexed.cli.knowledge.commands import watch_service
from indexed.cli.watch_config import WatchConfig

runner = CliRunner()

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

SIG_A = watch_service.WatchSignature(files=1, digest="a")
SIG_B = watch_service.WatchSignature(files=2, digest="b")
SIG_C = watch_service.WatchSignature(files=3, digest="c")


class FakeClock:
    """Deterministic monotonic clock advanced by ``sleep``."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += max(seconds, 0.0)


def _run(scan_sequence, *, apply_update, stop_on_apply=True, max_consecutive=3):
    """Drive ``run_watch_loop`` over a finite scan sequence; return the outcome."""
    clock = FakeClock()
    scans = iter(scan_sequence)
    exhausted = object()
    applied: list[int] = []
    errors: list[str] = []
    infos: list[str] = []
    stop = threading.Event()

    def scan():
        nxt = next(scans, exhausted)
        if nxt is exhausted:
            stop.set()
            return scan_sequence[-1]
        return nxt

    def apply():
        applied.append(1)
        if stop_on_apply:
            stop.set()
        apply_update()

    code = watch_service.run_watch_loop(
        scan=scan,
        apply_update=apply,
        debounce_seconds=2.0,
        poll_interval_seconds=1.0,
        log_info=infos.append,
        log_error=errors.append,
        stop=stop,
        max_consecutive_failures=max_consecutive,
        clock=clock.clock,
        sleep=clock.sleep,
    )
    return code, applied, errors, infos


def test_burst_of_changes_runs_exactly_one_update():
    """Five edits inside one debounce window must produce ONE update pass."""
    scan_sequence = [SIG_A] + [SIG_A] + [SIG_B] + [SIG_C] * 8

    code, applied, _errors, _infos = _run(
        scan_sequence, apply_update=lambda: None, stop_on_apply=False
    )

    assert code == 0
    assert len(applied) == 2, "one startup update and one coalesced burst update"


def test_quiet_tree_only_updates_at_startup():
    code, applied, _errors, _infos = _run(
        [SIG_A] * 6, apply_update=lambda: None, stop_on_apply=False
    )

    assert code == 0
    assert len(applied) == 1


def test_missing_source_path_blocks_the_update_and_resumes():
    """A vanished path must never reach `update` — that would empty the collection."""
    scan_sequence = [SIG_A, SIG_A, None, None, SIG_A, SIG_B, SIG_B, SIG_B, SIG_B]

    code, applied, errors, infos = _run(
        scan_sequence, apply_update=lambda: None, stop_on_apply=False
    )

    assert code == 0
    assert len(applied) == 2
    assert len(errors) == 1, "the vanished path is reported once, not every poll"
    assert "disappeared" in errors[0]
    assert any("is back" in message for message in infos)


def test_repeated_update_failures_exit_nonzero():
    def boom() -> None:
        raise RuntimeError("collection vanished")

    code, applied, errors, _infos = _run(
        [SIG_A] + [SIG_B] * 40,
        apply_update=boom,
        stop_on_apply=False,
        max_consecutive=3,
    )

    assert code == 1
    assert len(applied) == 3
    assert len(errors) == 3
    assert "update pass failed (3/3)" in errors[-1]


def test_signature_ignores_gitignored_and_excluded_files(tmp_path: Path):
    tree = tmp_path / "corpus"
    tree.mkdir()
    (tree / "kept.txt").write_text("tracked content\n")
    (tree / ".gitignore").write_text("ignored.txt\nbuild/\n")
    (tree / "ignored.txt").write_text("noise\n")
    (tree / "build").mkdir()
    (tree / "build" / "artifact.txt").write_text("noise\n")
    (tree / "node_modules").mkdir()
    (tree / "node_modules" / "dep.js").write_text("noise\n")

    before = watch_service.signature_for(tree)
    assert before is not None and before.files == 2  # kept.txt + .gitignore

    (tree / "ignored.txt").write_text("changed noise\n")
    (tree / "build" / "artifact.txt").write_text("changed noise\n")
    (tree / "node_modules" / "dep.js").write_text("changed noise\n")
    assert watch_service.signature_for(tree) == before

    (tree / "kept.txt").write_text("tracked content edited\n")
    after = watch_service.signature_for(tree)
    assert after is not None and after.digest != before.digest


def test_signature_is_none_when_the_source_path_is_missing(tmp_path: Path):
    assert watch_service.signature_for(tmp_path / "gone") is None


def test_iter_watched_files_skips_vcs_and_excluded_dirs(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("x")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "m.pyc").write_text("x")

    names = sorted(p.name for p in watch_service.iter_watched_files(tmp_path))

    assert names == ["a.txt"]


def _patch_watch_wiring(monkeypatch, tmp_path: Path, status):
    from indexed.cli import composition
    import indexed.core.engine as engine

    config_service = MagicMock()
    config_service.resolver.resolve_root.return_value = tmp_path / "storage"
    config_service.bind.return_value.get.return_value = WatchConfig()
    cli_ctx = SimpleNamespace(
        collections_path=tmp_path / "collections",
        caches_path=tmp_path / "caches",
        mode="local",
        config_service=config_service,
    )
    monkeypatch.setattr(
        composition, "resolve_collections_context", lambda **kwargs: cli_ctx
    )
    monkeypatch.setattr(composition, "wiring_kwargs_for_update", lambda ctx: {})
    monkeypatch.setattr(engine, "status", lambda *args, **kwargs: status)
    return cli_ctx


def test_watch_command_is_registered_both_ways():
    for invocation in (["index", "watch"], ["watch"]):
        result = runner.invoke(app, [*invocation, "--help"])
        assert result.exit_code == 0, result.stdout
        # Strip ANSI: with color forced on (CI), Click wraps long flag names in
        # escape codes and a plain substring match splits "--debounce".
        help_text = ANSI_ESCAPE.sub("", result.stdout)
        assert "--debounce" in help_text
        assert "--poll-interval" in help_text


def test_watch_refuses_a_non_local_source(monkeypatch, tmp_path: Path):
    _patch_watch_wiring(
        monkeypatch,
        tmp_path,
        [SimpleNamespace(name="jira-docs", source_type="jira", indexers=["default"])],
    )

    result = runner.invoke(app, ["--local", "watch", "jira-docs"])

    assert result.exit_code == 2
    # The message is rendered inside a Rich panel, so assert the fragments that
    # sit on one line rather than the whole sentence.
    assert "jira-docs" in result.stdout and "localFiles" in result.stdout


def test_watch_refuses_a_missing_source_path(monkeypatch, tmp_path: Path):
    collections = tmp_path / "collections"
    (collections / "docs").mkdir(parents=True)
    (collections / "docs" / "manifest.json").write_text(
        '{"reader": {"type": "localFiles", "basePath": "%s"}}' % (tmp_path / "gone")
    )
    _patch_watch_wiring(
        monkeypatch,
        tmp_path,
        [SimpleNamespace(name="docs", source_type="localFiles", indexers=["default"])],
    )

    result = runner.invoke(app, ["--local", "watch", "docs"])

    assert result.exit_code == 2
    assert "gone" in result.stdout


def test_watch_once_runs_a_single_update_pass(monkeypatch, tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text("a")
    collections = tmp_path / "collections"
    (collections / "docs").mkdir(parents=True)
    (collections / "docs" / "manifest.json").write_text(
        '{"reader": {"type": "localFiles", "basePath": "%s"}}' % corpus
    )
    _patch_watch_wiring(
        monkeypatch,
        tmp_path,
        [SimpleNamespace(name="docs", source_type="localFiles", indexers=["default"])],
    )
    import indexed.core.engine as engine

    calls: list[list] = []
    monkeypatch.setattr(engine, "update", lambda configs, **kw: calls.append(configs))

    result = runner.invoke(app, ["--local", "watch", "docs", "--once"])

    assert result.exit_code == 0, result.stdout
    assert len(calls) == 1
    assert calls[0][0].name == "docs"


def test_watch_rejects_positional_and_option_together(monkeypatch, tmp_path: Path):
    _patch_watch_wiring(monkeypatch, tmp_path, [])

    result = runner.invoke(app, ["--local", "watch", "a", "--collection", "b"])

    assert result.exit_code == 1
    assert "Pass the collection once" in result.stdout


@pytest.mark.parametrize("value", [0.0, -1.0])
def test_watch_config_rejects_non_positive_cadence(value: float):
    with pytest.raises(Exception):
        WatchConfig(debounce_seconds=value)
    with pytest.raises(Exception):
        WatchConfig(poll_interval_seconds=value)


def test_resolve_watch_config_uses_defaults_when_section_is_absent():
    """An unconfigured project must get the defaults, not a KeyError."""
    from indexed.cli.composition import register_app_config
    from indexed.cli.watch_config import resolve_watch_config
    from indexed.config import get_config

    config_service = get_config(mode_override="global")
    register_app_config(config_service)

    resolved = resolve_watch_config(config_service)

    assert resolved.debounce_seconds == 2.0
    assert resolved.poll_interval_seconds == 2.0


def test_resolve_watch_config_reads_a_configured_section():
    from indexed.cli.composition import register_app_config
    from indexed.cli.watch_config import resolve_watch_config
    from indexed.config import get_config, reload as reload_config

    global_config = Path.home() / ".indexed" / "config.toml"
    global_config.parent.mkdir(parents=True, exist_ok=True)
    global_config.write_text("[watch]\ndebounce_seconds = 5.5\n")
    reload_config()
    config_service = get_config(mode_override="global")
    register_app_config(config_service)

    resolved = resolve_watch_config(config_service)

    assert resolved.debounce_seconds == 5.5
    assert resolved.poll_interval_seconds == 2.0


def test_watch_ignores_custom_storage_writes(monkeypatch, tmp_path: Path):
    corpus = tmp_path / "corpus"
    storage = corpus / "custom-store"
    collections = storage / "data" / "collections"
    (collections / "docs").mkdir(parents=True)
    (corpus / "source.txt").write_text("source")
    (collections / "docs" / "manifest.json").write_text(
        '{"reader": {"type": "localFiles", "basePath": "%s"}}' % corpus
    )
    ctx = _patch_watch_wiring(
        monkeypatch,
        tmp_path,
        [SimpleNamespace(name="docs", source_type="localFiles", indexers=["default"])],
    )
    ctx.collections_path = collections
    ctx.config_service.resolver.resolve_root.return_value = storage

    def check_loop(*, scan, **kwargs):
        before = scan()
        (storage / "data" / "new-state").write_text("update")
        assert scan() == before
        (corpus / "source.txt").write_text("changed source")
        assert scan() != before
        return 0

    monkeypatch.setattr(watch_service, "run_watch_loop", check_loop)
    result = runner.invoke(app, ["watch", "docs"])
    assert result.exit_code == 0, repr(result.exception)


@pytest.mark.parametrize("option", ["--debounce", "--poll-interval"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_watch_rejects_non_positive_cli_cadence(option, value):
    result = runner.invoke(app, ["watch", "docs", option, value])
    assert result.exit_code != 0
    assert option in result.output


def test_source_disappearing_at_update_resumes_without_failure(tmp_path):
    import shutil
    from indexed.connectors.files.connector import FileSystemConnector

    source = tmp_path / "source"
    source.mkdir()
    (source / "kept.txt").write_text("first")
    connector = FileSystemConnector(path=str(source), change_tracking="content_hash")
    state = connector.build_state()
    clock = FakeClock()
    stop = threading.Event()
    errors, infos, updates, deletions = [], [], [], []
    scans = 0

    def scan():
        nonlocal scans
        scans += 1
        if scans == 2:
            (source / "kept.txt").write_text("changed")
        if scans == 7:
            source.mkdir()
            (source / "kept.txt").write_text("restored")
        if scans > 12:
            stop.set()
        return watch_service.signature_for(source)

    def update():
        if not updates:
            updates.append("startup")
        elif len(updates) == 1:
            updates.append("disappeared")
            shutil.rmtree(source)
            deletions.extend(connector.get_changes(state))
        else:
            updates.append("resumed")
            stop.set()

    code = watch_service.run_watch_loop(
        scan=scan,
        apply_update=update,
        debounce_seconds=1,
        poll_interval_seconds=1,
        log_info=infos.append,
        log_error=errors.append,
        stop=stop,
        clock=clock.clock,
        sleep=clock.sleep,
    )
    assert code == 0
    assert updates == ["startup", "disappeared", "resumed"]
    assert deletions == []
    assert len(errors) == 1 and "disappeared" in errors[0]
    assert any("resuming" in msg for msg in infos)


def test_watch_signature_matches_manifest_reader_exclusion_override(tmp_path: Path):
    import json
    from indexed.cli.knowledge.commands.update_service import (
        _read_manifest_reader_config,
    )
    from indexed.connectors.files.files_document_reader import FilesDocumentReader

    source = tmp_path / "source"
    (source / "node_modules").mkdir(parents=True)
    (source / "other").mkdir()
    included = source / "node_modules" / "sample.txt"
    excluded = source / "other" / "skip.txt"
    included.write_text("one")
    excluded.write_text("ignore")
    reader = FilesDocumentReader(
        base_path=str(source), excluded_dirs=["other"], respect_gitignore=False
    )
    collections = tmp_path / "collections"
    (collections / "docs").mkdir(parents=True)
    (collections / "docs" / "manifest.json").write_text(
        json.dumps({"reader": reader.get_reader_details()})
    )
    config = _read_manifest_reader_config("docs", str(collections))
    assert set(reader._iter_file_paths()) == {str(included)}

    def scan():
        return watch_service.signature_for(
            source,
            excluded_dirs=tuple(config.get("excludedDirs") or ()),
            respect_gitignore=config.get("respectGitignore", True),
        )

    before = scan()
    excluded.write_text("ignored changed")
    assert scan() == before
    included.write_text("content changed")
    assert scan() != before


def test_watch_signature_matches_reader_defaults_and_gitignore(tmp_path: Path):
    from indexed.connectors.files.files_document_reader import FilesDocumentReader

    (tmp_path / "node_modules").mkdir()
    default_excluded = tmp_path / "node_modules" / "dependency.txt"
    default_excluded.write_text("one")
    (tmp_path / ".gitignore").write_text("ignored.txt\n")
    ignored = tmp_path / "ignored.txt"
    ignored.write_text("one")
    kept = tmp_path / "kept.txt"
    kept.write_text("one")
    reader = FilesDocumentReader(base_path=str(tmp_path))
    assert set(reader._iter_file_paths()) == {str(kept), str(tmp_path / ".gitignore")}
    before = watch_service.signature_for(tmp_path)
    default_excluded.write_text("changed")
    ignored.write_text("changed")
    assert watch_service.signature_for(tmp_path) == before
    kept.write_text("changed")
    assert watch_service.signature_for(tmp_path) != before


def test_startup_updates_existing_change_without_new_edit():
    code, applied, errors, _infos = _run([SIG_A] * 5, apply_update=lambda: None)
    assert code == 0
    assert len(applied) == 1
    assert errors == []


def test_startup_failure_retries_without_new_edit():
    attempts = []
    stop = threading.Event()
    clock = FakeClock()

    def update():
        attempts.append(clock.now)
        if len(attempts) == 1:
            raise RuntimeError("temporary")
        stop.set()

    errors = []
    code = watch_service.run_watch_loop(
        scan=lambda: SIG_A,
        apply_update=update,
        debounce_seconds=2,
        poll_interval_seconds=1,
        log_info=lambda _: None,
        log_error=errors.append,
        stop=stop,
        clock=clock.clock,
        sleep=clock.sleep,
    )
    assert code == 0
    assert len(attempts) == 2 and attempts[1] >= attempts[0] + 3
    assert len(errors) == 1


def test_change_during_startup_update_triggers_followup():
    current = SIG_A
    stop = threading.Event()
    clock = FakeClock()
    applied = []

    def update():
        nonlocal current
        applied.append(current)
        if len(applied) == 1:
            current = SIG_B
        else:
            stop.set()

    scans = 0

    def scan():
        nonlocal scans
        scans += 1
        if scans > 10:
            stop.set()
        return current

    code = watch_service.run_watch_loop(
        scan=scan,
        apply_update=update,
        debounce_seconds=2,
        poll_interval_seconds=1,
        log_info=lambda _: None,
        log_error=lambda _: None,
        stop=stop,
        clock=clock.clock,
        sleep=clock.sleep,
    )
    assert code == 0
    assert applied == [SIG_A, SIG_B]
