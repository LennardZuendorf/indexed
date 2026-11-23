---
type: concept
updated: 2026-11-23
---

# Current Focus: Readiness

[Current focus](README.md) · [Readiness milestones](../readiness/README.md)

The Shared Project Workspace contract is settled for storage, selection and
migration: one global store with a stable-id registry, a committed `indexed.toml`
that CLI, LSP and MCP (from its process CWD) resolve, and `indexed storage migrate`
with dry run, resume, rollback and `--verify structural|hash`. What remains of the
milestone is per-request MCP scope ([#345](https://github.com/LennardZuendorf/indexed/issues/345))
and the checkout-difference case.

Next, the work whose gate is already met: installer lifecycles for Droid, Hermes
Agent and OpenClaw ([#351](https://github.com/LennardZuendorf/indexed/issues/351),
[#352](https://github.com/LennardZuendorf/indexed/issues/352),
[#354](https://github.com/LennardZuendorf/indexed/issues/354)) reusing the Codex and
OpenCode modules, and the held-out evaluation that starts merged search
([#204](https://github.com/LennardZuendorf/indexed/issues/204)).

In parallel: the published v0.0.11 Quick Start is the remaining unbounded Python
claim ([#336](https://github.com/LennardZuendorf/indexed/issues/336),
[#218](https://github.com/LennardZuendorf/indexed/issues/218)) — the repository, the
classifiers and the package metadata already state 3.11.5–3.14. The
[#358](https://github.com/LennardZuendorf/indexed/issues/358) macOS MCP catch-up
timeout has its import-race fix on `main` (#361, #362) and still needs a macOS run.
