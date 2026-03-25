# indexed-utils

Shared utility functions for the indexed project including logging, retry logic, batching, and performance monitoring.

## Overview

`indexed-utils` provides lightweight, dependency-minimal utilities used across all indexed packages. These utilities handle cross-cutting concerns like logging, error handling, API pagination, and performance monitoring.

**Design Principle:** This package has minimal dependencies (only Loguru) to avoid circular dependencies and keep the utility layer lightweight. For Rich-enhanced CLI output, use `indexed.utils.logging` which extends this base configuration.

## Features

| Feature | Description |
|---------|-------------|
| **Logging** | Base Loguru configuration with JSON support |
| **Retry Logic** | Exponential backoff for transient failures |
| **Batching** | Automatic pagination for API calls |
| **Performance** | Execution timing and profiling utilities |

## Installation

This package is part of the indexed monorepo workspace. Requires **Python 3.11+**.

```bash
# Install with workspace
uv sync

# Or standalone (for development)
cd packages/utils
uv pip install -e .
```

## Usage

### Logging

```python
from utils import setup_root_logger, is_verbose_mode, get_current_log_level

# Setup basic logging (WARNING level by default, quiet mode)
setup_root_logger()

# Setup with custom level
setup_root_logger(level_str="DEBUG")

# Setup with verbose mode (INFO level)
setup_root_logger(level_str="INFO")

# Setup JSON logging for production
setup_root_logger(json_mode=True)

# Check current mode
if is_verbose_mode():
    print("Verbose logging is enabled")

level = get_current_log_level()
print(f"Current log level: {level}")
```

### Retry Logic

```python
from utils import execute_with_retry

def fetch_data():
    """Operation that might fail transiently."""
    response = requests.get("https://api.example.com/data")
    response.raise_for_status()
    return response.json()

# Retry up to 3 times with exponential backoff
result = execute_with_retry(
    fetch_data,
    func_identifier="Fetching API data",
    retries=3,
    delay=1,  # Initial delay in seconds
)

# The retry logic handles:
# - HTTP 429 (Rate Limit) with Retry-After header
# - Network timeouts
# - Connection errors
# - Configurable exponential backoff
```

### Batching / Pagination

```python
from utils import read_items_in_batches

def read_batch(start_at: int, batch_size: int, cursor=None):
    """Make API call for a batch of items."""
    response = api.get_items(start=start_at, limit=batch_size)
    return response

# Read all items with automatic pagination
items = read_items_in_batches(
    read_batch_func=read_batch,
    fetch_items_from_result_func=lambda r: r["items"],
    fetch_total_from_result_func=lambda r: r["total"],
    batch_size=100,
    max_skipped_items_in_row=5,  # Fail after 5 consecutive errors
    itemsName="documents",       # For logging
)

for item in items:
    process(item)

# The batch reader handles:
# - Automatic pagination
# - Error recovery (skip failed items, continue with next batch)
# - Progress logging
# - Cursor-based pagination support
```

### Performance Monitoring

```python
from utils import log_execution_duration, execute_and_measure_duration

# Log execution duration automatically
result = log_execution_duration(
    lambda: expensive_operation(),
    identifier="Data processing",
    enabled=True,  # Set to False to disable timing
)

# Measure duration without logging (for custom handling)
result, error, duration = execute_and_measure_duration(
    lambda: expensive_operation()
)

if error:
    print(f"Operation failed after {duration:.2f}s: {error}")
else:
    print(f"Operation succeeded in {duration:.2f}s")
```

### Safe Attribute Access

```python
from utils import safe_str_attr

# Safely get string attribute with fallback
obj = SomeObject()
value = safe_str_attr(obj, "name", default="Unknown")

# Handles:
# - None objects
# - Missing attributes
# - Non-string values (converts to string)
```

## Architecture

This package is designed as the **base layer** for logging and utilities:

```
┌─────────────────────────────────────────────────────┐
│  CLI Layer (indexed/utils/logging.py)               │
│  - Rich formatting (RichHandler)                    │
│  - Status capture for spinners                      │
│  - CLI-specific features                            │
└─────────────────────────┬───────────────────────────┘
                          │ extends
┌─────────────────────────▼───────────────────────────┐
│  Base Layer (packages/utils - this package)         │
│  - Pure Loguru (no Rich dependency)                 │
│  - Simple stderr sink                               │
│  - Works for library/non-CLI usage                  │
└─────────────────────────────────────────────────────┘
```

## API Reference

### Logging Functions

| Function | Description |
|----------|-------------|
| `setup_root_logger(level_str, json_mode)` | Configure Loguru root logger |
| `is_verbose_mode()` | Check if verbose logging is enabled |
| `get_current_log_level()` | Get current log level string |

### Retry Function

| Function | Description |
|----------|-------------|
| `execute_with_retry(func, func_identifier, retries, delay)` | Execute function with exponential backoff |

### Batch Function

| Function | Description |
|----------|-------------|
| `read_items_in_batches(...)` | Read paginated API results as generator |

### Performance Functions

| Function | Description |
|----------|-------------|
| `log_execution_duration(func, identifier, enabled)` | Execute and log duration |
| `execute_and_measure_duration(func)` | Execute and return (result, error, duration) |

### Utility Functions

| Function | Description |
|----------|-------------|
| `safe_str_attr(obj, attr, default)` | Safely get string attribute |

## Project Structure

```
utils/
├── src/utils/
│   ├── __init__.py          # Package exports
│   ├── logger.py            # Loguru configuration
│   ├── retry.py             # Retry with exponential backoff
│   ├── batch.py             # Paginated reading
│   ├── performance.py       # Timing utilities
│   └── safe_getattr.py      # Safe attribute access
│
├── pyproject.toml
└── README.md
```

## Dependencies

| Package | Purpose |
|---------|---------|
| **loguru** | Advanced logging with colors and structured output |

## Development

### Running Tests

```bash
# Run utils tests
uv run pytest tests/unit/utils -v

# With coverage
uv run pytest tests/unit/utils --cov=utils
```

### Code Quality

```bash
# Format
uv run ruff format packages/utils/

# Lint
uv run ruff check packages/utils/

# Type check
uv run mypy packages/utils/src/
```

## Best Practices

1. **Always use `execute_with_retry` for external API calls** to handle transient failures gracefully.

2. **Use `read_items_in_batches` for paginated APIs** to avoid memory issues with large datasets.

3. **Set `enabled=False` on performance logging in production** unless actively profiling.

4. **Use `safe_str_attr` when accessing attributes from external data** to avoid AttributeError exceptions.

5. **Configure logging at application entry point** (CLI main, test setup) not in library code.

## License

See LICENSE file in the project root.
