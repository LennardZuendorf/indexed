---
type: concept
updated: 2026-11-22
---

# Current Focus

**Feature 14 Simplify is DONE** (2026-07-10): the seven-package workspace is
collapsed to a single `indexed` package (one wheel `indexed-sh`); dead code + chrome
tests are removed; the CLI/config chrome is shrunk (config CLI 2061→47 over
get/set/list/validate, `create` de-cloned to one schema-driven handler, every command
file ≤300); the process apparatus is unvendored (one root `AGENTS.md` ≤100 lines,
skills install from `skills-lock.json`); and the two deferred Foundation config
cleanups (cached `get_config()/reload()`, single path/mode resolver) landed. Full
suite + system tests green; coverage ≥85% on core/connectors/config; size + import
gates enforced by `scripts/check_sizes.py` + `scripts/check_imports.py`.

**Feature 16 Core v2 is DONE** (implemented in PR #158 + end-to-end testing
fixes, 2026-07-19): a LlamaIndex-based engine coexisting with the frozen v1
engine behind the version-dispatching `indexed.core.engine` facade, with
manifest-authoritative per-collection routing, explicit engine selection for new
collections, optional reranking, unified cross-engine relevance, and safe v1→v2
migration (dry-run, automatic backup, rollback, purge). Live surface:
`src/indexed/core/v2/`, `core/engine.py`, `core/versioning.py`; tests
`tests/unit/indexed/core/v2/`. Feature 15 (Review Remediation, merged in PR #155)
and Feature 16 both had their feature-spec folders promoted + deleted on
2026-07-19 (v2 routing contract → [Core Facade & App
Composition Root](../../tech/core-facade-composition-root.md); lessons → [lessons.md](../../lessons.md)). The full v2 planning
artifact (research + ADRs) lives in git history (PR #158).
