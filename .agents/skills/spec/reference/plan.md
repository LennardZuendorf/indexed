# Writing Plans

Plans sequence work. They reference product, tech, design, and feature specs — they do not duplicate them.

## Two layers

| Layer | File | Scope |
|---|---|---|
| **Root** | `.spec/plan.md` | Value-prop + architecture links, feature sequence, boundaries, current focus, spec-vs-repo gaps |
| **Feature** | `.spec/features/<name>/plan.md` | Unit tables (`feature/n`), same-feature dependencies, verification, feature-scoped open questions |

**Rule:** root plan = *which whole features ship in what order*. Feature plan = *how this one feature is sliced* into units. If you are writing step-by-step tasks for one feature, they belong in the feature plan.

Optional branch plans (`plan-{topic}.md`) follow the root pattern for cross-cutting workstreams (e.g. infrastructure rollout).

---

## The four rules

These govern how work is sliced, named, sequenced, and retired. They exist to keep features independent and the repo current.

### 1. Interdependence — features couple as whole boxes, never as slots

A feature is a closed, deliverable, testable box. Dependencies exist **between boxes**, never between units inside different boxes.

- A feature plan's unit `Depends` column lists **same-feature units only** (`vibe-flow/2` depends on `vibe-flow/1`).
- Cross-feature order lives **only** in the root plan, as a **binary** gate: the upstream feature is `DONE` before the downstream feature leaves `NOT STARTED`. No partial locks, no "after unit X of feature Y".
- Contracts between features are **shipped artifacts** (files, scripts, APIs) delivered by the upstream feature's acceptance — not living edges between mid-arc units.
- Parallel feature work is allowed **only** when the root sequence has no edge between the two features.

> Smell: you want `featureA/3` to depend on `featureB/5`. Fix: move the work to one owner, or serialize the whole features (see rule 2).

### 2. Feature slicing — closed, deliverable, testable

Slice until each feature can be delivered and tested on its own.

- **Deliverable:** feature `DONE` = a defined artifact set exists and passes the feature's acceptance check.
- **Testable:** every feature names a test surface (`tests/<feature>/...` or equivalent) in the root sequence.
- **Closed scope:** the plan only touches paths the feature `product.md` Scope table owns.
- **Split** when two features would edit the same paths mid-arc, or you keep needing a cross-feature unit dependency.
- **Grow** when work is one vertical slice through one layer — keep it in the owning feature instead of half-in-a-neighbour.
- **Merge** when two "features" always ship together and one's last unit is the other's prerequisite — they are one box.

### 3. Naming — path-shaped IDs, adaptive roadmap

Units are `feature-slug/n` (e.g. `vibe-flow/1`, `agent-instructions/3`). The path reads as what it is; no opaque prefix table.

- `n` is an integer assigned **once** and **never renumbered** on reorder — add a new `feature/n` for new work.
- An optional **Seq** column carries rewriteable execution order *within* a feature; the ID itself does not imply order.
- Cite IDs in commits and tests during impl: `feat(flow): vibe-flow/1 add orders blocks`.
- Legacy IDs (old `PREFIX+N`) survive only as a one-time alias footnote for git grep — never as live ordinals.

**Roadmap modes** (pick by repo shape):

- **Single-goal / small repo** — the repo strategy *is* the one end goal. List features in delivery order (1, 2, 3 …); that numbered feature list **is** the roadmap. No separate milestone layer.
- **Larger repo** — use a **Feature sequence** table with explicit binary gates (order, feature, deliverable, test, status, starts-when). When there is no single endgame, the sequence degrades to an **unordered cluster list** of independent features with no cross-edges — do not force a linear `M0 → M1` arc onto unrelated work.

### 4. Lifecycle — current-only, cleansed, code is truth

Feature specs are branch-scoped and the repo holds only what is live.

- Lifecycle: **created in DESIGN → consumed in IMPL → wrapped up in the single `compound` phase** (record lessons + promote cross-cutting decisions to root product/tech/plan + move the folder to `archive/` + regen the digest).
- **Archive is a transient safety net** (e.g. CI fails right after wrapup and the feature context is briefly useful). It is **never** a store for active work — **CODE IS TRUTH**. After validation passes, the agent **prompts the user to delete the archive**; the folder should be gone **before the branch merges**.
- The **root plan is current-only** and **cleansed after delivery** — delivered features collapse to a one-line historical note; the plan reflects current focus.
- **Backlog gate:** every plan entry is either work-ready with a clear dependency, or it does not belong in `.spec/`. Long-term / speculative work is tracked **outside** the repo (issue tracker) — a hint to humans, not a workflow artifact. No inline backlog; agents refuse to record speculative future work in specs.
- **Repo-type split:** app repos cleanse aggressively; single-purpose / greenfield repos keep a longer-lived feature list and may commit to main, but still cleanse once the initial purpose is delivered — future additions get fresh specs when tackled.

---

## When to write

| Moment | Write |
|---|---|
| Strategy / roadmap | Root `plan.md` — value-prop + architecture links, feature sequence |
| Feature design complete | Feature `plan.md` — units with stable `feature/n` IDs |
| Scope changes mid-flight | Amend the relevant plan; add units, never renumber |
| Compound | Promote cross-cutting sequencing into root `plan.md`; cleanse delivered detail to notes; archive then prompt to delete the feature folder |

Human gate: the root feature sequence and feature unit tables should be approved before `impl`.

---

## Sub-feature promotion — flat siblings, not nesting

When a large feature decomposes into pieces that each need their own product/tech docs, **promote them to sibling feature folders** — never nest `feature/subfeature/n`.

```text
ai-input/           product.md tech.md plan.md   → ai-input/1, ai-input/2
ai-input-suggest/   product.md tech.md plan.md   → ai-input-suggest/1 …
ai-input-offline/   product.md tech.md plan.md   → ai-input-offline/1 …
```

Decide where a sub-piece goes:

| Sub-piece is… | Goes where |
|---|---|
| Just implementation steps | `feature/n` units in the same plan |
| Demoable alone, needs its own product/tech docs | A new **sibling** feature folder |

Heuristic: once a feature exceeds ~5–8 units or wants more than one integration boundary, consider splitting it into siblings. Root plan then carries only whole-feature edges (`ai-input-suggest` depends on `ai-input`), never `ai-input-suggest/1` depends on `ai-input/3`.

---

## Unit table columns

| Column | Purpose |
|---|---|
| **ID** | Stable `feature/n` — never renumbered |
| **Seq** | Optional rewriteable execution order within the feature |
| **Summary** | One line — what ships |
| **Depends** | Prior **same-feature** units only (`—` when none) |
| **Verification** | Observable evidence — command, test path, behaviour check |

Pair each unit with observable evidence. Verify phase checks this table, not agent assertions. Cross-feature ordering is **not** a column here — it lives in the root feature sequence.

---

## Feature boundaries

Every feature `product.md` includes a **Scope** table:

| | |
|---|---|
| **Owns** | Paths, scripts, contracts this feature may write |
| **Does not own** | Neighbour features and root concerns — explicit negatives prevent bleed |

Root `plan.md` summarizes boundaries across features (diagram or table). Feature plans do not redefine product scope — they reference `product.md`.

---

## Standard feature doc headers

Consistent cross-links across the feature folder:

```markdown
**Parent:** [../../product.md](../../product.md)   # or ../../tech.md in tech.md
**Architecture:** [tech.md](tech.md)              # product.md
**Requirements:** [product.md](product.md)        # tech.md
**Design:** [design.md](design.md)                # when present
**Plan:** [plan.md](plan.md)                      # when present
**Related:** [../other-feature/product.md](../other-feature/product.md)  # when coupled
```

---

## Root plan sections

1. **Features** — table linking every active feature's product, tech, plan
2. **Feature boundaries** — who owns what (compressed from feature Scope tables)
3. **Feature sequence** — ordered features with binary gates (or an unordered cluster list when there is no single endgame)
4. **Spec vs implementation** — honest drift inventory with the owning feature
5. **Current focus** — active feature and next human gate

Do **not** duplicate feature unit tables in the root plan. Do **not** keep a long-horizon backlog.

---

## Feature plan sections

1. **Units** — full `feature/n` unit table (same-feature deps only)
2. **Feature gate** — which upstream feature must be `DONE` before this one starts (one line; references the root sequence)
3. **Spec vs implementation** — feature-scoped gaps
4. **Verification** — evidence per unit
5. **Open questions** — planning blockers only

Template: [templates/feature-plan.md](templates/feature-plan.md)

---

## Frontmatter

**Root plan:**
```yaml
---
type: plan
parent: product.md
children: []   # feature plan paths when registered
updated: YYYY-MM-DD
---
```

**Feature plan:**
```yaml
---
type: feature-plan
feature: <name>
parent: ../../plan.md
updated: YYYY-MM-DD
---
```

List feature plans in root `children:` when you want validate to track them (optional but recommended).

---

## Anti-slop

Plans sequence decisions — they are not implementation dumps.

- **Repo-relative paths only** — link `.spec/features/<name>/plan.md`, not absolute paths.
- **No process exhaust** — no brainstorming, triage notes, or "how we got here" in the plan file.
- **No qualifiers or hedges** — units state what ships; delete "maybe", "TBD unless".
- **No backlog** — every entry is work-ready with a clear dependency, or it lives outside the repo. Delete speculative / long-horizon items.
- **Omit empty sections** — skip placeholder tables and headers with no rows.
- **Decisions, not code** — no code snippets, pseudocode, or pasted API shapes; link to `tech.md`.

---

## Style rules

- Reference specs by link — never paste requirements or architecture inline.
- Prefer tables for units, sequence, and boundaries.
- Keep "Current focus" to 2–3 sentences — it rots fast; bump `updated:` when it changes.
- Open questions belong in the plan that owns the blocker; close them by decision or new unit.

---

## Example (multi-feature repo)

Root `.spec/plan.md` feature sequence:

| Order | Feature | Deliverable | Test | Status | Starts when |
|---:|---|---|---|---|---|
| 1 | spec | `.spec/` + validate + tests | `tests/spec/run.sh` | DONE | — |
| 2 | vibe-flow | `.agents/flow` + `vibe-*` skills | `tests/flow/run.sh` | ACTIVE | spec DONE |
| 3 | agent-instructions | `AGENTS.md` template + merge | `tests/agent-instructions/run.sh` | BLOCKED | vibe-flow DONE |

Feature `vibe-flow/plan.md` unit rows:

| ID | Seq | Summary | Depends | Verification |
|---|---:|---|---|---|
| vibe-flow/1 | 1 | Per-turn orders in vibe-* skills; strip frozen injects | — | `tests/flow/run.sh` |
| vibe-flow/2 | 2 | Skill-count decision | vibe-flow/1 | review note |

This pattern scales: add features, promote sub-features to siblings, extend the sequence — without cross-feature unit locks and without rewriting history.
