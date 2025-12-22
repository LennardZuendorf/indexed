"""Tests for MCP CLI command building and execution."""

from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from indexed.mcp.cli import (
    app,
    _build_fastmcp_command,
    _get_server_path,
)


runner = CliRunner()


class TestBuildFastmcpCommand:
    """Tests for _build_fastmcp_command function."""

    def test_run_command_basic(self) -> None:
        """Test run command with default options."""
        cmd = _build_fastmcp_command("run")
        assert cmd[0] == "fastmcp"
        assert cmd[1] == "run"
        assert _get_server_path() in cmd
        # Default options should not be included
        assert "--transport" not in cmd
        assert "--host" not in cmd
        assert "--port" not in cmd

    def test_run_command_with_transport(self) -> None:
        """Test run command with non-default transport."""
        cmd = _build_fastmcp_command("run", transport="http")
        assert "--transport" in cmd
        assert "http" in cmd

    def test_run_command_with_host_and_port(self) -> None:
        """Test run command with custom host and port."""
        cmd = _build_fastmcp_command("run", host="0.0.0.0", port=9000)
        assert "--host" in cmd
        assert "0.0.0.0" in cmd
        assert "--port" in cmd
        assert "9000" in cmd

    def test_run_command_with_log_level(self) -> None:
        """Test run command with custom log level."""
        cmd = _build_fastmcp_command("run", log_level="DEBUG")
        assert "--log-level" in cmd
        assert "DEBUG" in cmd

    def test_run_command_with_env_options(self) -> None:
        """Test run command with environment options."""
        cmd = _build_fastmcp_command(
            "run",
            python="3.11",
            with_packages=["pandas", "numpy"],
            with_requirements="requirements.txt",
            with_editable="/path/to/project",
            project="/project/dir",
            skip_env=True,
        )
        assert "--python" in cmd
        assert "3.11" in cmd
        assert cmd.count("--with") == 2
        assert "pandas" in cmd
        assert "numpy" in cmd
        assert "--with-requirements" in cmd
        assert "requirements.txt" in cmd
        assert "--with-editable" in cmd
        assert "/path/to/project" in cmd
        assert "--project" in cmd
        assert "/project/dir" in cmd
        assert "--skip-env" in cmd

    def test_run_command_excludes_inspect_options(self) -> None:
        """Test that run command does not include inspect-specific options."""
        cmd = _build_fastmcp_command("run", format="mcp", output="manifest.json")
        assert "--format" not in cmd
        assert "-o" not in cmd
        assert "mcp" not in cmd
        assert "manifest.json" not in cmd

    def test_run_command_excludes_dev_options(self) -> None:
        """Test that run command does not include dev-specific options."""
        cmd = _build_fastmcp_command(
            "run",
            inspector_version="0.5.0",
            ui_port=3000,
            server_port=8001,
        )
        assert "--inspector-version" not in cmd
        assert "--ui-port" not in cmd
        assert "--server-port" not in cmd


class TestDevCommand:
    """Tests for dev command building."""

    def test_dev_command_basic(self) -> None:
        """Test dev command with default options."""
        cmd = _build_fastmcp_command("dev")
        assert cmd[0] == "fastmcp"
        assert cmd[1] == "dev"
        assert _get_server_path() in cmd

    def test_dev_command_with_inspector_options(self) -> None:
        """Test dev command includes inspector-specific options."""
        cmd = _build_fastmcp_command(
            "dev",
            inspector_version="0.5.0",
            ui_port=3000,
            server_port=8001,
        )
        assert "--inspector-version" in cmd
        assert "0.5.0" in cmd
        assert "--ui-port" in cmd
        assert "3000" in cmd
        assert "--server-port" in cmd
        assert "8001" in cmd

    def test_dev_command_with_transport_options(self) -> None:
        """Test dev command includes transport options (like run)."""
        cmd = _build_fastmcp_command(
            "dev",
            transport="http",
            host="0.0.0.0",
            port=9000,
            log_level="DEBUG",
        )
        assert "--transport" in cmd
        assert "http" in cmd
        assert "--host" in cmd
        assert "0.0.0.0" in cmd
        assert "--port" in cmd
        assert "9000" in cmd
        assert "--log-level" in cmd
        assert "DEBUG" in cmd

    def test_dev_command_excludes_inspect_options(self) -> None:
        """Test that dev command does not include inspect-specific options."""
        cmd = _build_fastmcp_command("dev", format="mcp", output="manifest.json")
        assert "--format" not in cmd
        assert "-o" not in cmd


class TestInspectCommand:
    """Tests for inspect command building."""

    def test_inspect_command_basic(self) -> None:
        """Test inspect command with default options."""
        cmd = _build_fastmcp_command("inspect")
        assert cmd[0] == "fastmcp"
        assert cmd[1] == "inspect"
        assert _get_server_path() in cmd

    def test_inspect_command_with_format(self) -> None:
        """Test inspect command with format option."""
        cmd = _build_fastmcp_command("inspect", format="mcp")
        assert "--format" in cmd
        assert "mcp" in cmd

    def test_inspect_command_with_output(self) -> None:
        """Test inspect command with output option."""
        cmd = _build_fastmcp_command("inspect", output="manifest.json")
        assert "-o" in cmd
        assert "manifest.json" in cmd

    def test_inspect_command_excludes_transport_options(self) -> None:
        """Test that inspect command does not include transport options."""
        cmd = _build_fastmcp_command(
            "inspect",
            transport="http",
            host="0.0.0.0",
            port=9000,
            log_level="DEBUG",
            no_banner=True,
        )
        assert "--transport" not in cmd
        assert "--host" not in cmd
        assert "--port" not in cmd
        assert "--log-level" not in cmd
        assert "--no-banner" not in cmd

    def test_inspect_command_excludes_env_options(self) -> None:
        """Test that inspect command does not include environment options."""
        cmd = _build_fastmcp_command(
            "inspect",
            python="3.11",
            with_packages=["pandas"],
            skip_env=True,
        )
        assert "--python" not in cmd
        assert "--with" not in cmd
        assert "--skip-env" not in cmd

    def test_inspect_command_excludes_dev_options(self) -> None:
        """Test that inspect command does not include dev-specific options."""
        cmd = _build_fastmcp_command(
            "inspect",
            inspector_version="0.5.0",
            ui_port=3000,
            server_port=8001,
        )
        assert "--inspector-version" not in cmd
        assert "--ui-port" not in cmd
        assert "--server-port" not in cmd


class TestCliCommands:
    """Tests for CLI command invocation."""

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_without_subcommand_runs_server(self, mock_execute: MagicMock) -> None:
        """Test that 'indexed mcp' without subcommand runs the server."""
        runner.invoke(app, [])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert cmd[1] == "run"

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_run_command(self, mock_execute: MagicMock) -> None:
        """Test that 'indexed mcp run' works correctly."""
        runner.invoke(app, ["run"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert cmd[1] == "run"

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_dev_command(self, mock_execute: MagicMock) -> None:
        """Test that 'indexed mcp dev' invokes fastmcp dev."""
        runner.invoke(app, ["dev"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert cmd[0] == "fastmcp"
        assert cmd[1] == "dev"

    @patch("indexed.mcp.cli.subprocess.run")
    def test_mcp_inspect_command(self, mock_subprocess: MagicMock) -> None:
        """Test that 'indexed mcp inspect' captures fastmcp output for processing."""
        # When inspect is called without format/output options, it captures output itself
        mock_subprocess.return_value = MagicMock(
            stdout='{"server": {"name": "test"}, "tools": [], "resources": [], "prompts": []}',
            stderr="",
            returncode=0,
        )
        runner.invoke(app, ["inspect"])
        mock_subprocess.assert_called_once()
        cmd = mock_subprocess.call_args[0][0]
        assert cmd[0] == "fastmcp"
        assert cmd[1] == "inspect"

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_inspect_with_format(self, mock_execute: MagicMock) -> None:
        """Test 'indexed mcp inspect --format mcp' passes correct options."""
        runner.invoke(app, ["inspect", "--format", "mcp"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert "--format" in cmd
        assert "mcp" in cmd

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_fastmcp_passthrough_quoted(self, mock_execute: MagicMock) -> None:
        """Test that 'indexed mcp fastmcp "version"' passes arguments through."""
        runner.invoke(app, ["fastmcp", "version"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert cmd == ["fastmcp", "version"]

    def test_mcp_fastmcp_no_args_shows_error(self) -> None:
        """Test that 'indexed mcp fastmcp' without args shows error."""
        result = runner.invoke(app, ["fastmcp"])
        assert result.exit_code == 1
        assert "No arguments provided" in result.output

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_fastmcp_args_prefix(self, mock_execute: MagicMock) -> None:
        """Test that 'indexed mcp fastmcp args=--help' passes --help to fastmcp."""
        runner.invoke(app, ["fastmcp", "args=--help"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert cmd == ["fastmcp", "--help"]

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_fastmcp_arg_prefix(self, mock_execute: MagicMock) -> None:
        """Test that 'indexed mcp fastmcp arg=version' works."""
        runner.invoke(app, ["fastmcp", "arg=version"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert cmd == ["fastmcp", "version"]

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_fastmcp_arguments_prefix(self, mock_execute: MagicMock) -> None:
        """Test that 'indexed mcp fastmcp arguments=version' works."""
        runner.invoke(app, ["fastmcp", "arguments=version"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert cmd == ["fastmcp", "version"]

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_fastmcp_subcommand_with_args_help(
        self, mock_execute: MagicMock
    ) -> None:
        """Test that 'indexed mcp fastmcp run args=--help' works."""
        runner.invoke(app, ["fastmcp", "run", "args=--help"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert cmd == ["fastmcp", "run", "--help"]

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_fastmcp_multiple_args(self, mock_execute: MagicMock) -> None:
        """Test multiple arguments with mixed patterns."""
        runner.invoke(app, ["fastmcp", "arg=install", "arg=cursor"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert cmd == ["fastmcp", "install", "cursor"]

    @patch("indexed.mcp.cli._execute_fastmcp")
    def test_mcp_dev_with_inspector_options(self, mock_execute: MagicMock) -> None:
        """Test dev command with inspector-specific options."""
        runner.invoke(app, ["dev", "--ui-port", "3000", "--server-port", "8001"])
        mock_execute.assert_called_once()
        cmd = mock_execute.call_args[0][0]
        assert "--ui-port" in cmd
        assert "3000" in cmd
        assert "--server-port" in cmd
        assert "8001" in cmd


class TestGetServerPath:
    """Tests for _get_server_path function."""

    def test_returns_absolute_path(self) -> None:
        """Test that server path is absolute."""
        path = _get_server_path()
        assert path.startswith("/") or path[1] == ":"  # Unix or Windows path

    def test_path_ends_with_server_py(self) -> None:
        """Test that server path ends with server.py."""
        path = _get_server_path()
        assert path.endswith("server.py")

    def test_path_contains_mcp_directory(self) -> None:
        """Test that server path contains mcp directory."""
        path = _get_server_path()
        assert "mcp" in path
