---
type: concept
updated: 2026-11-26
---

# Feature Sequence: delivered-feature detail

**Feature 10 detail:** items #1 (ConfigService split), #2 (MCP decompose), #4
(flag parsing), #5 (exception hierarchy), #6 (schema versioning), #7 (public API)
all shipped. Architectural rules promoted to [Architectural Rules](../tech/architectural-rules.md).
Only the thin-command pattern (extract `knowledge/services/`, shrink oversized
command files) remains open — tracked as [issue #119](https://github.com/LennardZuendorf/indexed/issues/119), not a spec backlog item.

**Feature 11 detail:** Shipped 2026-07-03 — `indexed-protocols` leaf package;
core no longer depends on connectors; app composition root (then `bootstrap.py` +
`runtime.py`, folded into `composition.py` by Feature 13);
`resolve_collections_context()` storage parity for CLI/MCP; explicit config
registration; unified `read_for_mode`; shared HTTP retry policy; dead-code removal;
import-graph CI gate. Unblocks v2 core/connectors rewrite.

**Feature 13 detail:** Shipped 2026-07-08 — every audited bug fixed behind the
foundation/1 characterization harness (foundation/2–6); typed data contracts in
the `protocols` leaf (`Manifest`/`ConvertedDocument`/`Chunk`/`CollectionSearchResult`,
byte-stable round-trip) + corrected connector protocols (foundation/7); the
`core.v1.engine` facade (single core surface, v2 swap seam) + one `composition.py`
wiring site with two required callables, connector `from_manifest` replacing the
per-source/`localFiles` branches (foundation/8); read-mostly config verified
byte-stable across updates + both functional-wrapper singletons removed
(foundation/9). Two config tech-refinements are deferred follow-ups (foundation/9
note, shipped in PR #153): the `ConfigService.instance()` → `get_config()/reload()`
rename and the path/mode resolver consolidation — structure-only, R3 does not depend
on them; both are folded into Feature 14 Simplify (simplify/4). Unblocks Feature 14
(Simplify).

### Delivered baseline

Two tables split at the `v0.0.11` release boundary (published 2026-11-20), so a row
claims only what the artifact it names contains. Both record delivery, not the
milestone status in [readiness](readiness/README.md). A feature marked `◑` in
[Feature Sequence](feature-sequence.md) is still delivered where it appears: that
table tracks whether its live surface is complete, these track when the bytes shipped.

#### In the `v0.0.11` artifact

| Feature | State | Evidence |
| --- | --- | --- |
| Core indexing, connectors and v1/v2 coexistence | DONE | [Facade](../../../src/indexed/core/engine.py), [v2 and migration](../../../src/indexed/core/v2/), [connectors](../../../src/indexed/connectors/registry.py) |
| github-connector | SHIPPED, SPEC WRAP-UP OPEN | [GitHub connector](../../../src/indexed/connectors/github/), [#200](https://github.com/LennardZuendorf/indexed/pull/200) |
| retrieval-eval | SHIPPED, SPEC WRAP-UP OPEN | [Harness and evidence](../../../eval/README.md), [#297](https://github.com/LennardZuendorf/indexed/pull/297) |
| lsp-tier0 | SHIPPED, SPEC WRAP-UP OPEN | [Editor server](../../../src/indexed/lsp/), [#303](https://github.com/LennardZuendorf/indexed/pull/303) |
| lsp-tier1 | SHIPPED, SPEC WRAP-UP OPEN | [Editor system tests](../../../tests/system/test_lsp_out_of_process.py), [#303](https://github.com/LennardZuendorf/indexed/pull/303) |
| file-watcher | SHIPPED, CATCH-UP OPEN | [CLI #278](https://github.com/LennardZuendorf/indexed/pull/278), [MCP #316](https://github.com/LennardZuendorf/indexed/pull/316), [catch-up test](../../../tests/system/test_mcp_watch_freshness.py) |
| Canonical search, Git provenance and Claude Code installer | DONE | [Search contract](../../reference/search-output.md), [Git #293](https://github.com/LennardZuendorf/indexed/pull/293), [installer #317](https://github.com/LennardZuendorf/indexed/pull/317) |

#### On `main` since `v0.0.11`

| Feature | State | Evidence |
| --- | --- | --- |
| collection-registry | MERGED, SPEC IN REVIEW | [Registry](../../../src/indexed/config/collections_registry.py), [migration service](../../../src/indexed/cli/storage/commands/_migration.py), [#363](https://github.com/LennardZuendorf/indexed/pull/363), [#373](https://github.com/LennardZuendorf/indexed/pull/373) |
| workspace-selection | MERGED, SPEC IN REVIEW | [Selection](../../../src/indexed/config/workspace_selection.py), [resolver](../../../src/indexed/cli/composition.py), [#372](https://github.com/LennardZuendorf/indexed/pull/372) |
| codex-install, opencode-install | MERGED, SPEC IN REVIEW | [Codex](../../../src/indexed/cli/install_codex.py), [OpenCode](../../../src/indexed/cli/install_opencode.py), [#365](https://github.com/LennardZuendorf/indexed/pull/365), [#368](https://github.com/LennardZuendorf/indexed/pull/368) |
| MCP resource errors and Python range | MERGED | [#374](https://github.com/LennardZuendorf/indexed/pull/374), [#371](https://github.com/LennardZuendorf/indexed/pull/371), [pyproject](../../../pyproject.toml) |
