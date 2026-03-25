"""System test fixtures.

This module provides fixtures for system tests (CLI correctness, multi-module workflows).
It also handles TQDM configuration which is shared with benchmarks.
"""

import os

import pytest

if "TQDM_DISABLE" not in os.environ:
    os.environ["TQDM_DISABLE"] = "1"


def pytest_configure(config):
    """Pytest hook to ensure TQDM_DISABLE is set before any test imports."""
    # Force set TQDM_DISABLE before any tests run
    os.environ["TQDM_DISABLE"] = "1"


@pytest.fixture
def cli_runner():
    """Provide CliRunner instance for CLI tests."""
    from typer.testing import CliRunner

    return CliRunner()


@pytest.fixture
def cli_env(temp_workspace, monkeypatch):
    """Set up environment for CLI tests."""
    monkeypatch.chdir(temp_workspace)
    monkeypatch.setenv("TQDM_DISABLE", "1")
    return {"TQDM_DISABLE": "1"}
