---
type: tech
updated: 2026-11-22
applies: "tests/**"
---

# Testing Strategy

**Target:** >85% coverage on `core`/`connectors`/`config`/`parsing`/`protocols`/
`utils`. `cli`/`mcp` (UI chrome) are exempt from the gate — see [Post-Simplify
Structural Rules](post-simplify-structural-rules.md) and `[tool.coverage.run]` in `pyproject.toml`.

```text
tests/
├── unit/              # tests/unit/{indexed,utils,scripts}/ — indexed/ mirrors src/indexed/'s subpackages
├── system/            # integration tests
├── characterization/  # behavior-net harness (regression-guards fixed bugs)
└── benchmarks/        # performance tests
```

```bash
uv run pytest -q                              # all
uv run pytest tests/unit/indexed/core/ -q     # one subpackage
uv run pytest -q --cov=src/indexed --cov-report=html
```
