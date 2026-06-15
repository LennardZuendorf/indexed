# Writing Design Specs

Design specs answer **how it should feel and behave** for users and agents. Interaction patterns, visual language, information hierarchy, tone — all welcome. Implementation detail is not — reference the tech spec instead.

There are two places design content goes. Pick the right one.

---

## 1. Root: `design.md`

The cross-cutting design language. **Stay high-level.** No feature-level flows or screens.

Sections (visual projects — see token-plus-prose below):
- **Overview** — look, feel, interaction personality, audience, what agents must preserve
- **Colors** — semantic roles and how tokens apply
- **Typography** — hierarchy, font roles, rhythm, reading density
- **Layout** — spacing, grid, density, responsive behavior, containment
- **Elevation & Depth** — shadows, borders, layers, tonal contrast
- **Shapes** — radius, edge language, icon shape, component silhouettes
- **Components** — reusable patterns with use-when guidance
- **Do's and Don'ts** — concise guardrails
- **Feature Design Index** — table linking to `features/<name>/design.md`

For **non-visual workflow design**, omit token groups and use prose-only sections such as design principles, interaction conventions, information hierarchy, and agent tone. See [Non-visual mode](#non-visual-prose-only-mode) below.

If you're describing one feature's screens or flows, you're in the wrong file. Move to `features/<name>/design.md`.

---

## 2. Feature: `features/<name>/design.md`

Where feature-level UX and interaction detail lives. **Short-lived** — created during DESIGN, merged or archived after COMPOUND.

Sections:
- **Design rules** — feature-scoped constraints agents must follow
- **User flows** — key paths, states, and transitions
- **Interaction detail** — controls, feedback, empty/error states
- **Copy and tone** — labels, messages, agent-facing language when relevant
- **Open questions** — feature-scoped design decisions still open

Optional: include token overrides in frontmatter when this feature diverges from root tokens.

Frontmatter:
```yaml
---
type: feature-design
feature: <name>
sibling: product.md
parent: ../../design.md
updated: YYYY-MM-DD
---
```

---

## Token-Plus-Prose Pattern

For visual identity or UI design systems, follow the public
[`DESIGN.md` format](https://github.com/google-labs-code/design.md): YAML
frontmatter for machine-readable tokens plus markdown prose for human rationale.

Use it inside `.spec/design.md` or `.spec/features/<name>/design.md`. Do not move
design docs out of `.spec/`.

**Useful token groups:**
- `colors`
- `typography`
- `rounded`
- `spacing`
- `components`

**Recommended section order** (match prose sections to token groups):
1. Overview
2. Colors
3. Typography
4. Layout
5. Elevation & Depth
6. Shapes
7. Components
8. Do's and Don'ts

Keep token groups you need; delete unused groups. Prose sections explain *why* and *when* — tokens hold the canonical values.

**Example — token frontmatter:**
```yaml
---
type: entrypoint
scope: design
design_format: google-labs-code/design.md-compatible
children: []
updated: 2026-06-06
colors:
  primary: "#1a1a2e"
  surface: "#ffffff"
typography:
  body:
    fontFamily: "Inter, sans-serif"
    fontSize: 16px
    lineHeight: 1.5
rounded:
  sm: 4px
  md: 8px
spacing:
  sm: 8px
  md: 16px
---
```

---

## Non-Visual Prose-Only Mode

Workflow, CLI, and agent-harness projects often have no visual interface. The same
`design.md` filename still applies — but the doc is prose-first:

- Omit token groups from frontmatter (or leave `design_format` unset).
- Replace visual sections with workflow-oriented prose: design principles, state
  visibility, delegation ergonomics, information hierarchy, adapter copy tone.
- Link to feature `design.md` files when a buildable unit has distinct interaction
  shape (e.g. setup vs verify flows).

Root `design.md` sets project-wide conventions; feature `design.md` captures
feature-scoped interaction detail. Product and tech specs stay separate — design
bridges feel and behavior without architecture or requirements duplication.

---

## Style Rules

**Do:**
- State concrete interaction rules agents can apply without guessing
- Use tables for component patterns, states, and copy conventions
- Link parent ↔ feature design docs both ways
- Preserve token values in frontmatter; explain semantics in prose
- Describe empty, loading, and error states when they affect UX

**Don't:**
- Specify file paths, APIs, or implementation choices — that's tech
- Restate requirements verbatim — link to product instead
- Use vague adjectives ("clean", "modern", "intuitive") without measurable rules
- Split one feature's design across root and feature docs

---

## Cross-References

Always link to your product and tech counterparts:
```markdown
**Product:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)
**Parent:** [../../design.md](../../design.md)  # from feature to root
```

---

## When to Update vs Create

- **Update** root `design.md` when a convention applies project-wide
- **Create a feature `design.md`** when UX, interaction, or tone detail is scoped to one buildable unit
- **Never** put feature-level flows or screens in root `design.md`
- **Never** duplicate product requirements in design — link and add feel/behavior only

---

## Templates

- **Root entrypoint:** [templates/design.md](templates/design.md)
- **Feature design:** [templates/design.md](templates/design.md) (same template; set `type: feature-design` and parent links)
