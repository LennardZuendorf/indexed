---
type: tech
updated: 2026-11-22
applies: "src/indexed/**"
---

# Error Handling

All exceptions inherit from `IndexedError`:

```text
IndexedError
├── ConfigurationError
│   └── ConfigValidationError
├── StorageError
│   └── StorageConflictError
├── CLIError
└── MCPError
```

- All package exceptions MUST inherit from `IndexedError`
- NEVER use bare `except Exception: pass` — always log or re-raise
- CLI layer catches `IndexedError` subtypes → user-friendly message + exit code
- MCP layer catches `IndexedError` subtypes → structured error dict
- Unexpected exceptions propagate with full traceback
- Missing/corrupt collections **fail loud**: they raise `IndexedError` and are
  **omitted from status** (never zero-filled into a fake-healthy placeholder); the
  CLI exits **non-zero** (via `exit_code_for`) with a clean message — never a raw
  traceback, never a success exit on failure
- The MCP boundary **envelopes every exception** (not only `IndexedError`) and
  surfaces per-collection failures in the result envelope — never a silent
  "0 matches" — and must not serve **stale** cached results after a re-index
