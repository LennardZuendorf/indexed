# Integration Tests

This directory contains comprehensive integration tests for indexed-python, testing complex interactions between connectors, APIs, embedding services, vector storage, and full indexing/search pipelines.

## Directory Structure

```
tests/integration/
├── conftest.py                 # Integration-specific fixtures
├── connectors/                 # Connector integration tests
│   ├── test_confluence_integration.py
│   ├── test_jira_integration.py
│   └── test_filesystem_integration.py
├── pipeline/                   # Full pipeline tests
│   ├── test_indexing_pipeline.py
│   └── test_search_pipeline.py
└── services/                   # Service integration tests
    ├── test_storage_service.py
    └── test_embedding_service.py
```

## Test Categories

### Connector Tests
- **Confluence**: Tests Confluence connector with mocked API server
- **Jira**: Tests Jira connector with mocked API server
- **FileSystem**: Tests file system connector with real file operations

### Pipeline Tests
- **Indexing**: End-to-end tests of the full indexing pipeline
- **Search**: End-to-end tests of the search pipeline

### Service Tests
- **Storage**: FAISS storage persistence, search, and vector operations
- **Embedding**: Sentence-transformers model loading and batch processing

## Running Tests

### Run All Integration Tests
```bash
uv run pytest -m integration tests/integration/
```

### Run Specific Category
```bash
# API-based tests
uv run pytest -m "integration and api" tests/integration/connectors/

# Slow tests only
uv run pytest -m "integration and slow" tests/integration/

# Connector tests only
uv run pytest tests/integration/connectors/ -v
```

### Run with Parallel Execution
Use `pytest-xdist` for faster test execution:

```bash
# Auto-detect number of CPU cores
uv run pytest -n auto -m integration tests/integration/

# Specify number of workers
uv run pytest -n 4 -m integration tests/integration/
```

### Run with Test Retry (for flaky tests)
Use `pytest-rerunfailures` to automatically retry failed tests:

```bash
# Retry failed tests up to 3 times
uv run pytest --reruns 3 -m integration tests/integration/

# Retry with delay between attempts
uv run pytest --reruns 3 --reruns-delay 1 -m integration tests/integration/
```

### Combined Advanced Options
```bash
# Parallel execution with retry on failure
uv run pytest -n auto --reruns 2 -m integration tests/integration/

# Verbose output with parallel execution
uv run pytest -n 4 -v -m integration tests/integration/

# Generate coverage report
uv run pytest -m integration --cov=packages/indexed-core tests/integration/
```

## Test Markers

Integration tests use the following markers:

- `@pytest.mark.integration` - All integration tests
- `@pytest.mark.api` - Tests that interact with external APIs (mocked)
- `@pytest.mark.slow` - Tests that take > 1 second
- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.requires_api` - Tests requiring real API credentials
- `@pytest.mark.requires_network` - Tests requiring network access

### Filter by Markers
```bash
# Run only API integration tests
uv run pytest -m "integration and api" tests/integration/

# Run integration tests except slow ones
uv run pytest -m "integration and not slow" tests/integration/

# Run only slow integration tests
uv run pytest -m "integration and slow" tests/integration/
```

## Fixtures

### Session-Scoped Fixtures
Expensive operations shared across all tests in a session:

- `temp_workspace` - Temporary directory for test session
- Session-scoped fixtures cache expensive operations like model loading

### Function-Scoped Fixtures
Fresh state for each test:

- `clean_config` - Fresh ConfigService instance with isolated state
- `sample_documents` - Sample test documents in temporary directory
- `temp_collections_path` - Isolated collections storage path
- `temp_caches_path` - Isolated caches storage path
- `mock_confluence_server` - Mock HTTP server for Confluence API
- `mock_jira_server` - Mock HTTP server for Jira API

### Auto-Use Fixtures
Automatically applied to all tests:

- `isolate_config` - Ensures ConfigService singleton is reset between tests

## Best Practices

### Test Isolation
Each test should be independent and not rely on others:

```python
@pytest.mark.integration
def test_example(clean_config, temp_collections_path):
    """Test description."""
    # Test uses clean fixtures for isolation
    pass
```

### Temporary Storage
Always use temporary paths provided by fixtures:

```python
@pytest.mark.integration
def test_storage(temp_workspace):
    """Test with temporary storage."""
    storage_path = temp_workspace / "my_test_data"
    # Use temp_workspace, not hardcoded paths
```

### Marking Tests
Always mark integration tests appropriately:

```python
@pytest.mark.integration  # Required
@pytest.mark.slow          # If test takes > 1 second
@pytest.mark.api           # If test uses mock API server
def test_full_pipeline():
    pass
```

### Performance Optimization

1. **Use Parallel Execution** for independent tests:
   ```bash
   uv run pytest -n auto -m integration
   ```

2. **Skip slow tests** during rapid development:
   ```bash
   uv run pytest -m "integration and not slow"
   ```

3. **Cache expensive operations** at session scope:
   - Embedding model loading
   - Large test data generation

## Debugging

### Verbose Output
```bash
# Show test names and verbose output
uv run pytest -v -s -m integration tests/integration/

# Show detailed failure information
uv run pytest -vv --tb=long -m integration tests/integration/
```

### Run Single Test
```bash
# Run specific test by name
uv run pytest tests/integration/connectors/test_filesystem_integration.py::test_filesystem_connector_basic -v

# Run tests matching pattern
uv run pytest -k "filesystem" -v
```

### Debug with pdb
```bash
# Drop into debugger on failure
uv run pytest --pdb -m integration tests/integration/

# Drop into debugger on first failure, then stop
uv run pytest -x --pdb -m integration tests/integration/
```

## CI/CD Integration

Recommended CI/CD pipeline configuration:

```yaml
# Example GitHub Actions workflow
- name: Run Integration Tests
  run: |
    uv sync --all-groups
    uv run pytest -n auto --reruns 2 -m integration tests/integration/
```

For faster CI/CD:
- Use parallel execution (`-n auto`)
- Add retry for flaky tests (`--reruns 2`)
- Cache dependencies between runs
- Skip slow tests in PR checks, run full suite on merge

## Troubleshooting

### ConfigService Singleton Issues
If tests fail with config state issues, verify `isolate_config` fixture is working:

```python
# Manual reset if needed
from indexed_config import ConfigService
ConfigService._instance = None
```

### Port Conflicts with Mock Servers
Mock servers use random ports by default. If issues occur, check:

```python
# Mock server provides port automatically
server_url = f"http://localhost:{mock_jira_server.port}"
```

### Slow Test Execution
- Use parallel execution: `pytest -n auto`
- Profile slow tests: `pytest --durations=10`
- Consider marking very slow tests for optional execution

## Contributing

When adding new integration tests:

1. Follow existing patterns in the directory
2. Use appropriate fixtures for isolation
3. Mark tests with correct markers
4. Add docstrings explaining what is being tested
5. Ensure tests are independent and reproducible
6. Update this README if adding new categories

## Example Test Template

```python
"""Integration tests for [component].

Brief description of what this test file covers.
"""

import pytest
from your.module import YourClass


@pytest.mark.integration
@pytest.mark.slow  # If applicable
def test_component_functionality(clean_config, temp_workspace):
    """Test specific functionality with clear description.

    This test verifies that [component] correctly [behavior]
    when [conditions].
    """
    # Arrange
    component = YourClass(config=clean_config)

    # Act
    result = component.do_something()

    # Assert
    assert result is not None
    assert result.status == "expected"
```
