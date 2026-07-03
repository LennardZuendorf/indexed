---
type: feature-runbook
feature: architecture-audit
sibling: plan.md
parent: ../../plan.md
updated: 2026-07-03
---

# Architecture Audit — Overnight Subagent Orchestrator

Use with Cursor loop:

```text
/loop 5m @.spec/features/architecture-audit/OVERNIGHT.md
```

Or dynamic pacing (agent self-schedules between units):

```text
/loop @.spec/features/architecture-audit/OVERNIGHT.md
```

---

You are the **orchestrator**, not the implementer. Dispatch fresh subagents per unit; keep your context for coordination, progress tracking, and verify gates.

## Workspace

- **Root:** `/Users/lennard/Development/indexed/.worktrees/chore/review`
- **Branch:** `spec/architecture-audit` (stay on this branch unless blocked)
- **Plan (source of truth):** `.spec/features/architecture-audit/plan.md`
- **Also read on first tick:** `.spec/plan.md`, `.spec/lessons.md`, `.spec/features/architecture-audit/tech.md`, `.spec/features/architecture-audit/product.md`

## Required skills (invoke before acting)

1. `superpowers:using-superpowers` — session start
2. `superpowers:subagent-driven-development` — one implementer subagent + task reviewer per unit
3. `superpowers:verification-before-completion` — before any "done" claim

## Loop behavior (every tick)

1. `cd` to workspace root; run `git status` and `git log -5 --oneline`.
2. Open `.spec/features/architecture-audit/plan.md` → **Progress** table.
3. Find the **first unit** that is `NOT STARTED` or `IN PROGRESS` (order: `/0` → `/1` → … → `/12`).
4. If **all units DONE** and COMPOUND checklist complete → run full verify gate; report success; **stop the loop** (do not arm another wake).
5. If a unit is `IN PROGRESS` from a crashed prior run → assess git diff/tests; resume or revert and restart that unit.
6. Otherwise execute **exactly one unit** this tick using subagent-driven-development (see Per-Unit Protocol).
7. After unit completes: update Progress table in `plan.md` (`DONE`), check off task boxes in that unit section, commit, run unit Verification command from plan.
8. If you just finished `/4`, `/8`, or `/12` → run the **Sprint verify gate** from plan's "Overnight Run Guide".
9. End tick with a 5-line status: last commit, unit done, next unit, blockers, estimated remaining units.

**Do NOT** ask the user for confirmation between units. **Do NOT** expand scope into issue #119 (thin commands / config/cli split). **Do NOT** skip tests or claim green without pasted command output.

## Per-Unit Protocol (subagent-driven)

For unit `architecture-audit/N`:

### A. Dispatch implementer subagent

Use `Task` tool, `subagent_type: generalPurpose` or `cavecrew-builder` for 1–2 file edits only; prefer `generalPurpose` for multi-file units.

**Prompt template:**

```text
Implement architecture-audit/N from the indexed monorepo execution plan.

Workspace: /Users/lennard/Development/indexed/.worktrees/chore/review
Read FIRST: .spec/features/architecture-audit/plan.md section "architecture-audit/N"
Also: .spec/features/architecture-audit/tech.md for architecture contracts
Also: AGENTS.md workflow (ASK→read .spec→PLAN→IMPL→VERIFY — PLAN already approved; skip CONFIRM)

Your job:
1. Implement ONLY unit N — no other units
2. Follow every checkbox and code snippet in the plan for unit N
3. Write/run tests specified in unit Verification block
4. Run unit Verification command; paste real output in your final report
5. Keep touched files within R10 limits (CLI ≤150, service ≤300, module ≤400)
6. Commit: refactor(<scope>): architecture-audit/n <subject>  (≤50 chars, imperative)
7. Do not push unless explicitly told

Return: files changed, test output, commit hash, any blockers
```

Mark unit `IN PROGRESS` in plan Progress table before dispatching.

### B. Dispatch task reviewer subagent

After implementer returns, dispatch readonly reviewer:

```text
Review the architecture-audit/N implementation just committed on branch spec/architecture-audit.
Workspace: /Users/lennard/Development/indexed/.worktrees/chore/review
Compare against: .spec/features/architecture-audit/plan.md unit N acceptance criteria
and .spec/features/architecture-audit/product.md requirements trace for that unit.

Report: SPEC PASS/FAIL, quality issues (Critical/Important/Minor), fix list.

If Critical/Important → dispatch fix subagent → re-review. Only mark `DONE` when reviewer approves.
```

## Unit order & sprint gates

| Sprint | Units | Gate after |
|--------|-------|------------|
| 0a | /0 | — |
| 1 | /1, /2, /3, /4 | Sprint 1 verify (plan) |
| 2 | /5, /6, /7, /8 | Sprint 2 verify (plan) |
| 3 | /9, /10, /11, /12 | Full feature verify + COMPOUND |

## Verify gates (paste output before claiming pass)

**Unit level:** each unit's `Verification:` block in plan.md

**Sprint 1 (after /4):**

```bash
uv run pytest tests/unit/indexed_protocols/ tests/unit/indexed_core/test_import_isolation.py \
  tests/unit/indexed/test_bootstrap.py tests/unit/indexed/test_runtime_context.py \
  tests/system/test_mcp_storage_parity.py -q
uv run mypy src/
```

**Sprint 2 (after /8):**

```bash
uv run pytest tests/unit/indexed_config/ tests/unit/utils/test_retry.py \
  tests/unit/indexed_connectors/test_http_retry.py -q
uv run pytest -q --cov=src
```

**Feature complete (after /12 + COMPOUND):**

```bash
uv run ruff check . --fix && uv run ruff format
uv run mypy src/
uv run python scripts/check_import_graph.py
uv run pytest -q --cov=src
bash .agents/skills/spec/scripts/validate.sh
```

## COMPOUND (after /12 green)

- [ ] Promote rules to `.spec/tech.md`
- [ ] Mark Feature 11 DONE in `.spec/plan.md`
- [ ] Append learnings to `.spec/lessons.md`
- [ ] Bump `updated:` on edited specs
- [ ] Commit: `docs(spec): architecture-audit compound`

## Stop conditions

**Stop the loop when:**

- All `/0`–`/12` are DONE AND full feature verify gate is green AND COMPOUND committed

**Pause and report (do not spin forever) when:**

- Same unit fails 3 times
- Verify gate fails and fix requires human decision (scope/architecture)
- git merge conflict or dirty state you cannot resolve

## Pre-flight (first tick only)

```bash
cd /Users/lennard/Development/indexed/.worktrees/chore/review
uv sync --all-groups
uv run pytest -q --co 2>/dev/null | tail -3
git status
```

Then start with `architecture-audit/0` if NOT STARTED, else first incomplete unit.

## Critical reminders from audit

- `/8`: migrate Jira Server to `UnifiedJiraDocumentReader` **before** deleting wrapper files
- `/4`: delete `resolve_preferred_collections_path`; wire MCP `collections_path`; fix hardcoded `localFiles`
- `/2`: zero `from connectors` in `packages/indexed-core/` (CI enforces in /12)
- `/6`: fix `ConfigService.instance()` to honor `mode_override` on subsequent calls
- Commit `uv.lock` when deps change in `/1`

Execute now. Begin with the first incomplete unit.

---

## Tips for a successful overnight run

1. Use dynamic `/loop` if your agent supports it — it can start the next unit immediately after `/0` or `/1` instead of waiting 45 minutes.
2. Leave the worktree clean before starting — stash or commit anything unrelated.
3. Morning check: `git log --oneline` should show commits architecture-audit/0 … /12; Progress table should be all DONE.
4. Stop manually if needed: ask the agent to kill the loop PID it armed.
