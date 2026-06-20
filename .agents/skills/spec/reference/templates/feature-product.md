---
type: feature-product
feature: {name}
sibling: tech.md
parent: ../../product.md
updated: {YYYY-MM-DD}
---

<!--
  TEMPLATE GUARDRAIL — feature product.md
  Job: WHAT this feature must do (requirements, scope, UX). Link to tech.md for HOW.
  Do NOT: file paths, code, APIs, algorithms, plan units, implementation steps.
  Omit optional sections entirely when empty — placeholder prose is worse than absence.
-->

# Feature: {Name} — Product

{One-paragraph summary: what this feature does, who uses it, what it produces.}

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
<!-- Add Design and Plan header links when design.md / plan.md exist (both optional). -->

---

## Scope

| | |
|---|---|
| **Owns** | {Paths, scripts, contracts this feature writes} |
| **Does not own** | {Neighbour features and root concerns — explicit negatives} |

---

## Requirements

### Requirement: {Short name}

The system SHALL {concrete, testable obligation using RFC 2119 MUST/SHALL language}.

#### Scenario: {Scenario name}

- **Given** {precondition}
- **When** {action or trigger}
- **Then** {observable outcome}

### Requirement: {Short name}

The system MUST {another obligation}.

#### Scenario: {Scenario name}

- **Given** {precondition}
- **When** {action or trigger}
- **Then** {observable outcome}

Reference requirements as R1, R2, … in the feature plan's Requirements Trace.

<!-- include-when-material: User Experience — omit when requirements fully capture UX -->

## User Experience

{What the user sees and does. Concrete examples. No code, paths, or component names.}

```
{Example interaction or output sample}
```

<!-- /include-when-material -->

<!-- include-when-material: Outputs — omit when outputs are obvious from requirements -->

## Outputs

- {What the feature writes / produces / changes}
- {…}

<!-- /include-when-material -->

<!-- include-when-material: Non-Goals — omit when nothing feature-scoped to exclude -->

## Non-Goals

- {What this feature is explicitly NOT doing}
- {…}

<!-- /include-when-material -->

<!-- include-when-material: Open Questions — omit when no feature-scoped blockers -->

## Open Questions

1. **{Question}** — {Context. Recommendation if any.}

<!-- /include-when-material -->
