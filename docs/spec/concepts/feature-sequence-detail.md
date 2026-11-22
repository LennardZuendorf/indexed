---
type: concept
updated: 2026-11-22
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
