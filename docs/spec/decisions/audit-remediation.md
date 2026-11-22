---
type: decision
updated: 2026-11-22
---

# 2026-07-05: Audit remediation

**Decision:** Cleaned the residue the architecture-audit branch left on Feature 11
infra — collapsed duplicated connector wiring, centralised `missing_wiring_error`
in `indexed_config.errors`, fixed the 2 branch-new `connector_wiring` mypy errors,
deleted the branch-broken `core.v1.Index` facade + dead re-export registries/DTOs,
hardened the import-graph gate to forbid upward `indexed` imports (with a negative
test), de-tautologised weak tests, and corrected the documented mypy command.
**Rationale:** A clean graph deserves clean code/types/tests/docs before the v2
rewrite. Feature spec compounded into [lessons.md](../lessons.md) + `AGENTS.md`, then
deleted. 1449 tests green; mypy 0-new on touched files; ruff + validate clean.
