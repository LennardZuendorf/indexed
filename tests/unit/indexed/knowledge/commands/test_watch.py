"""Unit tests for the opt-in collection watcher (`index watch`).

The loop is exercised with an injected clock/sleep so a burst is deterministic
and instant; the signature tests run against a real temporary tree so the
gitignore/excluded-dir behaviour is proven, not asserted.
"""

from __future__ import annotations

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

    code, applied, _errors, _infos = _run(scan_sequence, apply_update=lambda: None)

    assert code == 0
    assert len(applied) == 1, "a burst must coalesce into a single update"


def test_quiet_tree_never_updates():
    code, applied, _errors, _infos = _run([SIG_A] * 6, apply_update=lambda: None)

    assert code == 0
    assert applied == []


def test_missing_source_path_blocks_the_update_and_resumes():
    """A vanished path must never reach `update` — that would empty the collection."""
    scan_sequence = [SIG_A, SIG_A, None, None, SIG_A, SIG_B, SIG_B, SIG_B, SIG_B]

    code, applied, errors, infos = _run(scan_sequence, apply_update=lambda: None)

    assert code == 0
    assert len(applied) == 1
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
        assert "--debounce" in result.stdout


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
