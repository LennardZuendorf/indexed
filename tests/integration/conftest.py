"""Integration test fixtures.

This module provides fixtures for integration testing:
- Session-scoped fixtures for expensive operations (temp workspace, embedding models)
- Function-scoped fixtures for isolated test state (clean config, mock servers)
- Test data fixtures (sample documents, collections paths)
"""

import os

# CRITICAL: Disable tqdm BEFORE any imports that might use it
# sentence-transformers uses tqdm internally when loading models, and its monitor
# threads cause segfaults when not properly cleaned up during test teardown.
# This must be set before sentence-transformers is imported anywhere.
if "TQDM_DISABLE" not in os.environ:
    os.environ["TQDM_DISABLE"] = "1"

import pytest
import tempfile
from pathlib import Path
from pytest_httpserver import HTTPServer


def pytest_configure(config):
    """Pytest hook to ensure TQDM_DISABLE is set before any test imports."""
    # Force set TQDM_DISABLE before any tests run
    os.environ["TQDM_DISABLE"] = "1"


# ============================================================================
# Session-Scoped Fixtures (shared across test session)
# ============================================================================


@pytest.fixture(scope="session")
def temp_workspace():
    """Create temporary workspace directory for entire test session.

    This directory is reused across all tests in the session for efficiency.
    Each test should create its own subdirectories to avoid conflicts.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ============================================================================
# Function-Scoped Fixtures (fresh for each test)
# ============================================================================


@pytest.fixture
def clean_config(temp_workspace):
    """Provide fresh ConfigService instance per test.

    This fixture ensures each test gets an isolated ConfigService instance
    with the singleton pattern properly reset before and after the test.
    """
    from core.v1.engine.services.config_service import ConfigService

    # Reset singleton before test
    ConfigService._instance = None

    # Create fresh instance
    config = ConfigService()

    yield config

    # Cleanup singleton after test
    ConfigService._instance = None


@pytest.fixture
def sample_documents(temp_workspace):
    """Create sample document structure for testing.

    Creates a temporary directory with sample markdown documents
    that can be used for testing file-based indexing.

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

    Returns:
        str: Path to temporary caches directory
    """
    caches_path = temp_workspace / "caches"
    caches_path.mkdir(parents=True, exist_ok=True)
    return str(caches_path)


# ============================================================================
# HTTP Mock Server Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def mock_confluence_server():
    """Mock Confluence API server.

    Provides a fake HTTP server that simulates Confluence REST API endpoints.
    Useful for testing Confluence connector without requiring actual API access.

    The server responds to:
    - /rest/api/content/search: Returns sample page data

    Yields:
        HTTPServer: Running HTTP server instance
    """
    server = HTTPServer()
    server.start()

    # Define API endpoints matching Confluence REST API
    server.expect_request("/rest/api/content/search", method="GET").respond_with_json(
        {
            "results": [
                {
                    "id": "123",
                    "title": "Test Page",
                    "type": "page",
                    "ancestors": [],  # Empty for top-level page
                    "body": {
                        "storage": {"value": "<p>Test content about authentication</p>"}
                    },
                    "space": {"key": "TEST"},
                    "version": {"when": "2025-01-01T00:00:00.000Z"},
                    "children": {"comment": {"results": [], "size": 0}},
                    "_links": {
                        "webui": "/display/TEST/Test+Page",
                        "self": f"http://localhost:{server.port}/rest/api/content/123",
                    },
                },
                {
                    "id": "124",
                    "title": "API Documentation",
                    "type": "page",
                    "ancestors": [],  # Empty for top-level page
                    "body": {
                        "storage": {"value": "<p>Documentation for REST APIs</p>"}
                    },
                    "space": {"key": "TEST"},
                    "version": {"when": "2025-01-02T00:00:00.000Z"},
                    "children": {"comment": {"results": [], "size": 0}},
                    "_links": {
                        "webui": "/display/TEST/API+Documentation",
                        "self": f"http://localhost:{server.port}/rest/api/content/124",
                    },
                },
            ],
            "size": 2,
            "limit": 25,
            "start": 0,
            "totalSize": 2,
        }
    )

    yield server

    server.stop()


@pytest.fixture(scope="function")
def mock_jira_server():
    """Mock Jira API server.

    Provides a fake HTTP server that simulates Jira REST API endpoints.
    Useful for testing Jira connector without requiring actual API access.

    The server responds to:
    - /rest/api/latest/search: Returns sample issue data (for JiraConnector Server/DC)

    Yields:
        HTTPServer: Running HTTP server instance
    """
    server = HTTPServer()
    server.start()

    # Define Jira REST API endpoints
    # JiraConnector (Server/DC) uses /rest/api/latest/search
    server.expect_request("/rest/api/latest/search", method="GET").respond_with_json(
        {
            "issues": [
                {
                    "id": "10001",
                    "key": "TEST-1",
                    "self": f"http://localhost:{server.port}/rest/api/latest/issue/10001",
                    "fields": {
                        "summary": "Test Issue for Authentication",
                        "description": "This issue covers authentication methods",
                        "issuetype": {"name": "Story"},
                        "status": {"name": "Open"},
                        "priority": {"name": "High"},
                        "updated": "2025-01-01T00:00:00.000+0000",
                        "comment": {"comments": []},
                    },
                },
                {
                    "id": "10002",
                    "key": "TEST-2",
                    "self": f"http://localhost:{server.port}/rest/api/latest/issue/10002",
                    "fields": {
                        "summary": "API Integration Testing",
                        "description": "Testing REST API integrations",
                        "issuetype": {"name": "Task"},
                        "status": {"name": "In Progress"},
                        "priority": {"name": "Medium"},
                        "updated": "2025-01-02T00:00:00.000+0000",
                        "comment": {"comments": []},
                    },
                },
            ],
            "total": 2,
            "maxResults": 50,
            "startAt": 0,
        }
    )

    yield server

    server.stop()


# ============================================================================
# Test Isolation Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def isolate_config():
    """Ensure each test gets clean config state.

    This autouse fixture runs for every test and ensures the ConfigService
    singleton is properly reset before and after each test, preventing
    state leakage between tests.
    """
    from core.v1.engine.services.config_service import ConfigService

    # Reset before test
    ConfigService._instance = None

    yield

    # Reset after test
    ConfigService._instance = None


@pytest.fixture(autouse=True)
def isolate_search_service():
    """Ensure each test gets clean SearchService cache state.

    This autouse fixture runs for every test and clears the SearchService
    cache to prevent resource leaks (like tqdm threads from sentence-transformers)
    that cause segfaults during test teardown.
    """
    from core.v1.engine.services.search_service import _default_service

    # Clear cache before test
    _default_service._searcher_cache.clear()

    yield

    # Clear cache after test to release references to FAISS indexers and models
    # This prevents tqdm threads from sentence-transformers from causing segfaults
    _default_service._searcher_cache.clear()

    # Force garbage collection to ensure resources are released
    import gc

    gc.collect()

    # Ensure tqdm's monitor thread is cleaned up to prevent segfaults under Python 3.13
    try:
        import tqdm

        if getattr(tqdm.tqdm, "monitor", None) is not None:
            tqdm.tqdm.monitor.exit()
    except Exception:
        # If tqdm isn't available or exit fails, proceed without hard failing
        pass
