---
type: feature-plan
feature: {name}
sibling: tech.md
parent: ../../plan.md
updated: {YYYY-MM-DD}
---

<!--
  TEMPLATE GUARDRAIL — feature plan.md
  Job: HOW to build this feature (units, files, verification). Link up to product.md for WHAT.
  Do NOT: re-litigate product requirements, UX prose, architecture essays, root milestones.
  Omit optional sections entirely when empty — placeholder prose is worse than absence.
-->

# Feature: {Name} — Implementation Plan

{One-paragraph summary: what this feature delivers and in what order. This feature is a closed, deliverable, testable box.}

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)
<!-- Add Design header link when design.md exists (optional). -->

**Feature gate:** Starts when {upstream feature} is `DONE` (root [plan.md](../../plan.md) Feature Sequence). Does not depend on any other feature's units — only on the whole upstream feature.

---

## Problem Frame

{The technical problem this plan solves. Why these units, in this order. One tight paragraph — do not restate product requirements.}

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [{Short name}](product.md#{anchor}) | {name}/1, {name}/2 |
| R2 | [{Short name}](product.md#{anchor}) | {name}/3 |

Every unit below MUST cite the R-IDs it satisfies. Add rows as requirements grow; do not renumber R-IDs.

---

## Key Technical Decisions

1. **{Decision}.** {Trade-off and rationale. Link to tech.md for detail.}
2. **{Decision}.** {…}

---

## Unit IDs

Units are `{name}/n` — the feature slug plus an integer assigned once and **never renumbered** on reorder (add a new `{name}/n` for new work). An optional **Seq** holds rewriteable execution order. Cite IDs in commits and tests during impl (`feat({name}): {name}/1 ...`).

---

### {name}/1 — {Unit name}

**Goal:** {One sentence — what ships in this slice.}

**Requirements:** R1, R2

**Dependencies:** {Prior **same-feature** units only; use `—` when none. Cross-feature order lives in the root Feature Sequence, never here.}

**Files:**

```
{path/to/file.ext}        # {what changes}
{path/to/other.ext}       # {what changes}
```

**Test scenarios:**

- {Observable behaviour to prove — maps to product requirement scenarios}
- {…}

**Verification:** {Command, test path, script output, or behaviour check that proves this unit done.}

---

### {name}/2 — {Unit name}

**Goal:** {…}

**Requirements:** R2

**Dependencies:** {name}/1

**Files:**

```
{path/to/file.ext}
```

**Test scenarios:**

- {…}

**Verification:** {…}

---

<!-- include-when-material: Dependencies — omit when all deps are per-unit above -->

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| {name}/2 | {downstream same-feature units} | {name}/1 |

Same-feature dependencies only. Cross-feature order is a whole-feature gate in the root [plan.md](../../plan.md) Feature Sequence, not a unit edge here.

<!-- /include-when-material -->

<!-- include-when-material: Spec vs Implementation — omit when spec and repo are aligned -->

## Spec vs Implementation

| Gap | Tracked in | Notes |
|---|---|---|
| {Known delta between spec and repo} | {name}/n | {One line} |

<!-- /include-when-material -->

<!-- include-when-material: Progress — omit until work begins -->

## Progress

| Unit | Status |
|---|---|
| {name}/1 | NOT STARTED |
| {name}/2 | NOT STARTED |

<!-- /include-when-material -->

<!-- include-when-material: Open Questions — omit when no planning blockers -->

## Open Questions

1. **{Question}** — {Context. Recommendation if any.}

<!-- /include-when-material -->
