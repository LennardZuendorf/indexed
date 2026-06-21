# Feature layer — ephemeral per-feature specs

Each **named** unit of work gets `.spec/features/<name>/`. Specs here are **branch-scoped**: created in DESIGN, read in IMPL, wrapped up in COMPOUND (promote cross-cutting decisions, move folder to `archive/`), then **deleted before the branch merges**. Archive is a transient safety net, never a store for active work — **CODE IS TRUTH**. Global, long-living rules stay in root files — see [strategy.md](strategy.md). Wrap-up procedure: [SKILL.md](SKILL.md) § Wrapped-up features.

## Feature authoring flow

Six-step interview micro-flow. Run steps 1–5 for every named feature; step 6 is the escape hatch.

### 1. Locate & name

Confirm the feature name with the user. Read root `.spec/product.md`, `.spec/tech.md`, and `.spec/lessons.md` before writing anything. Create `.spec/features/<name>/` when the name is settled.

### 2. Interview for WHAT

Dialogue — not a form fill. Cover:

- **Problem / why** — one paragraph; push back on vague goals
- **Scope** — Owns / Does not own / Deferred table; explicit boundaries vs neighbour features
- **Requirements** — `### Requirement: <title>` with SHALL/MUST language; each requirement gets `#### Scenario:` blocks in Given/When/Then form

Reject hand-wavy requirements. If the user cannot state observable behaviour, keep interviewing.

Write to `product.md`. Use [reference/product.md](reference/product.md) § feature product. Omit empty sections.

### 3. Rigor gate

Choose **lite** (product + tech + plan) vs **full** (+ `design.md`):

| Need `design.md` when… | Skip when… |
|---|---|
| UI layout, interaction flows, visual language | Pure backend / script / config |
| API or data contract needs a human-readable spec | Contracts fit in `tech.md` alone |
| Migration or rollout has UX-facing steps | No user-visible surface |

If unsure, default lite. Do not create `design.md` "just in case."

### 4. Sketch HOW

Trace the codebase (existing files, contracts, KTDs). Write **only sections with content** to `tech.md` — paths, interfaces, file layout, risks. No speculative boilerplate.

Delegate tracing to `code-explorer`; sketch approaches with `code-architect` when needed. Use [reference/tech.md](reference/tech.md) § feature tech.

Optional: write `design.md` when step 3 chose full. Template: [reference/templates/feature-design.md](reference/templates/feature-design.md). Guide: [reference/design.md](reference/design.md); token format: [SKILL.md](SKILL.md) § Design.md Compatibility.

### 5. Plan units

Write `plan.md` with stable `feature/n` unit IDs (`### <name>/1`, `### <name>/2`, … per [reference/plan.md](reference/plan.md)):

- Each unit cites requirement IDs from `product.md`
- Each unit names test scenarios and verification evidence (command, test path, behaviour check)
- Same-feature dependencies only — cross-feature order is a whole-feature gate in root `.spec/plan.md` Feature Sequence
- Add the feature to the root `.spec/plan.md` Feature Sequence

**Human gate:** confirm units before implementation.

### 6. Skip conditions

Route to `vibe-quick` instead of this flow when **all** hold:

- Atomic change — one file or one bounded fix
- No architectural decisions
- No new requirements needing Scope negotiation

If any condition fails, stay in the feature flow.

---

## Examples in this repo

- [.spec/features/vibe-flow/](../../../.spec/features/vibe-flow) — flow state machine, `vibe-*` skills (units `vibe-flow/n`)
- [`.agents/skills/spec/`](../../) — spec framework (units `spec/n`, delivered — wrapped up; no feature folder)
- [.spec/features/agent-instructions/](../../../.spec/features/agent-instructions) — `AGENTS.md` template and adapter symlinks (units `agent-instructions/n`)
- [.spec/features/platform-adapters/](../../../.spec/features/platform-adapters) — Codex / Claude Code adapters (units `platform-adapters/n`)

## Anatomy of `features/<name>/`

| File | Required | Purpose |
|---|---|---|
| `product.md` | yes | What this feature does (requirements, UX) |
| `tech.md` | yes | How it is built (paths, contracts, implementation) |
| `design.md` | optional | UI/UX or design-system fragment for this feature |
| `plan.md` | recommended | Stable unit IDs, dependencies, verification — see [reference/plan.md](reference/plan.md) |
| `research.md` | optional | Discovery artifacts |

**Frontmatter** (shape — adjust paths to your tree):

```yaml
---
type: feature-product   # or feature-tech
feature: <name>
sibling: tech.md          # or product.md
parent: ../../product.md # or ../../tech.md
updated: YYYY-MM-DD
---
```

Full conventions: [reference/product.md](reference/product.md) § feature product, [reference/tech.md](reference/tech.md) § feature tech.

## Lifecycle

```
Created  →  Consumed  →  Merged  →  Archived  →  Deleted (before merge)
   ↑           ↑           ↑           ↑              ↑
 DESIGN      IMPL       COMPOUND    COMPOUND       after validation
 phase       phase      phase       phase          (agent prompts)
```

1. **Created during DESIGN.** Steps 1–4 of the authoring flow → `product.md`, `tech.md`, optional `design.md`.
2. **Planned before IMPL.** Step 5 → `plan.md` with stable IDs; human gate on units.
3. **Consumed during IMPL.** Read feature specs; cite unit IDs in commits and tests; amend with targeted fixes if reality diverges.
4. **Verified against plan.** Evidence checked per unit verification table — not agent assertions alone.
5. **Merged during COMPOUND.** Cross-cutting blocks from `features/<name>/tech.md` promote into root `tech.md` (or branch docs). Feature-only detail does not promote.
6. **Archived then deleted.** Move `.spec/features/<name>/` to `archive/<name>/` at wrapup as a transient safety net. After validation passes, the agent prompts the user to delete the archive — the folder is gone **before the branch merges**. CODE IS TRUTH; archive is never read for active work. See § Archive and delete.

No `/code:feature` workflow? Same lifecycle: create folder when scoping, remove when done.

## Marking content for promotion (tech)

Wrap **cross-cutting** sections so COMPOUND tooling (e.g. `bin/merge-feature.sh` in your project) can promote them into root `tech.md`:

```markdown
<!-- merge -->
## Single routing contract
All `vibe-*` workflow skills and adapters call the same flow reader — one JSON shape everywhere.
<!-- /merge -->
```

Feature-only sections (one file's line count, one hook's exit code table) stay **outside** merge markers — they are discarded at wrap-up unless you archive the folder.

Details: [reference/tech.md](reference/tech.md) (merge markers, feature `tech.md` sections).

## What stays vs what graduates

| Stays in feature folder (discarded or archived) | Graduates to root / branch |
|---|---|
| Per-hook matcher strings, per-command LOC estimates | "Every hook delegates to keystone" |
| Feature file list for this build | Global file layout diagram |
| One feature's user-visible copy | Reusable design principles in root `product.md` |

If everything you wrote applies to **every** future feature, that content belongs in [strategy.md](strategy.md) / root branch docs — move it up, don't bury it in a feature folder. Canonical two-layer rules: [SKILL.md](SKILL.md) § The Two-Layer Model.

## Archive and delete

After promote, move `.spec/features/<name>/` to `archive/<name>/`. Archive is a **transient safety net** — useful if CI fails right after wrapup and the feature context is briefly needed. It is **never** a store for active work, and never read while building — **CODE IS TRUTH**.

Once validation passes, the agent **prompts the user to delete the archive**, and the folder is gone **before the branch merges**. Keeping an archive past the branch is the exception, not the default; justify it (rejected alternatives, plan archaeology worth standalone history) or delete it.

**Delete checklist:** root `plan.md` Feature Sequence row → DONE with live-surface link; no links pointing at `features/<name>/` or `archive/<name>/`; do not restore the folder if validation complains — wrapped-up features are expected to be absent from `features/`.

Canonical wrap-up sequence: [SKILL.md](SKILL.md) § Wrapped-up features.

## Templates and validation

- Feature templates: [feature-product](reference/templates/feature-product.md), [feature-tech](reference/templates/feature-tech.md), [feature-plan](reference/templates/feature-plan.md), optional [feature-design](reference/templates/feature-design.md)
- Writing guides: [product](reference/product.md), [tech](reference/tech.md), [plan](reference/plan.md), [design](reference/design.md)

Global layer handoff: [strategy.md](strategy.md).
