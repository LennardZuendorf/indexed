# indexed-utils

Shared utility functions for the indexed project including logging, retry logic, batching, and progress tracking.

## Overview

`indexed-utils` provides common utilities used across the indexed project packages. These utilities handle cross-cutting concerns like logging, error handling, performance monitoring, and user feedback.

## Features

### Logging
- **Structured logging** with Loguru
- **Colored console output** for better readability
- **JSON logging mode** for production environments
- **Status capture** for real-time UI updates
- **Configurable log levels** via environment variables

### Retry Logic
- **Exponential backoff** for transient failures
- **Configurable retry attempts** and delays
- **Error logging** with context
- **Used by connectors** for API resilience

### Batching
- **Automatic pagination** handling
- **Generic batch reader** for various APIs
- **Cursor-based pagination** support
- **Skip tracking** for failed items
- **Progress integration** with batch processing

### Progress Tracking
- **Progress bars** using tqdm
- **Generator wrapping** for lazy evaluation
- **Iterator support** for known-size collections
- **Customizable labels** and display

### Performance Monitoring
- **Execution timing** utilities
- **Duration logging** with identifiers
- **Conditional profiling** support

## Usage

### Logging

```python
from utils.logger import setup_root_logger

# Setup basic logging
setup_root_logger()

# Setup with custom level
setup_root_logger(level_str="DEBUG")

# Setup JSON logging for production
setup_root_logger(json_mode=True)

# Check if verbose mode is enabled
from utils.logger import is_verbose_mode
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

# Retry up to 3 times with 1 second delay
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

# Read all items in batches
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

### Progress Tracking

```python
from utils.progress_bar import wrap_generator_with_progress_bar, wrap_iterator_with_progress_bar

# Wrap a generator with progress bar
def fetch_items():
    for i in range(100):
        yield i

items = wrap_generator_with_progress_bar(
    fetch_items(),
    approx_total=100,
    progress_bar_name="Processing items"
)

# Wrap an iterator with progress bar
batches = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]
for batch in wrap_iterator_with_progress_bar(batches, "Processing batches"):
    process(batch)
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
duration_ms, result = execute_and_measure_duration(
    lambda: expensive_operation()
)
print(f"Operation took {duration_ms}ms")
```

## Environment Variables

- `INDEXED__LOGGING__LEVEL` - Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `INDEXED__LOGGING__AS_JSON` - Enable JSON logging (true/false)

## Dependencies

- **loguru** - Advanced logging with colors and structured output
- **tqdm** - Progress bars and progress tracking
- **rich** (optional) - Enhanced console formatting for logs

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

