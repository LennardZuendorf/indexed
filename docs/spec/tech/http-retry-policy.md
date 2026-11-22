---
type: tech
updated: 2026-11-22
applies: ["src/indexed/utils/**", "src/indexed/connectors/**"]
---

# HTTP Retry Policy

Transient HTTP statuses are centralized in `utils/retry.py`:

```python
TRANSIENT_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})
```

`execute_with_retry` re-raises immediately on non-transient HTTP errors (e.g. 404).
Connector readers use this helper — do not duplicate status-code tuples.
