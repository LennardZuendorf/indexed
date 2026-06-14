---
type: entrypoint
scope: product
children:
  - product-{topic}.md
updated: {YYYY-MM-DD}
---

<!--
  TEMPLATE GUARDRAIL — root product.md
  Job: project anchor (WHAT/WHY at project level). Link down via Features index.
  Do NOT: feature-level UX, file paths, implementation, code constructs, unit tables.
  Omit optional sections entirely when empty — placeholder prose is worse than absence.
-->

# {Project Name} — Product

{One-paragraph description: what this project is, who it's for, and what makes it distinct.}

**One-liner:** {Single sentence that captures the essence.}

---

## Story

{The problem in one paragraph. Why this project exists now. What changes when it ships.}

---

## Requirements

At a project level, {Project Name} must:

1. **{Requirement headline}.** {Concrete, testable project-level obligation.}
2. **{Requirement headline}.** {…}

---

## Design Principles

1. **{Principle}.** {Why this principle matters and how it resolves ambiguity.}
2. **{Principle}.** {Explanation.}
3. **{Principle}.** {Explanation.}

---

## Target User

{Specific description of who uses this. Not "everyone" — a concrete persona.}

---

## Features

| Feature | Covers |
|---|---|
| **[features/{name}/](features/{name}/product.md)** | {One line — what this feature owns at a product level.} |

Add one row per active feature. Feature-level UX and requirements live in `features/<name>/product.md` — not here.

<!-- include-when-material: Implementation Phases — omit this section when phases are not yet defined -->

## Implementation Phases

| Phase | Goal | Exit Criteria |
|---|---|---|
| **1: {Name}** | {What this phase achieves} | {How you know it's done} |
| **2: {Name}** | {What this phase achieves} | {How you know it's done} |

<!-- /include-when-material -->

<!-- include-when-material: Non-Goals — omit when nothing to exclude yet -->

## Non-Goals

- {Thing you are explicitly NOT building}
- {Another non-goal}

<!-- /include-when-material -->

<!-- include-when-material: Open Questions — omit when no project-level blockers -->

## Open Questions

1. **{Question}** — {Context. Recommendation if any.}

<!-- /include-when-material -->

<!-- include-when-material: Branch Documents — omit when no cross-cutting product branches exist -->

## Branch Documents

| Document | Covers |
|---|---|
| **[product-{topic}.md](product-{topic}.md)** | {Summary of what this branch covers} |

<!-- /include-when-material -->
