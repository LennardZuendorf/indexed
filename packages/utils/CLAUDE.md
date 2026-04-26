# Shared Utilities Guide

This package provides lightweight, dependency-minimal utilities for use across all packages.

## Package Overview

**Location:** `packages/utils/`

**Purpose:**
- Provide cross-cutting utilities for logging, retry logic, batching, and performance measurement
- Keep minimal dependencies (only Loguru) to avoid circular dependencies
- Enable reusable patterns without forcing heavy frameworks
- Support all packages without creating dependency conflicts

**Design Principle:** Utilities are lightweight building blocks, not full frameworks.

**Key Files:**
```
src/utils/
├── logger.py              # Loguru setup and configuration
├── retry.py               # Exponential backoff retry logic
├── batch.py               # Pagination and batch processing
├── performance.py         # Execution timing and measurement
└── safe_getattr.py        # Safe attribute access with fallbacks
```

## Logging (`logger.py`)

Single-sink Loguru architecture. All log records — both Loguru and stdlib `logging` — flow through one Loguru configuration. Bootstrapped once at CLI entry.

### Bootstrap

```python
from utils import bootstrap_logging

# CLI entry point — call once, idempotent
bootstrap_logging(
    level="WARNING",     # Effective console level (resolved by caller from flags)
    debug=False,         # --debug: lowers third-party libs to DEBUG, enables file sink
    quiet=False,         # --quiet: silences status sink (no spinner text)
    rich_console=None,   # Optional shared rich.console.Console instance
    theme_styles=None,   # Optional {level_name: style_str} for Rich rendering
    log_dir=None,        # Optional dir for the rotating --debug file sink
)
```

The CLI in `apps/indexed` builds `theme_styles` from `apps/indexed/src/indexed/utils/components/theme.py` accessors. Library / non-CLI consumers omit `rich_console` and `theme_styles` and get plain stderr output.

### Strict verbosity matrix

| Flag        | Console | Console format          | Status sink | File sink |
|-------------|---------|-------------------------|-------------|-----------|
| _(default)_ | WARNING | level + msg             | on          | off       |
| `--verbose` | INFO    | level + name:line + msg | on          | off       |
| `--debug`   | DEBUG   | full + file sink path   | on          | DEBUG, daily-rotating |
| `--quiet`   | ERROR   | level + msg             | **off**     | off       |

### Status messages (spinner)

```python
from utils import emit_status, subscribe_status, unsubscribe_status

# Application code: emit progress narration
emit_status("Embedding chunk 42 of 120")

# UI code (spinner / progress bar): subscribe
token = subscribe_status(lambda msg: spinner.update(msg))
try:
    do_work_that_emits_status()
finally:
    unsubscribe_status(token)
```

`emit_status` is `logger.bind(status=True).info(...)` under the hood. The status sink filters on the `status` extra and fans out to subscribers. This is independent of console verbosity — `--quiet` is the only flag that disables it.

### Third-party logger policy

`THIRD_PARTY_LOGGERS` is a declarative table of noisy libs and their default level floors:

```python
from utils import THIRD_PARTY_LOGGERS

# Current defaults — extend when a new noisy dep surfaces:
{
    "docling": "CRITICAL",         # wrapped by indexed-parsing; their errors are noise
    "docling_core": "CRITICAL",
    "transformers": "ERROR",       # informative — surface ERROR+
    "sentence_transformers": "WARNING",
    "urllib3": "WARNING",
    "huggingface_hub": "WARNING",
    "filelock": "WARNING",
}
```

In `--debug`, every entry is lowered to `DEBUG` so the user sees what these libs are doing. Otherwise the level here is the floor.

### Defense in depth

`bootstrap_logging` does the following at startup:

1. Installs an `InterceptHandler` on the root stdlib logger — every `logging` record routes through Loguru.
2. Sets `logging.lastResort = None` — kills Python's silent stderr fallback. (Without this, records that find no handler in the chain leak to stderr at WARNING level.)
3. For each entry in `THIRD_PARTY_LOGGERS`: sets the level, attaches a `NullHandler` (so `callHandlers` finds a handler and never falls back to `lastResort`), leaves `propagate=True` so the record still reaches the InterceptHandler.

Result: no third-party `logging` record can produce raw stderr output, ever, regardless of bootstrap order. The console sink is the only path to user output.

### Using Loguru in application code

```python
from loguru import logger

logger.debug("Detailed diagnostic")
logger.info("Operation complete")
logger.warning("Something unusual")
logger.error("Recoverable failure")

try:
    risky_operation()
except Exception:
    logger.exception("Operation failed")  # Includes traceback
```

### Verbosity introspection

```python
from utils import is_verbose_mode, get_current_log_level

if is_verbose_mode():  # True at INFO or DEBUG
    logger.debug("verbose-only diagnostic")

current = get_current_log_level()  # "WARNING" / "INFO" / "DEBUG" / "ERROR"
```

### Migration from `setup_root_logger`

`setup_root_logger(level_str=...)` is kept as a deprecated shim that delegates to `bootstrap_logging`. New code should call `bootstrap_logging` directly with the full Strict matrix.

## Retry Logic (`retry.py`)

Exponential backoff retry mechanism for network calls and transient failures.

### Basic Retry

```python
from utils import execute_with_retry

# Simple retry with defaults
result = execute_with_retry(
    fn=lambda: api.fetch_data(),
    max_attempts=3,
)
```

### Custom Backoff Strategy

```python
from utils import execute_with_retry

# Custom retry configuration
result = execute_with_retry(
    fn=lambda: api.fetch_data(),
    max_attempts=5,
    base_delay=1.0,              # Start with 1 second delay
    backoff_multiplier=2.0,      # Double delay on each retry (1s, 2s, 4s, 8s, 16s)
    max_delay=60.0,              # Cap delay at 60 seconds
    jitter=True,                 # Add randomness to prevent thundering herd
)
```

### Specific Exception Handling

```python
from utils import execute_with_retry
import requests

# Retry only on specific exceptions
result = execute_with_retry(
    fn=lambda: requests.get("https://api.example.com/data"),
    max_attempts=3,
    retryable_exceptions=(
        requests.ConnectionError,  # Network errors
        requests.Timeout,          # Timeout errors
    ),
)
```

### With Logging

```python
from utils import execute_with_retry
from loguru import logger

result = execute_with_retry(
    fn=lambda: api.fetch_data(),
    max_attempts=3,
    on_retry=lambda attempt, delay, error: logger.warning(
        f"Retry {attempt}/3 after {delay}s due to: {error}"
    ),
)
```

### Common Use Cases

**HTTP Request with Rate Limiting:**
```python
# Handles HTTP 429 (Too Many Requests) with backoff
result = execute_with_retry(
    fn=lambda: requests.get("https://api.example.com/items"),
    max_attempts=5,
    base_delay=2.0,
    backoff_multiplier=2.0,  # 2s, 4s, 8s, 16s, 32s
)
```

**Database Query with Transient Failures:**
```python
# Handles temporary database connection issues
result = execute_with_retry(
    fn=lambda: db.query("SELECT * FROM items"),
    max_attempts=3,
    retryable_exceptions=(ConnectionError, TimeoutError),
)
```

**File I/O with Lock Contention:**
```python
# Handles file lock contention on shared filesystems
result = execute_with_retry(
    fn=lambda: json.load(open("shared_config.json")),
    max_attempts=3,
    base_delay=0.1,
    backoff_multiplier=2.0,
)
```

### Backoff Calculation

The retry mechanism calculates delay between attempts:

```
Delay = min(base_delay * (backoff_multiplier ^ attempt), max_delay)
With jitter: Delay = Delay * random(0.5, 1.5)

Example with base_delay=1.0, multiplier=2.0, max_delay=60.0:
Attempt 1: 1s
Attempt 2: 2s
Attempt 3: 4s
Attempt 4: 8s
Attempt 5: 16s
Attempt 6: 32s
Attempt 7+: 60s (capped)
```

## Batch Processing (`batch.py`)

Iterator for efficiently processing paginated API responses.

### Basic Batching

```python
from utils import read_items_in_batches

# Fetch items in batches of 100
for batch in read_items_in_batches(
    fetch_fn=lambda offset: api.list_items(offset=offset, limit=100),
    batch_size=100,
):
    for item in batch:
        print(f"Processing: {item}")
```

### With Error Handling

```python
from utils import read_items_in_batches

# Batches with retry on transient failures
for batch in read_items_in_batches(
    fetch_fn=lambda offset: api.list_items(offset=offset),
    batch_size=100,
    max_retries=3,
    raise_on_error=False,  # Skip failed batches instead of crashing
):
    for item in batch:
        try:
            process_item(item)
        except Exception as e:
            logger.error(f"Failed to process item: {e}")
            continue
```

### Cursor-Based Pagination

```python
from utils import read_items_in_batches

# Cursor-based pagination (instead of offset)
for batch in read_items_in_batches(
    fetch_fn=lambda cursor: api.list_items(cursor=cursor),
    batch_size=50,
    use_cursor=True,  # Use cursor parameter instead of offset
):
    for item in batch:
        process_item(item)
```

### Common Use Cases

**Jira Issue Pagination:**
```python
def fetch_issues(start_at):
    return jira_client.jql("project = DOCS", start_at=start_at, max_results=100)

for batch in read_items_in_batches(
    fetch_fn=fetch_issues,
    batch_size=100,
):
    for issue in batch:
        process_issue(issue)
```

**Confluence Page Pagination:**
```python
def fetch_pages(cursor):
    return confluence_client.get_pages(cursor=cursor, limit=50)

for batch in read_items_in_batches(
    fetch_fn=fetch_pages,
    batch_size=50,
    use_cursor=True,
):
    for page in batch:
        process_page(page)
```

**Database Query Batching:**
```python
def fetch_rows(offset):
    return db.query("SELECT * FROM items LIMIT 1000 OFFSET ?", offset)

for batch in read_items_in_batches(
    fetch_fn=fetch_rows,
    batch_size=1000,
):
    for row in batch:
        process_row(row)
```

## Performance Measurement (`performance.py`)

Utilities for measuring and logging execution time.

### Simple Timing

```python
from utils import log_execution_duration
from loguru import logger

@log_execution_duration(logger=logger, level="INFO")
def expensive_operation():
    """Function decorated with timing."""
    time.sleep(2)
    return "result"

# Logs: "expensive_operation completed in 2000ms"
result = expensive_operation()
```

### Manual Timing

```python
from utils import execute_and_measure_duration

def fetch_documents():
    # Simulate API call
    return ["doc1", "doc2", "doc3"]

docs, duration_ms = execute_and_measure_duration(fetch_documents)
print(f"Fetched {len(docs)} documents in {duration_ms}ms")
```

### Timing with Context

```python
from utils import execute_and_measure_duration
from loguru import logger

operation_name = "index_creation"
result, duration_ms = execute_and_measure_duration(
    fn=lambda: create_collection("my-docs"),
)

logger.info(
    f"Operation completed",
    extra={
        "operation": operation_name,
        "duration_ms": duration_ms,
        "status": "success",
    }
)
```

### Batch Operation Timing

```python
from utils import log_execution_duration
from loguru import logger

@log_execution_duration(logger=logger, prefix="Batch")
def process_batch(items):
    """Process items and measure total time."""
    for item in items:
        process_single_item(item)
    return len(items)

# Logs: "Batch process_batch completed in 5000ms"
count = process_batch(items)
```

### Performance Profiling

```python
from utils import execute_and_measure_duration
from loguru import logger
import time

# Measure multiple operations
operations = {
    "embedding": lambda: embed_texts(["text1", "text2"]),
    "indexing": lambda: create_faiss_index(embeddings),
    "persistence": lambda: save_to_disk(index),
}

total_ms = 0
for op_name, op_fn in operations.items():
    result, duration_ms = execute_and_measure_duration(op_fn)
    total_ms += duration_ms
    logger.info(f"{op_name}: {duration_ms}ms")

logger.info(f"Total time: {total_ms}ms")
```

## Safe Attribute Access (`safe_getattr.py`)

Safe attribute access with fallbacks and defaults.

### Basic Safe Access

```python
from utils import safe_str_attr

# Safe access with fallback
config = {"name": "my-collection"}
value = safe_str_attr(config, "description", default="No description")
# Returns: "No description" (because 'description' key doesn't exist)
```

### Nested Object Access

```python
from utils import safe_str_attr

class Document:
    def __init__(self):
        self.metadata = {"title": "Doc 1"}

doc = Document()

# Safe nested access
title = safe_str_attr(doc.metadata, "title", default="Untitled")
# Returns: "Doc 1"

# Safe access to missing nested attribute
author = safe_str_attr(doc.metadata, "author", default="Unknown")
# Returns: "Unknown"
```

### Type Conversion

```python
from utils import safe_str_attr

# Converts attribute value to string
result = safe_str_attr(obj, "count", default="0")
# If obj.count = 42, returns "42"
# If obj.count missing, returns "0"
```

## Usage Examples

### Complete Example: Indexing with Utilities

```python
from utils import (
    setup_root_logger,
    execute_with_retry,
    read_items_in_batches,
    execute_and_measure_duration,
)
from loguru import logger

# Setup logging
setup_root_logger(level="INFO", verbose=False)

# Time the entire operation
def create_index():
    logger.info("Starting index creation")

    # Fetch documents with retry
    docs = execute_with_retry(
        fn=lambda: api.list_documents(),
        max_attempts=3,
    )

    # Process in batches with timing
    total_processed = 0
    for batch in read_items_in_batches(
        fetch_fn=lambda offset: api.list_documents(offset=offset),
        batch_size=100,
    ):
        for doc in batch:
            embed_and_index(doc)
            total_processed += 1

    logger.info(f"Indexed {total_processed} documents")
    return total_processed

# Execute with timing
count, duration_ms = execute_and_measure_duration(create_index)
logger.info(f"Index creation completed in {duration_ms}ms")
```

### Complete Example: Connector with Retry & Batch

```python
from utils import execute_with_retry, read_items_in_batches
from loguru import logger

class JiraConnector:
    def __init__(self, config):
        self.config = config
        self.client = JiraClient(config)

    def read_all_documents(self):
        """Read all issues with retry and batching."""
        def fetch_page(start_at):
            return execute_with_retry(
                fn=lambda: self.client.search_issues(
                    jql=self.config.jql,
                    start_at=start_at,
                    max_results=100,
                ),
                max_attempts=3,
                backoff_multiplier=2.0,
            )

        for batch in read_items_in_batches(
            fetch_fn=fetch_page,
            batch_size=100,
        ):
            for issue in batch:
                yield self._convert_issue(issue)
```

## Best Practices

### Best Practice 1: Always Use Logging

```python
# ✅ GOOD - Use logger for diagnostics
from loguru import logger

logger.info("Starting operation")
try:
    result = operation()
    logger.info(f"Operation succeeded: {result}")
except Exception as e:
    logger.exception("Operation failed")

# ❌ BAD - Silent failures
def my_function():
    try:
        operation()
    except:
        pass  # Silently ignores errors
```

### Best Practice 2: Use Retry for Network Operations

```python
# ✅ GOOD - Retry on transient failures
from utils import execute_with_retry

data = execute_with_retry(
    fn=lambda: requests.get("https://api.example.com/data"),
    max_attempts=3,
    retryable_exceptions=(requests.ConnectionError, requests.Timeout),
)

# ❌ BAD - Single attempt for unreliable operations
data = requests.get("https://api.example.com/data")  # Fails on network issues
```

### Best Practice 3: Batch API Calls

```python
# ✅ GOOD - Process in batches
from utils import read_items_in_batches

for batch in read_items_in_batches(
    fetch_fn=lambda offset: api.get_items(offset=offset),
    batch_size=100,
):
    process_batch(batch)

# ❌ BAD - Fetch one at a time
for i in range(total_count):
    item = api.get_item(i)  # N API calls instead of N/100
    process_item(item)
```

### Best Practice 4: Measure Performance

```python
# ✅ GOOD - Measure and log timing
from utils import execute_and_measure_duration
from loguru import logger

result, duration_ms = execute_and_measure_duration(expensive_operation)
logger.info(f"Operation completed in {duration_ms}ms")

# ❌ BAD - No timing visibility
result = expensive_operation()  # No insight into performance
```

## Integration with Other Packages

### Used By: indexed (CLI)

Logging setup for CLI application:

```python
# apps/indexed/app.py
from utils import setup_root_logger

@app.callback()
def init_app(verbose: bool = False):
    setup_root_logger(verbose=verbose)
```

### Used By: indexed-core

Retry logic in document readers:

```python
# packages/indexed-core/engine/connectors/jira_reader.py
from utils import execute_with_retry

def fetch_issues(self):
    return execute_with_retry(
        fn=lambda: self.client.search_issues(),
        max_attempts=3,
    )
```

### Used By: indexed-connectors

Batch processing for pagination:

```python
# packages/indexed-connectors/confluence_reader.py
from utils import read_items_in_batches

for batch in read_items_in_batches(
    fetch_fn=self.fetch_pages,
    batch_size=50,
):
    for page in batch:
        yield page
```

## Testing Utilities

### Unit Testing Retry

```python
from unittest.mock import MagicMock
from utils import execute_with_retry

def test_retry_on_failure():
    """Test that retry handles transient failures."""
    mock_fn = MagicMock(side_effect=[
        ConnectionError("Network error"),
        ConnectionError("Network error"),
        "success",  # Third attempt succeeds
    ])

    result = execute_with_retry(
        fn=mock_fn,
        max_attempts=3,
        retryable_exceptions=(ConnectionError,),
    )

    assert result == "success"
    assert mock_fn.call_count == 3
```

### Unit Testing Batching

```python
from utils import read_items_in_batches

def test_batch_pagination():
    """Test that batching fetches all items."""
    fetch_calls = []

    def mock_fetch(offset):
        fetch_calls.append(offset)
        if offset < 200:
            return list(range(offset, offset + 100))
        return []

    items = []
    for batch in read_items_in_batches(
        fetch_fn=mock_fetch,
        batch_size=100,
    ):
        items.extend(batch)

    assert len(items) == 200
    assert fetch_calls == [0, 100, 200]
```

## Related Documentation

- **[Root CURSOR.md](../../CURSOR.md)** - Project overview
- **[CLI CURSOR.md](../../apps/indexed/CURSOR.md)** - CLI implementation
- **[Core Engine CURSOR.md](../../packages/indexed-core/CURSOR.md)** - Engine architecture
- **[Connectors CURSOR.md](../../packages/indexed-connectors/CURSOR.md)** - Connector system
- **[Configuration CURSOR.md](../../packages/indexed-config/CURSOR.md)** - Config system

---

**Last Updated:** January 24, 2026
