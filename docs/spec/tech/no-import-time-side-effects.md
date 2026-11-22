---
type: tech
updated: 2026-11-22
applies: "src/indexed/**"
---

# No Import-Time Side Effects

Module-level code must not call singleton accessors, register config specs, set up
logging, or mutate global state. All initialization happens in explicit
`setup_*()` / `register_*()` functions called by the app entry point.
