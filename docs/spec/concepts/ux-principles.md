---
type: concept
updated: 2026-11-22
---

# UX Principles

## Privacy First

- Never send data externally
- All embedding generation local
- Credentials stored in .env (not config)
- No telemetry or analytics

## Fast & Minimal

- CLI startup <1s despite ML dependencies
- Search latency <1s for typical collections
- Minimal configuration required
- Sensible defaults

## Developer Experience

- Beautiful terminal output (Rich)
- Guided prompts for setup
- Clear error messages
- Excellent documentation

## Composability

- Unix philosophy (do one thing well)
- JSON output for scripting
- Standard protocols (MCP)
- Extensible connector system
