---
type: decision
updated: 2026-11-22
---

# 2026-07-12: Feature 15 (Review Remediation) opened

**Decision:** Capture the confirmed defects from the extra-high-effort review of
PR #155 as Feature 15 rather than fixing ad-hoc. The review ran 14 finder passes
(Opus/Sonnet/Haiku subagents) + 8 adversarial verifiers + a gap sweep over the
changed `src/indexed/` surface; every requirement traces to a defect confirmed or
plausible against real code at HEAD (several with live repros). Fifteen
requirements grouped into nine mostly-independent units, ordered P1 (data-loss /
common-path crash / silent-wrong) → P2 → P3 (diagnosability + test coverage).
**Rationale:** the defects are point fixes on stable surface, but each needs a
regression test so the next refactor can't reintroduce it — that is feature-layer
work, not a root backlog. Two altitude questions are deferred to design-in-unit:
whether R7 (Rich-markup safety) lands as a shared render seam vs per-site escaping,
and whether R13 re-wires `max_skipped_items_in_row` skip/retry or deletes the dead
param. Folder deletes before the branch merges per spec rules; any cross-cutting
outcome (R7 seam) promotes to root tech.md at wrap-up.
