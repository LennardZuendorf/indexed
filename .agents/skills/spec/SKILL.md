---
name: spec
description: |
  Maintains `.spec/` design docs across two layers: persistent root specs
  (product, tech, design, plan, lessons, branch docs) kept current with no
  backlog, and branch-scoped `features/<name>/` folders that merge to root,
  archive transiently, then delete before the branch merges.
  Use when scoping a feature, bootstrapping strategy, reviewing architecture,
  updating a spec, validating consistency, or the user mentions spec, PRD,
  design doc, tech design, feature spec, or branch doc.
user-invocable: true
argument-hint: "[strategy|feature [<name>]|product|tech|design|plan|lessons|setup|validate]"
allowed-tools: Read, Bash(bash .agents/skills/spec/scripts/validate.sh), Bash(bash .agents/skills/spec/scripts/list-specs.sh), Bash(bash .agents/skills/spec/scripts/setup.sh), Bash(bash ~/.agents/skills/spec/scripts/validate.sh), Bash(bash ~/.agents/skills/spec/scripts/list-specs.sh), Bash(bash ~/.agents/skills/spec/scripts/setup.sh)
compatibility: Requires bash. macOS and Linux.
metadata:
  author: lennarddib
  version: "1.8"
---

# Spec System

Every project's design lives in `.spec/`. Single source of truth for what you're building, why, and how. Read specs before writing code. Update specs when decisions change.

## Agent quick start

1. **Pick layer** — global/root work → [strategy.md](strategy.md); one named feature → [feature.md](feature.md) + `.spec/features/<name>/`.
2. **Pick route** — explicit `/spec <arg>` → [Routing § $ARGUMENTS](#routing); no arg → [Routing § Route by task type](#routing).
3. **Finish** — bump `updated:` on every edited spec; run `bash .agents/skills/spec/scripts/validate.sh` (or global install path).

## Why Specs Exist

- **Persistent memory** — decisions survive across sessions
- **Separation of concerns** — product thinking stays separate from implementation thinking
- **Progressive disclosure** — load only what you need, when you need it
- **Shared language** — consistent vocabulary between product and tech

## The Two-Layer Model

Specs come in two layers. Use the right one for the job — mixing them is the most common mistake.

```
.spec/
│
│  ─── ROOT LAYER (high-level, persistent) ──────────────
│
├── product.md                # mini PRD — story, requirements, principles
├── tech.md                   # architecture summary — stack, principles, basic implementation
├── design.md                 # cross-cutting product/UX design language
├── plan.md                   # implementation roadmap
├── lessons.md                # accumulated mistakes, read at session start
├── product-{topic}.md        # cross-cutting product branch (design system, conventions)
├── tech-{topic}.md           # cross-cutting tech branch (infrastructure, observability)
│
│  ─── FEATURE LAYER (detailed, branch-scoped) ──────────────
│
├── features/<name>/
│   ├── product.md            # what this feature does (requirements)
│   ├── tech.md               # how this feature is built (architecture)
│   ├── design.md             # optional, feature UX / interaction detail
│   ├── plan.md               # optional, feature-scoped roadmap (`<name>/n` units)
│   └── research.md           # optional, discovery artifacts
│
└── archive/<name>/           # transient post-wrapup safety net (deleted before merge)
```

**Root layer rules:**
- `product.md` is the mini PRD: story, target user, requirements, design principles, non-goals.
- `tech.md` is the architecture summary: design philosophy, stack, file layout, state contracts, basic implementation, build sequence, risks.
- `design.md` is the cross-cutting design language: UX principles, interaction conventions, interface tone, and reusable design patterns. It may bridge product and implementation vocabulary when that helps design stay actionable.
- `plan.md` sequences the work at the **root** layer: feature map, Feature Sequence with binary whole-feature gates, current focus. Current-only — no long-horizon backlog. Unit-level detail (`<name>/n`) lives in `features/<name>/plan.md`. See [reference/plan.md](reference/plan.md).
- Branch docs (`product-{topic}.md`, `tech-{topic}.md`) cover **cross-cutting concerns only** — things that span every feature. Design system. Infrastructure. Naming conventions. If the topic is really about one feature, it belongs in the feature layer.

**Feature layer rules:**
- One directory per feature in `.spec/features/<name>/`. Always contains `product.md` and `tech.md`. Recommended: `plan.md` with stable unit IDs (`<name>/n`). Optionally `design.md`, `research.md`. Every feature `product.md` includes a **Scope** table (Owns / Does not own). Each feature is a closed, deliverable, testable box; cross-feature order is a whole-feature gate in the root plan, never a unit-to-unit edge.
- Feature specs are **branch-scoped**: written during DESIGN, consumed during IMPL, merged into root layer during COMPOUND, archived as a transient safety net, then **deleted before the branch merges** (agent prompts after validation). CODE IS TRUTH; archive is never read for active work (see [Wrapped-up features](#wrapped-up-features)).
- Cross-cutting decisions from a feature get merged into root `tech.md` or relevant branch doc. Feature-specific detail does not promote — it is discarded with the deleted folder.

## Strategy vs Feature — Which layer?

| You are… | Load first |
|---|---|
| Editing or bootstrapping **global** specs (root files, branch docs, lessons, writing order, product/tech/design/plan line) | [strategy.md](strategy.md) then the root `.spec/` files it points to |
| Creating or editing **one named feature** folder under `.spec/features/<name>/` | [feature.md](feature.md) then that folder's `product.md` + `tech.md` |

**Rule of thumb:** one buildable unit of work with a name → feature layer. Something that spans every feature → root branch doc (`product-{topic}.md` / `tech-{topic}.md`). If unsure, default to feature; extract to a branch doc when the same concern keeps recurring.

## Feature authoring flow

Ladder: **locate & name → interview WHAT → rigor gate → sketch HOW → plan units → skip check.**

- **product.md** — requirements with SHALL/MUST + GWT scenarios; Scope table; no code.
- **tech.md** — paths, contracts, files traced from the repo; only filled sections.
- **plan.md** — stable unit IDs citing requirement IDs; verification evidence per unit.

Full steps, rigor gate, and skip conditions: [feature.md](feature.md).

## Navigation Rules

1. **Read entrypoints first.** Branch docs and feature specs assume you have parent context.
2. **Read lessons at session start.** Past mistakes inform current decisions.
3. **Never load all specs at once.** Load only what's relevant.
4. **Follow the links.** Entrypoints link to features and branches. Trust the graph.

## Strict Rules

1. **Read before write.** Never edit a spec you haven't read in this session.
2. **Root specs stay high-level.** No feature-level detail in root `product.md` or `tech.md` — use `features/<name>/`. (Canonical statement; do not duplicate elsewhere.)
3. **One concern per doc.** Product specs contain zero code. Tech specs contain zero UX opinions. Design-system docs may cross the line — they're the only exception.
4. **Bump `updated:`.** Change the `updated:` date every time you edit a spec.
5. **Keep cross-references alive.** Link parent ↔ child both ways. List children in entrypoint frontmatter.
6. **Validate after changes.** Run `bash .agents/skills/spec/scripts/validate.sh` when the skill is vendored, or the equivalent global install path.
7. **Feature specs are branch-scoped.** Don't write them as if they're permanent. Cross-cutting decisions merge to root; the feature folder is archived transiently then deleted before the branch merges (see below). No backlog in any spec — work-ready items only; long-term ideas live in an external tracker.

## Wrapped-up features

When a feature arc completes (COMPOUND / wrap-up), follow this sequence:

1. **Promote** — merge cross-cutting blocks from `features/<name>/tech.md` (and product/design when relevant) into root `.spec/{product,tech,design,plan}.md`. Use `<!-- merge -->` markers or hand-merge; see [reference/tech.md](reference/tech.md).
2. **Record** — append a tagged lesson to `.spec/lessons.md` when a durable rule surfaced (via `vibe-compound`).
3. **Update root plan** — set the feature to **DONE** in the `.spec/plan.md` Feature Sequence and cleanse delivered detail to a one-line note. Link the **live surface** (skill path, root doc section, test suite) — not the removed feature folder.
4. **Archive transiently** — `mv features/<name>/ archive/<name>/` as a safety net (e.g. CI fails right after wrapup). Archive is **never** read for active work — CODE IS TRUTH.
5. **Prompt to delete** — after validation passes, prompt the user to delete `archive/<name>/`. The folder should be gone **before the branch merges**; keeping it is the justified exception, not the default.

**Why delete and not hoard:** the repo holds value-prop + architecture + current plan only. Decision archaeology that has standalone value can be kept in archive deliberately; otherwise delete — live artifacts (skill bundle, root specs, tests) are the truth.

**This repo:** `spec-framework` was **deleted, not archived** — truth lives in this skill bundle, root `.spec/` entrypoints, and `tests/spec/run.sh`.

**Agent rules after wrap-up:**

- Route to root `plan.md` Feature Sequence + live implementation paths — **never** restore `features/<name>/` because validation failed on a wrapped-up feature.
- Do not load `archive/<name>/` by default; it is cold, transient storage when it exists.
- Full lifecycle steps: [feature.md](feature.md) § Lifecycle and § Archive and delete.

## Routing

**$ARGUMENTS:**

| Argument | Action |
|---|---|
| `strategy` | Load [strategy.md](strategy.md) — global / long-living root layer |
| `feature` | Load [feature.md](feature.md) — feature layer rules (no folder yet) |
| `feature <name>` | Load [feature.md](feature.md) + `.spec/features/<name>/` |
| `product` | Load `.spec/product.md` and follow links |
| `tech` | Load `.spec/tech.md` and follow links |
| `design` | Load `.spec/design.md` and relevant design branch docs |
| `plan` | Load `.spec/plan.md` and relevant sub-plans |
| `lessons` | Load `.spec/lessons.md` |
| `setup` | Run [scripts/setup.sh](scripts/setup.sh) |
| `validate` | Run [scripts/validate.sh](scripts/validate.sh) |
| _(none)_ | Infer from task context (see table below) |

**Route by task type:**

| Task | Load first |
|---|---|
| Project bootstrap, design language, conventions, infra spanning every feature | [strategy.md](strategy.md), then root `.spec/` as needed |
| New feature scoping | `product.md` + `tech.md`, then [feature.md](feature.md) + create `features/<name>/` |
| Working on a **wrapped-up** feature (DONE in root plan, no `features/<name>/`) | root `plan.md` live-surface link + implementation path (skill, tests, root docs) — do not restore feature folder |
| Working on existing feature | [feature.md](feature.md) + `features/<name>/product.md` + `features/<name>/tech.md` + `plan.md` when present |
| Architecture, conventions, infrastructure | `tech.md` + relevant `tech-{topic}.md` |
| Design system, UX patterns | `design.md` + relevant `product-{topic}.md` or `tech-{topic}.md` if needed |
| Implementation planning, feature sequence | root `plan.md` + `features/<name>/plan.md` + [reference/plan.md](reference/plan.md) |
| UI / layout / user flows in a feature | `features/<name>/product.md` + `features/<name>/design.md` (if present) |

## Design.md Compatibility

For visual identity or UI design systems, prefer the public
[`DESIGN.md` format](https://github.com/google-labs-code/design.md): YAML
frontmatter for machine-readable tokens plus markdown prose for human rationale.
Use it inside `.spec/design.md` or `.spec/features/<name>/design.md`; do not move
design docs out of `.spec/`.

Useful token groups:
- `colors`
- `typography`
- `rounded`
- `spacing`
- `components`

Recommended section order for visual design docs:
1. Overview
2. Colors
3. Typography
4. Layout
5. Elevation & Depth
6. Shapes
7. Components
8. Do's and Don'ts

For non-visual workflow design, the same file may omit tokens and use prose-only
sections such as interaction conventions, information hierarchy, and agent tone.

## Current Project State

!`bash .agents/skills/spec/scripts/list-specs.sh`

## Setup, Templates, Validation

### Setup

`/spec setup` or `bash .agents/skills/spec/scripts/setup.sh` from a repo that vendors this skill — initializes `.spec/` with entrypoint templates and an empty `lessons.md`. If the skill is installed globally, `bash ~/.agents/skills/spec/scripts/setup.sh` is also valid. Does not create features (those are born when you scope a feature).

### Templates

Paths are under [reference/templates/](reference/templates/) (copy into your project's `.spec/`).

| Template | Use for |
|---|---|
| [reference/templates/product.md](reference/templates/product.md) | Root `product.md` |
| [reference/templates/tech.md](reference/templates/tech.md) | Root `tech.md` |
| [reference/templates/design.md](reference/templates/design.md) | Root `design.md` or feature `design.md` |
| [reference/templates/plan.md](reference/templates/plan.md) | Root `plan.md` |
| [reference/templates/feature-product.md](reference/templates/feature-product.md) | `features/<name>/product.md` |
| [reference/templates/feature-tech.md](reference/templates/feature-tech.md) | `features/<name>/tech.md` |
| [reference/templates/feature-plan.md](reference/templates/feature-plan.md) | `features/<name>/plan.md` |
| [reference/templates/feature-design.md](reference/templates/feature-design.md) | Optional `features/<name>/design.md` |

**Branch docs** (`product-{topic}.md`, `tech-{topic}.md`, `plan-{topic}.md`): no separate template files in this bundle — start from the root `product.md` / `tech.md` / `plan.md` templates, rename, set `type: branch` and parent/scope/covers per [reference/product.md](reference/product.md) and [reference/tech.md](reference/tech.md).

### Detailed writing guides

- **Product:** [reference/product.md](reference/product.md) — root vs feature, cross-cutting branches
- **Tech:** [reference/tech.md](reference/tech.md) — root vs feature, merge markers, cross-cutting branches
- **Design:** [reference/design.md](reference/design.md) — root vs feature, tokens + prose
- **Plans:** [reference/plan.md](reference/plan.md)

### Validation

`bash .agents/skills/spec/scripts/validate.sh` when the skill is vendored in the repo, or `bash ~/.agents/skills/spec/scripts/validate.sh` when installed globally — checks frontmatter, naming, internal links, orphaned children, and feature-folder consistency under `.spec/`.
