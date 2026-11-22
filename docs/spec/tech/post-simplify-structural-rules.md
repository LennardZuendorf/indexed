---
type: tech
updated: 2026-11-22
applies: "src/indexed/**"
---

# Post-Simplify Structural Rules

Promoted from the retired Feature 14 (Simplify) tech spec as of simplify/6 —
normative root rules from here on,
independent of Feature 14's own DONE/PLANNED status ([Feature Sequence](../concepts/feature-sequence.md)). The single-package collapse, `check_imports.py` gate,
scoped coverage config, and one `AGENTS.md` are already live in the tree; the
remaining Simplify units (residual dead-code/test cleanup) converge the rest
of the codebase toward these same rules rather than establishing new ones.

- **One package, four module edges** (`cli`/`mcp` → `core`|`connectors`|`config`;
  `core ↛ connectors`; `connectors ↛ core`; `config`/`utils`/`parsing`/`protocols`
  never import up), enforced by `scripts/check_imports.py`. One `pyproject.toml`,
  one wheel (`indexed-sh`), no `una`, no per-package builds, no `sync_version.py`.
- **No phantom generality.** No abstraction (registry/factory/multi-impl loop)
  over a single implementation. One indexer, one progress protocol, no dead DTOs
  or re-export shims.
- **Behavior-only tests.** Keep behavior/system/benchmark tests + the
  characterization harness; no mechanism tests (registry membership, shims,
  protocol stubs, Rich markup, migration). **Coverage gate is scoped to
  `core`/`connectors`/`config`/`parsing`/`protocols`/`utils`; UI chrome
  (`cli`/`mcp`) is exempt** (see `[tool.coverage.run]` in `pyproject.toml`).
- **One root `AGENTS.md`** (≤100 lines); agent skills install from
  `skills-lock.json`, never vendored.
