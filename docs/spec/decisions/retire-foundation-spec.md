---
type: decision
updated: 2026-11-22
---

# 2026-07-09: Retire the Foundation feature spec

**Decision:** Feature 13 Foundation is DONE/merged (PR #153), so its
`docs/spec/features/foundation/` folder is retired. The still-owed architectural rules
were promoted into root tech specs — typed data contracts and the corrected connector
protocol/`from_manifest` into [Protocols Package](../tech/protocols-subpackage.md) +
[Typed Data Contracts](../tech/core/core-typed-data-contracts.md); the `core.v1.engine` facade +
single `composition.py` wiring site into [Core Facade & App
Composition Root](../tech/core-facade-composition-root.md) (replacing the stale `bootstrap.py`/`runtime.py` description); the
corrected protocol into [Connector Protocol](../tech/connectors/connectors-protocol.md).
The full 2026-07-06 bug catalogue was **not** re-promoted (all ~40 defects are fixed
and it is resolved backlog — root stays high-level with no backlog); it lives in PR #153
and git history, with behavior regression-guarded by `tests/characterization/`. The
single-`Progress`-protocol rule was deliberately **not** promoted: the dual
callback system still exists and its collapse is a Feature 14 (simplify/2) target, so
promoting it now would be spec-drift ahead of code. **Rationale:** a completed feature
folder must not linger; content that outlives the branch belongs in root specs, and
resolved backlog belongs in history, not the spec.
