---
type: entrypoint
scope: technical
children:
  - tech-{topic}.md
updated: {YYYY-MM-DD}
---

<!--
  TEMPLATE GUARDRAIL — root tech.md
  Job: project architecture anchor (HOW at project level). Link down via Features index.
  Do NOT: feature-level file lists, algorithms, UX opinions, unit tables.
  Omit optional sections entirely when empty — placeholder prose is worse than absence.
-->

# {Project Name} — Technical Architecture

{One paragraph: project-level architecture summary. Feature implementation detail lives under `.spec/features/<name>/`.}

---

## Design Philosophy

1. **{Principle}.** {Technical guiding rule that constrains decisions.}
2. **{Principle}.** {Technical guiding rule.}
3. **{Principle}.** {Technical guiding rule.}

---

## Architecture Overview

```
{project}/
├── src/
│   ├── {directory}/          # {annotation: NEW / inherited / extended}
│   └── {directory}/          # {annotation}
├── {other dirs}/
└── .spec/                    # Design docs
```

---

## Tech Stack

**Inherited:** {Technologies and tools that come from upstream or existing infra.}

**Added:** {New dependencies introduced for this project.}

---

## State / Data Contracts

{File formats, protocols, and invariants that span features. What lives where; what must never be mixed.}

| Contract | Location | Invariant |
|---|---|---|
| {Name} | `{path}` | {Rule that must hold across features} |

---

## Build vs Inherit

| Source | Approx. Lines | What |
|---|---|---|
| **{Upstream}** (inherited) | ~{N}k | {What it provides} |
| **{New code}** (this project) | ~{N} | {What we actually write} |

---

## Build Sequence

| Order | Component | Feature |
|---|---|---|
| 1 | {Component or milestone} | {feature-name} |
| 2 | {Component or milestone} | {feature-name} |

Map build order to features. Unit-level detail lives in feature `plan.md` — not here.

---

## Features

| Feature | Covers |
|---|---|
| **[features/{name}/](features/{name}/tech.md)** | {One line — architecture this feature owns.} |

Add one row per active feature. Feature-level files, APIs, and algorithms live in `features/<name>/tech.md` — not here.

<!-- include-when-material: Basic Implementation — omit when no small cross-cutting support pieces exist -->

## Basic Implementation

{Installer scripts, conventions, and small support pieces that do not warrant their own feature.}

<!-- /include-when-material -->

<!-- include-when-material: Risks & Mitigations — omit when no project-level technical risks yet -->

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| {Risk description} | {How to handle it} |

<!-- /include-when-material -->

<!-- include-when-material: Branch Documents — omit when no cross-cutting tech branches exist -->

## Branch Documents

| Document | Covers |
|---|---|
| **[tech-{topic}.md](tech-{topic}.md)** | {Summary of what this branch covers} |

<!-- /include-when-material -->
