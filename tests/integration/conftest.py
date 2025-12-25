"""Integration test fixtures.

This module provides fixtures for integration testing:
- Function-scoped fixtures for isolated test state (clean config, mock servers)
- Test isolation fixtures (config, search service)

Note: Shared fixtures (temp_workspace, sample_documents, temp_collections_path,
temp_caches_path) are provided by tests/fixtures/conftest.py
"""

import pytest
from pytest_httpserver import HTTPServer


@pytest.fixture
def clean_config(temp_workspace):
    """Provide fresh ConfigService instance per test.

    This fixture ensures each test gets an isolated ConfigService instance
    with the singleton pattern properly reset before and after the test.

    Args:
        temp_workspace: Session-scoped temporary workspace fixture from fixtures/
    """
    from indexed_config import ConfigService

    # Reset singleton before test
    ConfigService.reset()

    # Create fresh instance
    config = ConfigService()

    yield config

    # Cleanup singleton after test
    ConfigService.reset()


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
    # Some clients use /rest/api/latest/search, others use /rest/api/2/search
    jira_response = {
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

    # Accept both endpoints
    server.expect_request("/rest/api/latest/search", method="GET").respond_with_json(
        jira_response
    )
    server.expect_request("/rest/api/2/search", method="GET").respond_with_json(
        jira_response
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
    from indexed_config import ConfigService

    # Reset before test
    ConfigService.reset()

    yield

    # Reset after test
    ConfigService.reset()


@pytest.fixture(autouse=True)
def isolate_search_service():
    """Ensure each test gets clean SearchService cache state.

    This autouse fixture runs for every test and clears the SearchService
    cache to prevent resource leaks (like tqdm threads from sentence-transformers)
    that cause segfaults during test teardown.
    """
    import core.v1.engine.services.search_service as search_service_module

    # Clear cache before test (only if service exists)
    if search_service_module._default_service is not None:
        search_service_module._default_service._searcher_cache.clear()

    yield

    # Clear cache after test to release references to FAISS indexers and models
    # This prevents tqdm threads from sentence-transformers from causing segfaults
    if search_service_module._default_service is not None:
        search_service_module._default_service._searcher_cache.clear()

    # Reset the singleton to ensure clean state
    search_service_module._default_service = None

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
