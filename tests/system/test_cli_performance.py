"""Minimal system test for CLI help command."""

import pytest
from typer.testing import CliRunner
from indexed.app import app


@pytest.mark.benchmark(min_rounds=3, max_time=1.0)
def test_cli_help(benchmark):
    runner = CliRunner()

    def run_help():
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        stdout = result.stdout.lower()
        assert "help" in stdout
        assert "options" in stdout
        assert "logging" in stdout
        assert "knowledge" in stdout
        assert "configuration management" in stdout
        assert "mcp server" in stdout
        assert "resources" in stdout

    # Run performance benchmark on the CLI help invocation (includes all assertions)
    benchmark(run_help)
