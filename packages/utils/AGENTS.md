# utils — Shared utilities

> Scope: this package. Workflow, rules, and verify gate live in the root
> [`AGENTS.md`](../../AGENTS.md). Architecture overview: [`.spec/tech.md`](../../.spec/tech.md).

## What this is

A thin, dependency-free foundation imported by every layer: logging, retry,
batching, timing, and test-safe attribute access. No business logic lives here.

## Layer & dependencies

Lowest layer alongside config/parsing/protocols. MUST NOT import anything above
it (`core`, connectors, CLI, MCP). Has no separate tech-branch spec by design.

## Where to find what

```
src/utils/
  logger.py          single-sink Loguru architecture for CLI + library code
  retry.py           execute_with_retry(func, id, retries=3, delay=1) — simple backoff
  batch.py           read_items_in_batches(...) — stream sources in batches
  performance.py     execute_and_measure_duration(func) — timing wrapper
  safe_getattr.py    safe_str_attr / safe_*_attr — MagicMock-safe access in tests
```

## Architecture notes

- **Single logging sink** (`logger.py`) — configured once by the app entry point,
  not at import time. Library code logs through it; it never sets up its own.
- Helpers are small, pure, and side-effect-free at import.
- Because everything depends on `utils`, keep its own dependencies minimal and
  never introduce an upward import (that would create a cycle).
