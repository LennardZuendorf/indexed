---
type: tech
updated: 2026-11-22
applies: ["src/indexed/core/**", src/indexed/cli/composition.py]
---

# Core Facade: import rule and wiring site

No code above the facade may import `core.v1.*` or `core.v2.*` directly (to mock a
facade-resolved symbol in tests, patch the facade attribute) — this is now CI-enforced by
`scripts/check_imports.py`'s `cli/mcp/lsp ↛ core.v1, core.v2` rule, not merely a documented
convention. `src/indexed/core/facade_config.py` is part of this facade surface: it holds
`CoreEngineConfig` ([core] engine, the default-engine selector for NEW collections) plus 7
lazily re-exported v1 config-model/utility symbols, so files above the facade never import
`core.v1.*`/`core.v2.*` for those either. `config/commands/` is a separate, pre-existing
exemption in `check_imports.py` (`_EXEMPT_DIRS`) — same composition-adjacent rationale as
`config/cli.py` and `cli/composition.py` — so a file there (e.g. `config/commands/
_helpers.py`) importing `core.v1.config_models` directly is expected, not a facade gap.
(v2 ships over a **new version-marked on-disk format**, not v1's — the earlier "same
format" swap premise was superseded by core-v2 ADR-1; v1's format stays frozen.)

**`src/indexed/cli/composition.py` is the single wiring site** — it folds in the
removed `bootstrap.py` + `runtime.py` + `connector_wiring.py`. It:

- builds the connector registry and hands the facade **two REQUIRED callables** —
  `connector_factory` (create-time) and `manifest_factory` (update-time). No
  `Callable | None` + `missing_wiring_error` on the happy path; a missing wiring is a
  `TypeError`/ty error at the call site, not a runtime guard.
- owns `resolve_collections_context(mode_override)` — the **single** storage-path resolver
  for CLI and MCP — and calls `register_app_config` itself, so registered config specs
  survive the singleton reset a non-None `mode_override` forces. Do not revive heuristics
  like "prefer local if non-empty collections dir", and do not add a per-caller defensive
  re-register for callers that go through it.

Each connector's `from_manifest` owns its manifest keys, so core carries no per-type
branches; `composition.manifest_factory` is a one-line registry dispatch.
