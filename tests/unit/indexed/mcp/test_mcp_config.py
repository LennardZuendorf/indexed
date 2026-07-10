"""Tests for MCP shared config resolution helpers."""

from unittest.mock import MagicMock, patch

from indexed.mcp.config import resolve_cli_context, resolve_config
from indexed.cli.composition import CliContext


def test_resolve_config_reads_from_lifespan_state() -> None:
    ctx = MagicMock()
    ctx.lifespan_context = {"search_config": {"k": "v"}}
    assert resolve_config(ctx, "search_config", lambda: {"fallback": True}) == {
        "k": "v"
    }


def test_resolve_config_falls_back_to_loader() -> None:
    assert resolve_config(None, "search_config", lambda: 42) == 42


def test_resolve_config_ignores_bad_context() -> None:
    class BadCtx:
        @property
        def lifespan_context(self):
            raise TypeError("boom")

    assert resolve_config(BadCtx(), "x", lambda: "ok") == "ok"


def test_resolve_cli_context_from_lifespan() -> None:
    cli_ctx = MagicMock(spec=CliContext)
    ctx = MagicMock()
    ctx.lifespan_context = {"cli_context": cli_ctx}
    assert resolve_cli_context(ctx) is cli_ctx


def test_resolve_cli_context_builds_fresh_context() -> None:
    built = MagicMock(spec=CliContext)
    with patch("indexed.mcp.config.resolve_collections_context", return_value=built):
        assert resolve_cli_context(None) is built


def test_resolve_cli_context_ignores_bad_context() -> None:
    class BadCtx:
        @property
        def lifespan_context(self):
            raise AttributeError("nope")

    built = MagicMock(spec=CliContext)
    with patch("indexed.mcp.config.resolve_collections_context", return_value=built):
        assert resolve_cli_context(BadCtx()) is built
