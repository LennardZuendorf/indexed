# Writing Product Specs

Product specs answer **what** and **why**. They describe user experience, not implementation. The moment you write code, component names, or architecture details — stop. That's a tech spec.

There are three places product content goes. Pick the right one.

---

## 1. Root: `product.md`

The mini PRD. **Stay high-level** — no feature-level detail (canonical: [SKILL.md](../SKILL.md) § Strict Rules).

Sections:
- **Story** — the problem in one paragraph
- **One-liner** — what the product is in one sentence
- **Requirements** — what the product must do at a project level
- **Design principles** — 3-7 rules that resolve ambiguity during implementation
- **Target user** — concrete, not "everyone"
- **Non-goals** — what you are explicitly NOT building
- **Implementation phases** — high-level milestones with exit criteria
- **Features index** — table linking to `features/<name>/product.md`
- **Open questions** — project-level decisions still open

Feature-level UX belongs in `features/<name>/product.md`.

---

## 2. Feature: `features/<name>/product.md`

Where feature-level UX and requirements live. **Short-lived** — created during DESIGN, archived after the feature ships.

Sections:
- **Scope** — Owns / Does not own table; explicit boundaries vs neighbour features
- **Why this feature exists** — the problem this feature solves, in one paragraph
- **Requirements** — numbered, testable
- **User experience** — what the user sees and does, with concrete examples
- **Outputs** — what the feature produces
- **Non-goals** — feature-scoped non-goals
- **Open questions** — feature-scoped questions

Link to feature `plan.md` in the header when present. Planning conventions: [plan.md](plan.md) (writing guide in this folder).

Frontmatter:
```yaml
---
type: feature-product
feature: <name>
sibling: tech.md
parent: ../../product.md
updated: YYYY-MM-DD
---
```

---

## 3. Branch: `product-{topic}.md`

**For cross-cutting concerns only.** Design system. Naming conventions. UX patterns that apply to every feature. If your "branch doc" is really about one feature, it's not a branch doc — it's a feature.

Create when:
- The topic spans multiple features
- The content has its own evolution (e.g., a design language that grows over time)
- Implementation guidance for this topic prevents mistakes across the project

Frontmatter:
```yaml
---
type: branch
parent: product.md
scope: <topic>
covers: <comma-separated list>
updated: YYYY-MM-DD
---
```

The `design` scope is the only place product and tech content may legitimately mix (design tokens are both brand identity and hex values).

---

## Anti-slop

Artifacts are durable memory — not session transcripts.

- **Repo-relative paths only** — `.spec/features/foo/product.md`, not absolute or machine-specific paths.
- **No process exhaust** — omit interview notes, brainstorming dumps, and "we considered X" unless the decision matters.
- **No qualifiers or hedges** — state decisions; delete "maybe", "probably", "might want to".
- **Omit empty sections** — if a section has no content yet, leave it out; add when there is something to say.

---

## Style Rules

**Do:**
- Describe what the user sees and does
- Use concrete examples
- State decisions with rationale
- Use tables for structured comparisons
- Write non-goals to prevent scope creep

**Don't:**
- Reference components, hooks, atoms, or any code constructs
- Mention codebase file paths
- Describe technical architecture or data flow
- Use words like "implement", "render", "component", "API"
- Write pseudocode

**Example — Describing a Feature:**
```markdown
## Auto-Save

Notes save automatically:
- Debounce 1.5s after the last keystroke
- Save on blur, tab switch, and window focus loss
- Cmd+S works but is rarely needed
- No save dialogs, ever

Dirty indicator (dot on tab title) appears immediately on edit, disappears on save.
```

No atoms, no event handlers, no file I/O. Pure user experience.

---

## Cross-References

Always link to your tech counterpart:
```markdown
**Architecture:** [tech.md](tech.md)            # for feature/branch docs
**Architecture:** [../../tech.md](../../tech.md)  # for feature docs pointing to root
```

This bridges WHAT to HOW so the reader can navigate.

---

## When to Update vs Create

- **Update** an existing doc when adding detail to an existing area
- **Create a feature** when scoping a new buildable unit of work
- **Create a branch doc** only when a genuinely cross-cutting concern emerges
- **Never** create a branch doc that's really about one feature — that's a feature
- **Never** put feature-level detail in root `product.md` — canonical rule in [SKILL.md](../SKILL.md) § Strict Rules

---

## Templates

- **Root entrypoint:** [templates/product.md](templates/product.md)
- **Feature spec:** [templates/feature-product.md](templates/feature-product.md)
- **Cross-cutting branch:** [templates/product-xxx.md](templates/product-xxx.md)
