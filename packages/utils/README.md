# indexed-utils

Shared utility functions for the indexed project including logging, retry logic, batching, and performance monitoring.

## Overview

`indexed-utils` provides lightweight, dependency-minimal utilities used across the indexed project packages. These utilities handle cross-cutting concerns like logging, error handling, and performance monitoring.

**Note:** This package intentionally has minimal dependencies (only Loguru). For Rich-enhanced CLI output, use the CLI logging module which extends this base configuration.

## Features

### Logging (Base Configuration)
- **Structured logging** with Loguru
- **Simple stderr output** with colorized levels
- **JSON logging mode** for production environments
- **Configurable log levels** (DEBUG, INFO, WARNING, ERROR)

For Rich-formatted CLI output with spinners and status capture, use `indexed.utils.logging` instead.

### Retry Logic
- **Exponential backoff** for transient failures
- **Configurable retry attempts** and delays
- **Rate limit handling** (respects 429 and Retry-After)
- **Error logging** with context

### Batching
- **Automatic pagination** handling
- **Generic batch reader** for various APIs
- **Cursor-based pagination** support
- **Skip tracking** for failed items

### Performance Monitoring
- **Execution timing** utilities
- **Duration logging** with identifiers
- **Conditional profiling** support

## Usage

### Logging

```python
from utils.logger import setup_root_logger, is_verbose_mode

# Setup basic logging (WARNING level by default)
setup_root_logger()

# Setup with custom level
setup_root_logger(level_str="DEBUG")

# Setup JSON logging for production
setup_root_logger(json_mode=True)

# Check if verbose mode is enabled
if is_verbose_mode():
    print("Verbose logging is enabled")
```

### Retry Logic

```python
from utils.retry import execute_with_retry

def fetch_data():
    # Some operation that might fail
    response = requests.get("https://api.example.com/data")
    response.raise_for_status()
    return response.json()

# Retry up to 3 times with exponential backoff
result = execute_with_retry(
    fetch_data,
    func_identifier="Fetching API data",
    retries=3,
    delay=1
)
```

### Batching

```python
from utils.batch import read_items_in_batches

def read_batch(start_at, batch_size, cursor=None):
    # Make API call for a batch
    response = api.get_items(start=start_at, limit=batch_size)
    return response

# Read all items in batches with automatic pagination
items = read_items_in_batches(
    read_batch_func=read_batch,
    fetch_items_from_result_func=lambda r: r["items"],
    fetch_total_from_result_func=lambda r: r["total"],
    batch_size=100,
    max_skipped_items_in_row=5,
    itemsName="documents"
)

for item in items:
    process(item)
```

### Performance Monitoring

```python
from utils.performance import log_execution_duration, execute_and_measure_duration

# Log execution duration
result = log_execution_duration(
    lambda: expensive_operation(),
    identifier="Data processing",
    enabled=True
)

# Measure duration without logging
result, error, duration = execute_and_measure_duration(
    lambda: expensive_operation()
)
print(f"Operation took {duration:.2f} seconds")
```

## Dependencies

- **loguru** - Advanced logging with colors and structured output

## Architecture

This package is designed as the **base layer** for logging:

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

## Development

This package is part of the indexed monorepo workspace. Use `uv` for dependency management:

```bash
# Install dependencies
uv sync --all-groups

# Run tests
uv run pytest packages/utils
```

## License

See LICENSE file in the project root.
