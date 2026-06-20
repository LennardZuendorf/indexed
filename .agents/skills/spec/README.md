# Spec Skill — Design Documentation System

> **For humans:** This README explains how the spec skill works. Agents read [SKILL.md](SKILL.md) instead.

## What This Skill Does

The **spec** skill teaches agents to write and maintain design documentation in `.spec/`. It enforces separation between product (what & why), tech (how), design (UX language), and plans (when & in what order). Two layers: persistent root specs (current content, no backlog) and branch-scoped per-feature folders (deleted before merge).

## Quick Start

```bash
# Initialize .spec/ in your project
/spec setup

# Navigate specs
/spec strategy          # Root layer — global specs
/spec feature <name>    # Feature layer — one named unit of work
/spec product           # Load product requirements
/spec tech              # Load technical docs
/spec plan              # Load implementation plan

# Maintenance
/spec validate          # Check consistency
```

## The Two-Layer Model

```
.spec/
│
├── product.md, tech.md, design.md, plan.md, lessons.md   # ROOT — persistent, high-level
├── product-{topic}.md, tech-{topic}.md                     # ROOT — cross-cutting branches (rare)
│
├── features/<name>/                                        # FEATURE — branch-scoped, detailed
│   ├── product.md          # required
│   ├── tech.md             # required
│   ├── plan.md             # recommended — stable `<name>/n` units
│   ├── design.md           # optional — UI/UX when needed
│   └── research.md         # optional
│
└── archive/<name>/         # transient post-wrapup safety net (deleted before merge)
```

**Root** answers project-level questions. **Feature** answers one closed, deliverable, testable box. Feature specs are written during design, consumed during implementation, merged when cross-cutting, archived transiently, then deleted before the branch merges (CODE IS TRUTH).

Canonical rules: [SKILL.md](SKILL.md) § The Two-Layer Model.

## Writing Order

### Bootstrap (strategy)

```
product.md → tech.md → design.md → plan.md (feature map, Feature Sequence with binary gates)
```

Branch docs (`product-{topic}.md`, `tech-{topic}.md`) only when a concern spans **every** feature — not as a substitute for feature folders.

### New feature (feature authoring flow)

Follow [feature.md](feature.md):

```
1. Locate & name     — confirm name; read root product/tech + lessons.md
2. Interview WHAT    — Scope, SHALL/MUST requirements, GWT scenarios → product.md
3. Rigor gate        — lite vs full (need design.md?)
4. Sketch HOW        — trace codebase → tech.md (+ design.md if full)
5. Plan units        — stable IDs, verification → plan.md (human gate)
6. Skip check        — atomic/no-decisions? → vibe-quick instead
```

Add the feature to the root `plan.md` Feature Sequence. Run `/spec validate` when done.

## Key Principles

### Strict separation

| Doc | Contains | Never contains |
|---|---|---|
| Product | User experience, requirements, rationale | Code, file paths, architecture |
| Tech | Paths, contracts, implementation | UX opinions |
| Plan | `feature/n` units, same-feature deps, verification | Code snippets, requirement prose, backlog |
| Design | Tokens, interaction patterns, visual language | Implementation detail (except tokens) |

### Progressive disclosure

- Read entrypoints and lessons first
- Load only what the task needs
- Follow links — don't load the whole tree

### Planning at two levels

- **Root `plan.md`** — feature map, boundaries, Feature Sequence (binary gates), current focus
- **`features/<name>/plan.md`** — unit tables (`<name>/n`), same-feature dependencies, verification per unit

Do not duplicate feature unit tables in the root plan; cross-feature order lives only in the root Feature Sequence.

## Workflow Examples

### Starting a new project

```bash
/spec setup
# Write root product.md, tech.md, design.md, plan.md
/spec validate
```

### Starting a new feature

```bash
/spec feature my-feature    # loads feature.md + folder if it exists
# Run the 6-step authoring flow in feature.md
/spec validate
```

### Resolving a design question

Discuss → decide → update the relevant spec → bump `updated:` → `/spec validate`.

## Validation

```bash
bash .agents/skills/spec/scripts/validate.sh   # vendored
bash ~/.agents/skills/spec/scripts/validate.sh # global install
```

Checks frontmatter, naming, internal links, orphaned children, and feature-folder consistency.

## References

- **Skill entrypoint:** [SKILL.md](SKILL.md)
- **Root layer:** [strategy.md](strategy.md)
- **Feature layer:** [feature.md](feature.md)
- **Writing guides:** [reference/product.md](reference/product.md), [reference/tech.md](reference/tech.md), [reference/plan.md](reference/plan.md), [reference/design.md](reference/design.md)
- **Templates:** [reference/templates/](reference/templates/)
- **Scripts:** [scripts/](scripts/) — `setup.sh`, `validate.sh`, `list-specs.sh`

## FAQ

**Q: Feature folder or branch doc?**
One named buildable unit → `features/<name>/`. Something spanning every feature → branch doc. Default to feature.

**Q: Can I have code in product specs?**
No. Product specs describe **what** and **why**, never **how**.

**Q: When do I need `design.md`?**
UI layout, interaction flows, visual language, or human-readable API/contract specs. Skip for pure backend/script work.

**Q: What order do I write specs in?**
Root entrypoints first (strategy). Per feature: product → tech → (design?) → plan. See [feature.md](feature.md).

**Q: Where do unit IDs live?**
In `features/<name>/plan.md` as `<name>/n` (e.g. `vibe-flow/1`). Add the feature to the root `plan.md` Feature Sequence. Cite IDs in commits and tests during implementation.

---
