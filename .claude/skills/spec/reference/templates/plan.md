---
type: entrypoint
scope: implementation
covers: feature sequence, build order, validation criteria, open decisions
children: []
updated: {YYYY-MM-DD}
---

<!--
  TEMPLATE GUARDRAIL — root plan.md
  Job: cross-feature sequencing (WHAT ships WHEN). Link to feature plan.md for units.
  Do NOT: feature unit tables, step-by-step tasks, product re-litigation, architecture detail.
  Omit optional sections entirely when empty — placeholder prose is worse than absence.
-->

# {Project Name} — Implementation Plan

{One paragraph: current delivery focus, how features compose, and which feature is active. Current-only — no long-horizon backlog.}

**Parent specs:** [product.md](product.md), [tech.md](tech.md), [design.md](design.md)

**Feature plans (unit-level detail lives here, not duplicated below):**

| Feature | Product | Plan | Status |
|---|---|---|---|
| [{name}](features/{name}/product.md) | `.spec/` + {layer} | [plan.md](features/{name}/plan.md) | {planned / in progress / done} |

---

<!-- include-when-material: Validation Summary — omit until a meaningful audit exists -->

## Validation Summary

{What is built vs what remains. Honest spec-vs-repo gap if any.}

<!-- /include-when-material -->

## Feature Boundaries

{ASCII diagram or table: what each feature owns vs does not own. Prevents scope bleed.}

```
{feature-a}  ── owns ──>  {paths / concerns}
{feature-b}  ── owns ──>  {paths / concerns}
```

| Layer | Owns | Does not own |
|---|---|---|
| **{feature}** | {paths, scripts, contracts} | {neighbour features, root concerns} |

---

## Feature Sequence

Whole-feature delivery order with **binary** gates — a downstream feature starts only when its upstream is `DONE`. Units (`feature/n`) live in feature plans, never here.

| Order | Feature | Deliverable | Test | Status | Starts when |
|---:|---|---|---|---|---|
| 1 | {name} | {artifact set} | `tests/{name}/...` | {NOT STARTED / ACTIVE / DONE} | — |
| 2 | {name} | {artifact set} | `tests/{name}/...` | {…} | {feature 1} DONE |

Pick by repo shape:

- **Single-goal / small repo** — the strategy *is* the one end goal; this numbered list **is** the roadmap (no separate milestone layer).
- **Larger repo** — keep the binary-gate table; promote big features into sibling feature folders rather than nesting.
- **No single endgame** — drop the order column and list features as an **unordered cluster** with no cross-edges. Do not force a linear arc onto unrelated work.

Cross-feature order is **only** here. Feature plans declare same-feature unit deps only.

<!-- include-when-material: Spec vs Implementation — omit when spec and repo are aligned -->

## Spec vs Implementation

| Gap | Feature / unit | Notes |
|---|---|---|
| {Known drift} | {name}/n | {One line} |

Honest inventory of spec-ahead-of-code. Close via feature units; shrink this table over time.

<!-- /include-when-material -->

<!-- include-when-material: Current Focus — omit when idle between features -->

## Current Focus

{Active feature, next human gate. Keep to 2–3 sentences; bump `updated:` when it changes. No long-horizon backlog — work-ready items only.}

<!-- /include-when-material -->
