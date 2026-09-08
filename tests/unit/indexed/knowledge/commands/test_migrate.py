"""CLI ``migrate`` command tests (core-v2/4, R7) — model-free.

Monkeypatches the facade-exposed service (``migrate.svc_migrate``) with a fake so
these exercise the THIN command's wiring + rendering only (option parsing,
``--from-source`` manifest-factory wiring, simple-output JSON vs Rich card, error
handling) without building a real collection or loading a model.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from indexed.cli.knowledge.commands import migrate as migrate_cmd
from indexed.core.errors import CoreV2Error
from indexed.core.v2.migration import MigrationResult
from indexed.cli.utils.simple_output import reset_simple_output, set_simple_output
from tests.unit.indexed.conftest import make_cli_context

runner = CliRunner()


@pytest.fixture(autouse=True)
def _patch_runtime_context():
    with (
        patch(
            "indexed.cli.composition.resolve_collections_context",
            side_effect=lambda *a, **k: make_cli_context(),
        ),
        patch(
            "indexed.cli.knowledge.commands.migrate.display_storage_mode_for_command",
            lambda *a, **k: None,
        ),
    ):
        yield


def _result(action: str = "migrate", **overrides) -> MigrationResult:
    base = dict(
        name="c1",
        action=action,
        dry_run=action == "dry-run",
        from_source=False,
        number_of_documents=2,
        number_of_chunks=3,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        vector_store="simple",
        backup_path="/cols/c1.v1-backup",
        backup_purged=False,
        validated=action == "migrate",
    )
    base.update(overrides)
    return MigrationResult(**base)  # type: ignore[arg-type]


def _install_svc(monkeypatch, fn):
    """Install a fake ``svc_migrate`` on the command module (bypasses __getattr__)."""
    monkeypatch.setattr(migrate_cmd, "svc_migrate", fn, raising=False)


def test_migrate_success_rich_render(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_svc(monkeypatch, lambda *a, **k: _result())
    result = runner.invoke(migrate_cmd.app, ["c1"])
    assert result.exit_code == 0, result.stdout
    assert "v2" in result.stdout
    assert "c1.v1-backup" in result.stdout  # backup-preserved hint


def test_migrate_dry_run_rich_render(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    def _svc(name, **kwargs):
        calls.update(kwargs)
        return _result(action="dry-run")

    _install_svc(monkeypatch, _svc)
    result = runner.invoke(migrate_cmd.app, ["c1", "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert calls["dry_run"] is True
    assert "no files were changed" in result.stdout.lower()


def test_migrate_simple_output_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_svc(monkeypatch, lambda *a, **k: _result())
    set_simple_output(True)
    try:
        result = runner.invoke(migrate_cmd.app, ["c1"])
    finally:
        reset_simple_output()
    assert result.exit_code == 0, result.stdout
    import json

    payload = json.loads(result.stdout)
    assert payload["status"] == "migrate"
    assert payload["collection"] == "c1"
    assert payload["vector_store"] == "simple"


def test_migrate_error_simple_output_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*a, **k):
        raise CoreV2Error("already a v2 collection")

    _install_svc(monkeypatch, _boom)
    set_simple_output(True)
    try:
        result = runner.invoke(migrate_cmd.app, ["c1"])
    finally:
        reset_simple_output()
    assert result.exit_code == 1
    import json

    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert "already a v2" in payload["error"]


def test_migrate_error_rich_exits_nonzero(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*a, **k):
        raise CoreV2Error("boom")

    _install_svc(monkeypatch, _boom)
    result = runner.invoke(migrate_cmd.app, ["c1"])
    assert result.exit_code == 1
    assert "Failed to migrate" in result.stdout


def test_migrate_offline_passes_no_manifest_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def _svc(name, **kwargs):
        captured.update(kwargs)
        return _result()

    _install_svc(monkeypatch, _svc)
    result = runner.invoke(migrate_cmd.app, ["c1"])
    assert result.exit_code == 0, result.stdout
    assert captured["manifest_factory"] is None  # offline default needs no wiring
    assert captured["from_source"] is False


def test_migrate_from_source_wires_manifest_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    sentinel = object()

    def _svc(name, **kwargs):
        captured.update(kwargs)
        return _result(from_source=True)

    _install_svc(monkeypatch, _svc)
    with patch(
        "indexed.cli.composition.make_manifest_factory",
        return_value=sentinel,
    ):
        result = runner.invoke(migrate_cmd.app, ["c1", "--from-source"])
    assert result.exit_code == 0, result.stdout
    assert captured["from_source"] is True
    assert captured["manifest_factory"] is sentinel


def test_migrate_via_collection_option(monkeypatch: pytest.MonkeyPatch) -> None:
    """L4: ``-c NAME`` must target NAME, not raise "No such option"."""
    _install_svc(monkeypatch, lambda *a, **k: _result())
    result = runner.invoke(migrate_cmd.app, ["-c", "c1"])
    assert result.exit_code == 0, result.stdout
    assert "v2" in result.stdout


def test_migrate_via_long_collection_option(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_svc(monkeypatch, lambda *a, **k: _result())
    result = runner.invoke(migrate_cmd.app, ["--collection", "c1"])
    assert result.exit_code == 0, result.stdout
    assert "v2" in result.stdout


def test_migrate_conflicting_positional_and_option_exits_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Different values for the positional and ``-c`` must error at exit 1."""
    _install_svc(monkeypatch, lambda *a, **k: _result())
    result = runner.invoke(migrate_cmd.app, ["c1", "-c", "c2"])
    assert result.exit_code == 1


def test_migrate_same_value_positional_and_option_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passing the SAME value both ways is not a conflict."""
    _install_svc(monkeypatch, lambda *a, **k: _result())
    result = runner.invoke(migrate_cmd.app, ["c1", "-c", "c1"])
    assert result.exit_code == 0, result.stdout


def test_migrate_neither_positional_nor_option_exits_1(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Today's required-arg behavior must be preserved: missing both must
    still error at exit 1 (was a Click UsageError exit 2 pre-change)."""
    _install_svc(monkeypatch, lambda *a, **k: _result())
    result = runner.invoke(migrate_cmd.app, [])
    assert result.exit_code == 1


def test_migrate_purge_backup_render(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_svc(
        monkeypatch,
        lambda *a, **k: _result(
            action="purge-backup", backup_path=None, backup_purged=True, validated=False
        ),
    )
    result = runner.invoke(migrate_cmd.app, ["c1", "--purge-backup"])
    assert result.exit_code == 0, result.stdout
    assert "backup" in result.stdout.lower()
