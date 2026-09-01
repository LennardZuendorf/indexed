"""Minimal system test for CLI help command."""

import webbrowser
import pytest
from typer.testing import CliRunner
from indexed.cli.app import app


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


def test_index_create_files_help_shows_engine_flag():
    """core-v2-discoverability/1 (R1): `--engine` is discoverable on the
    `index create files` subcommand's own --help, not only the root callback."""
    runner = CliRunner()
    result = runner.invoke(app, ["index", "create", "files", "--help"])
    assert result.exit_code == 0, result.stdout
    assert "--engine" in result.stdout


def test_index_create_group_help_shows_engine_flag():
    """core-v2-discoverability/1 (R1): R1 names BOTH surfaces — the leaf
    above and the GROUP itself. `index create --help` must list `--engine`
    too, or the flag stays invisible exactly where issue #188 says a user
    looks for it, one level up the command tree."""
    runner = CliRunner()
    result = runner.invoke(app, ["index", "create", "--help"])
    assert result.exit_code == 0, result.stdout
    assert "--engine" in result.stdout


@pytest.mark.benchmark(min_rounds=3, max_time=1.0)
def test_cli_license(benchmark):
    runner = CliRunner()

    def run_license():
        result = runner.invoke(app, ["license"])
        assert result.exit_code == 0
        stdout = result.stdout.lower()
        assert "indexed license" in stdout
        assert "sustainable use license" in stdout
        assert "acceptance" in stdout
        assert "copyright license" in stdout
        assert "limitations" in stdout
        assert "licensor" in stdout

    # Run performance benchmark on the CLI license invocation (includes all assertions)
    benchmark(run_license)


@pytest.mark.benchmark(min_rounds=3, max_time=1.0)
def test_cli_docs(benchmark, monkeypatch):
    runner = CliRunner()

    # Mock webbrowser.open to prevent actually opening a browser
    def fake_open(url):
        return True

    monkeypatch.setattr(webbrowser, "open", fake_open)

    def run_docs():
        result = runner.invoke(app, ["docs"])
        assert result.exit_code == 0
        stdout = result.stdout.lower()
        assert "opening" in stdout
        assert "documentation" in stdout
        assert "https://indexed.ignitr.dev/docs" in stdout

    # Run performance benchmark on the CLI docs invocation (includes all assertions)
    benchmark(run_docs)
