---
type: tech
updated: 2026-11-22
applies: "src/indexed/cli/**"
---

# CLI Startup Time

**Target:** <1s. **Actual:** ~500ms.

Techniques: lazy imports of heavy ML libs, deferred service init, minimal
module-level imports (`TYPE_CHECKING`), `__getattr__` module-level lazy loading.
The watcher imports its polling service only when the command runs.

```python
def __getattr__(name: str):
    """Lazy load heavy dependencies for tests and performance."""
    if name == "svc_search":
        from indexed.core.v1.engine import search
        return search
    if name == "SourceConfig":
        from indexed.core.v1.engine import SourceConfig
        return SourceConfig
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
```

The optional Git line attribution appears as `git` on the matched hit. Optional freshness verdicts appear in the search envelope.
