"""Tests for MCP CLI commands."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from indexed.mcp.cli import (
    _build_inspect_summary,
    app,
    dev_impl,
    inspect_impl,
    run_impl,
)


runner = CliRunner()


class TestBuildInspectSummary:
    def test_summary_counts(self) -> None:
        summary = _build_inspect_summary(
            name="MyServer",
            fastmcp_version="3.2.4",
            mcp_version="1.25.0",
            tools=[MagicMock(), MagicMock()],
            resources=[MagicMock()],
            templates=[MagicMock(), MagicMock()],
            prompts=[],
        )
        assert summary["name"] == "MyServer"
        assert summary["fastmcp_version"] == "3.2.4"
        assert summary["mcp_version"] == "1.25.0"
        assert summary["tools_count"] == 2
        # resources_count rolls templates into the resource total
        assert summary["resources_count"] == 3
        assert summary["templates_count"] == 2
        assert summary["prompts_count"] == 0
        assert summary["website_url"] is None


class TestRunImpl:
    @patch("indexed.mcp.server.mcp")
    def test_stdio_passes_log_level_only(self, mock_mcp: MagicMock) -> None:
        run_impl(transport="stdio", log_level="DEBUG", show_banner=False)

        mock_mcp.run.assert_called_once_with(
            transport="stdio", show_banner=False, log_level="DEBUG"
        )
        kwargs = mock_mcp.run.call_args.kwargs
        assert "host" not in kwargs
        assert "port" not in kwargs

    @patch("indexed.mcp.server.mcp")
    def test_http_passes_host_port(self, mock_mcp: MagicMock) -> None:
        run_impl(
            transport="http",
            host="0.0.0.0",
            port=9000,
            log_level="INFO",
            show_banner=True,
        )

        mock_mcp.run.assert_called_once_with(
            transport="http",
            show_banner=True,
            host="0.0.0.0",
            port=9000,
            log_level="INFO",
        )

    @patch("indexed.mcp.server.mcp")
    def test_streamable_http_routes_to_http_branch(self, mock_mcp: MagicMock) -> None:
        run_impl(transport="streamable-http", host="127.0.0.1", port=8000)

        kwargs = mock_mcp.run.call_args.kwargs
        assert kwargs["transport"] == "streamable-http"
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8000

    @patch("indexed.mcp.server.mcp")
    def test_sse_routes_to_http_branch(self, mock_mcp: MagicMock) -> None:
        run_impl(transport="sse", host="127.0.0.1", port=8000)

        kwargs = mock_mcp.run.call_args.kwargs
        assert kwargs["transport"] == "sse"
        assert "host" in kwargs


class TestDevImpl:
    @patch("indexed.mcp.cli.subprocess.run")
    def test_invokes_fastmcp_dev(self, mock_run: MagicMock) -> None:
        import sys as _sys

        dev_impl()

        cmd = mock_run.call_args.args[0]
        assert cmd[:5] == [_sys.executable, "-m", "fastmcp.cli", "dev", "inspector"]
        assert mock_run.call_args.kwargs.get("check") is True

    @patch("indexed.mcp.cli.subprocess.run")
    def test_forwards_inspector_ports(self, mock_run: MagicMock) -> None:
        dev_impl(ui_port=3000, server_port=8001, inspector_version="0.5.0")

        cmd = mock_run.call_args.args[0]
        assert "--ui-port" in cmd
        assert "3000" in cmd
        assert "--server-port" in cmd
        assert "8001" in cmd
        assert "--inspector-version" in cmd
        assert "0.5.0" in cmd

    @patch("indexed.mcp.cli.subprocess.run")
    def test_called_process_error_exits_one(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.CalledProcessError(2, ["fastmcp", "dev"])

        with pytest.raises(typer.Exit) as exc:
            dev_impl()
        assert exc.value.exit_code == 1

    @patch("indexed.mcp.cli.subprocess.run")
    def test_missing_fastmcp_exits_one(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(typer.Exit) as exc:
            dev_impl()
        assert exc.value.exit_code == 1


class TestInspectImpl:
    @patch("indexed.mcp.server.mcp")
    def test_renders_panel(self, mock_mcp: MagicMock) -> None:
        # is_simple_output is imported lazily inside inspect_impl from
        # indexed.utils.simple_output; patch the originating module so the
        # lazy import sees the mock.
        from indexed.utils import simple_output

        with patch.object(simple_output, "is_simple_output", return_value=False):
            tool = MagicMock()
            tool.name = "search"
            mock_mcp.name = "Indexed MCP Server"
            mock_mcp.list_tools = MagicMock(return_value=_async_value([tool]))
            mock_mcp.list_resources = MagicMock(return_value=_async_value([]))
            mock_mcp.list_resource_templates = MagicMock(return_value=_async_value([]))
            mock_mcp.list_prompts = MagicMock(return_value=_async_value([]))

            inspect_impl()

    @patch("indexed.mcp.server.mcp")
    def test_failure_exits_one(self, mock_mcp: MagicMock) -> None:
        mock_mcp.list_tools = MagicMock(side_effect=RuntimeError("boom"))

        with pytest.raises(typer.Exit) as exc:
            inspect_impl()
        assert exc.value.exit_code == 1


class TestCommandRegistration:
    def test_run_command_help(self) -> None:
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--transport" in result.stdout
        assert "--host" in result.stdout
        assert "--port" in result.stdout
        assert "--log-level" in result.stdout

    def test_dev_command_help(self) -> None:
        result = runner.invoke(app, ["dev", "--help"])
        assert result.exit_code == 0
        assert "--ui-port" in result.stdout
        assert "--server-port" in result.stdout

    def test_inspect_command_help(self) -> None:
        result = runner.invoke(app, ["inspect", "--help"])
        assert result.exit_code == 0

    def test_fastmcp_command_removed(self) -> None:
        result = runner.invoke(app, ["fastmcp", "--help"])
        assert result.exit_code != 0


def _async_value(value):
    """Build a coroutine that resolves to value, for mocking async methods."""

    async def _coro():
        return value

    return _coro()
