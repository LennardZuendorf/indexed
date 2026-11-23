---
type: decision
updated: 2026-11-22
---

# 2026-07-06: Split right-sizing into Foundation + Simplify

**Decision:** After the full audit (main + app/packages/overengineering passes)
and a 5-agent deep correctness hunt that confirmed ~33 behavioral bugs — several
corruption/data-loss/secret class — split the original single right-sizing
feature into two: **Feature 13 Foundation** (architecture & correctness: fix
every bug behind a characterization harness, land typed contracts + core-swap
facade, in the current layout) and **Feature 14 Simplify** (codebase reduction:
collapse to one package, delete dead code + mechanism tests, shrink chrome).
Foundation is gated first; Simplify is gated on Foundation DONE; the v2 rewrite
on both. Per user decision, architecture lands in the current 7-package layout
and the workspace collapse is deferred to Simplify. Tests-before-refactor is
enforced structurally: foundation/1 is the harness that gates every refactor
unit. Evidence: the full 2026-07-06 bug catalogue (~40 defects, all fixed) shipped in
the Foundation merge (PR #153) and remains in git history; the behavior it locked in is
regression-guarded by `tests/characterization/`. Size inventory: the 2026-07-06
audit (shipped with Feature 14, retained in git history).
**Rationale:** A 3-star personal project doesn't need a 7-package workspace,
1.17× tests-to-source, or 15k LOC of process apparatus; a v2 built on stringly
dict contracts would re-rot. Typed contracts + one facade make the core swap
cheap and safe.
