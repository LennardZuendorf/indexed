"""Characterization: `config set` -> read-back round-trip through the real store.

Drives the real CLI ``config set`` and proves the value is durably persisted and
read back by a *fresh* ``ConfigService`` loading from disk — the read-mostly
config write path that foundation/4 and foundation/9 later harden. Green
characterization: pins current correct behavior of the single write path.
"""

from __future__ import annotations

from typer.testing import CliRunner

from indexed.cli.app import app

runner = CliRunner()

KEY = "core.v1.search.max_docs"


def test_config_set_get_roundtrip(local_workspace) -> None:
    from indexed.config import ConfigService

    # --- set via the real CLI write path ---------------------------------
    result = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "config", "set", KEY, "7"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr

    # --- read back through a FRESH store loaded from disk ----------------
    ConfigService.reset()
    service = ConfigService.instance(
        workspace=local_workspace.root, mode_override="local"
    )
    assert service.get(KEY) == 7

    # --- overwrite and confirm the new value round-trips too -------------
    result = runner.invoke(
        app, ["--local", "--log-level", "ERROR", "config", "set", KEY, "3"]
    )
    assert result.exit_code == 0, result.stdout + result.stderr

    ConfigService.reset()
    service = ConfigService.instance(
        workspace=local_workspace.root, mode_override="local"
    )
    assert service.get(KEY) == 3
