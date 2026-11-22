---
type: decision
updated: 2026-11-22
---

# 2026-07-08: Foundation (Feature 13) complete; two config cleanups deferred

**Decision:** Shipped foundation/7 (typed contracts in the `protocols` leaf),
foundation/8 (the `core.v1.engine` facade + one `composition.py` wiring site +
connector `from_manifest`, deleting `bootstrap.py`/`runtime.py`/
`connector_wiring.py`), and foundation/9 (read-mostly config verified byte-stable
via `tests/system/test_read_mostly_config.py`; both functional-wrapper singletons
removed). R1–R7 verified, full suite green, mypy at baseline, import-graph clean.
**Deferred** the `ConfigService.instance()` → `get_config()/reload()` API rename
(~86 call sites) and the path/mode resolver consolidation to a follow-up (they
can fold into Simplify's config work). **Rationale:** the self-replacing
singleton's only functional harm (dropping registered specs on `reset`) was
already fixed in foundation/6d, so what remains is a cosmetic/structural change
with no behavioral payoff; forcing an 86-site refactor as the last unit of an
unattended run risked destabilizing a green tree for no requirement gain. R3
(config is user-owned) is satisfied and regression-locked without it.
