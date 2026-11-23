---
type: decision
updated: 2026-11-22
---

# 2026-09-03: Feature 18 (Core v2 Rendering Fixes, issue #187) shipped

**Decision:** Implemented all 5 units (R1–R8 verified) via
`superpowers:subagent-driven-development` — a fresh implementer subagent per
unit, a task-scoped spec+quality review after each (all 5 Approved; Minor
findings deferred to this log), then a final whole-branch review on the most
capable available model. Two integration-level gaps surfaced that no
per-unit review could see, both fixed and re-verified:
1. The controller's own post-unit full-suite run (not any task's scoped
   tests) caught one pre-existing test (`test_from_manifest.py`) asserting
   R3's old, now-superseded behavior (a glob pattern normalized to its
   `fnmatch.translate()` regex form) — outside Task 2's stated file list.
   Fixed by updating the assertion to the new, correct propagation value;
   no other sibling test depended on the old form.
2. The final whole-branch review found 4 Important findings the per-unit
   reviews structurally couldn't reach, fixed in one wave and re-verified
   clean by rendering real output (not just reasoning about it):
   - R1's fix (route `IndexedError` through the existing `print_error` panel)
     introduced a double-escape regression: `print_error`'s `Text(...)` sink
     renders literally, but the call site still `escape()`d first (correct
     for the OLD markup-parsed sink, wrong for the new literal one) — any
     error message containing `[` printed a visible backslash. Fixed by
     dropping the now-incorrect `escape()` call; the same pattern was found
     and fixed in a second, pre-existing (not introduced by this feature)
     call site (`search_render.py`'s `_print_collection_errors`).
   - R2's own written acceptance scenario (a v2 model descriptor on one line
     at 100+ columns) was unmet at ANY terminal width — the 100-column max
     clamp and a pure `ratio`-based label/value column split combined to cap
     below what a realistic descriptor needs. Fixed by raising the max to
     120 and switching the label column to a min-width auto-sizing column
     instead of ratio-based, verified by rendering the actual failing
     descriptor at multiple terminal widths, not by re-deriving the arithmetic.
   - R3's requirement that the new row align with its neighbors was left
     unmet — the `"Included Patterns"` label (17 chars) blew the existing
     10-char label-padding budget the sibling rows use. Fixed by shortening
     to `"Included"` (8 chars, matches the existing `"Excluded"` row).
   - R6's score-labeling requirement ("wherever a score renders") missed one
     of three render paths — `index search --compact` still rendered
     unlabeled scores. Fixed by applying the same `scoreKind` labeling
     pattern Task 4 already used in the other two paths.
**Rationale:** two independent verification layers — the controller's own
full-suite run between units, and a most-capable-model whole-branch review
after all units — exist precisely to catch defects no single unit's scoped
tests or review can see by construction. Both caught real, fixable gaps here;
neither required expanding the CONFIRMed 8-requirement scope. A handful of
Minor findings (stale docstrings describing superseded behavior in
`alerts.py`/`engine.py`; a pre-existing, practically-unreachable markup-escaping
gap in `format_search_results_compact` that the R6 fix extended to also carry
`score_kind`; duplicated score-label lookup logic across three render
functions; a legacy collection with a non-default glob pattern still
displaying raw regex on `update` until re-created) were deliberately left
unfixed rather than silently widening the branch past what two full review
passes had already scoped — recorded here, not fixed ad-hoc. Full gate green
throughout: ruff/ty/import-graph clean, full suite verified at delivery,
coverage above the required threshold.
