---
type: feature-design
feature: {name}
sibling: product.md
parent: ../../design.md
updated: {YYYY-MM-DD}
---

<!--
  TEMPLATE GUARDRAIL — feature design.md
  Job: feature-scoped look, feel, interaction, and workflow ergonomics (prose only).
  Do NOT: YAML design tokens (those belong in root design.md), code, file paths, plan units.
  Omit optional sections entirely when empty — placeholder prose is worse than absence.
-->

# Feature: {Name} — Design

{One paragraph: how this feature should feel and behave from a design perspective.}

**Parent:** [../../design.md](../../design.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Design Intent

{What agents should preserve when making design decisions for this feature. Tone, density, interaction personality.}

---

## Interaction Patterns

{How users move through this feature. Key flows, affordances, feedback loops. Concrete examples — no code.}

| Pattern | Use When | Notes |
|---|---|---|
| {Pattern} | {Situation} | {Constraint or example} |

---

<!-- include-when-material: Language & Copy — omit for non-UI features -->

## Language & Copy

{Terminology, labels, error messages, empty states. Keep consistent with root design.md.}

<!-- /include-when-material -->

<!-- include-when-material: Do's and Don'ts — omit when intent section is sufficient -->

## Do's and Don'ts

- Do {guideline specific to this feature}
- Don't {pitfall to avoid}

<!-- /include-when-material -->

<!-- include-when-material: Open Questions — omit when no design blockers -->

## Open Questions

1. **{Question}** — {Context. Recommendation if any.}

<!-- /include-when-material -->
