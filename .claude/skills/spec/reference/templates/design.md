---
type: entrypoint
scope: design
design_format: google-labs-code/design.md-compatible
children: []
updated: {YYYY-MM-DD}
# Optional visual design tokens. Keep when useful; delete unused groups.
colors:
  primary: "{#000000}"
  secondary: "{#666666}"
  neutral: "{#ffffff}"
typography:
  body:
    fontFamily: "{Font family}"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: 4px
  md: 8px
spacing:
  sm: 8px
  md: 16px
---

<!--
  TEMPLATE GUARDRAIL — root design.md
  Job: cross-cutting look, feel, and design language (tokens + prose). Link down via Feature Design Index.
  Do NOT: feature-specific interaction detail, code, plan units, implementation paths.
  Omit optional sections entirely when empty — placeholder prose is worse than absence.
  Non-visual projects: delete unused token groups from frontmatter; keep prose sections that apply.
-->

# {Project Name} — Design

Cross-cutting design language for the product. This template follows the spirit
of the google-labs-code `DESIGN.md` format: machine-readable tokens in YAML
frontmatter and human-readable rationale in markdown prose. Keep token groups
when this project has a visual interface; omit them for non-visual workflow
design.

**Product:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

---

## Overview

{Describe the product's look, feel, interaction personality, target audience,
and what agents should preserve when making design decisions.}

<!-- include-when-material: Colors — omit when no visual interface or tokens deleted -->

## Colors

{Explain semantic color roles and how the YAML tokens should be applied.}

<!-- /include-when-material -->

<!-- include-when-material: Typography — omit when not applicable -->

## Typography

{Explain type hierarchy, font roles, rhythm, and reading density.}

<!-- /include-when-material -->

<!-- include-when-material: Layout — omit when not applicable -->

## Layout

{Explain spacing, grid, density, responsive behavior, and containment.}

<!-- /include-when-material -->

<!-- include-when-material: Elevation & Depth — omit when not applicable -->

## Elevation & Depth

{Explain shadows, borders, layers, tonal contrast, or the lack of elevation.}

<!-- /include-when-material -->

<!-- include-when-material: Shapes — omit when not applicable -->

## Shapes

{Explain radius, edge language, icon shape, and component silhouettes.}

<!-- /include-when-material -->

<!-- include-when-material: Components — omit when no reusable component patterns yet -->

## Components

| Pattern | Use When | Notes |
|---|---|---|
| {Pattern} | {Situation} | {Constraint or example} |

<!-- /include-when-material -->

<!-- include-when-material: Do's and Don'ts — omit when overview is sufficient -->

## Do's and Don'ts

- Do {guideline}
- Don't {pitfall}

<!-- /include-when-material -->

## Feature Design Index

| Feature | Design Detail |
|---|---|
| {Feature} | [features/{name}/design.md](features/{name}/design.md) |

Feature-level interaction and copy live in `features/<name>/design.md` — not here.
