"""Shared test fixtures for all test types.

This module provides common fixtures that are used across unit, integration,
system, and benchmark tests. These fixtures handle temporary directories,
sample documents, and test data generation.
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


@pytest.fixture
def sample_documents(temp_workspace):
    """Create sample document structure for testing.

    Creates a temporary directory with sample markdown documents
    that can be used for testing file-based indexing.

    Args:
        temp_workspace: Session-scoped temporary workspace fixture

    Returns:
        Path: Directory containing sample documents
    """
    docs_dir = temp_workspace / "docs"
    docs_dir.mkdir(exist_ok=True)

    # Create sample markdown documents
    (docs_dir / "test1.md").write_text(
        "# Test Document 1\n\n"
        "This is a test document with some content about authentication methods.\n"
        "It includes information about OAuth and JWT tokens."
    )

    (docs_dir / "test2.md").write_text(
        "# Test Document 2\n\n"
        "More content about API testing and integration patterns.\n"
        "This document covers REST APIs and GraphQL endpoints."
    )

    (docs_dir / "test3.txt").write_text(
        "Plain text document for testing different file formats.\n"
        "Contains information about deployment strategies."
    )

    return docs_dir


@pytest.fixture
def temp_collections_path(temp_workspace):
    """Provide isolated collections storage path.

    Creates a temporary directory for storing collection data
    during tests. This ensures tests don't interfere with real data.

    Args:
        temp_workspace: Session-scoped temporary workspace fixture

    Returns:
        str: Path to temporary collections directory
    """
    collections_path = temp_workspace / "collections"
    collections_path.mkdir(parents=True, exist_ok=True)
    return str(collections_path)


@pytest.fixture
def temp_caches_path(temp_workspace):
    """Provide isolated caches storage path.

    Creates a temporary directory for storing cache data
    during tests.

    Args:
        temp_workspace: Session-scoped temporary workspace fixture

    Returns:
        str: Path to temporary caches directory
    """
    caches_path = temp_workspace / "caches"
    caches_path.mkdir(parents=True, exist_ok=True)
    return str(caches_path)
