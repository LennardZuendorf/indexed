---
type: tech
updated: 2026-11-22
applies: [scripts/check_spec_root.py, ".github/workflows/**"]
---

# Spec-Root CI

`scripts/check_spec_root.py` (workflow `Spec Root`, job `spec-root`, no path filter) asserts
`docs/spec/` exists with the core specs, the legacy dot-directory is gone, and no tracked
file outside the hash-locked eval/benchmark captures names it. The spec skill falls back
to a legacy root when `docs/spec/` is absent, so without this gate a half-migration stays green.
