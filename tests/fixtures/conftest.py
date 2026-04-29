"""Shared test fixtures for all test types.

This module provides common fixtures that are used across unit, integration,
system, and benchmark tests. These fixtures handle temporary directories
and test data generation.
"""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def temp_workspace():
    """Create temporary workspace directory for entire test session.

    This directory is reused across all tests in the session for efficiency.
    Each test should create its own subdirectories to avoid conflicts.

    Yields:
        Path: Path to temporary workspace directory
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
