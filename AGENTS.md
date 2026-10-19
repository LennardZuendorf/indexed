# AGENTS.md — indexed Engineering Guide

**indexed** · Python 3.11+ single-package project (`uv`, one wheel `indexed-sh`) ·
local-first semantic search over files/Jira/Confluence/Outline, served by a Typer **CLI**
and a FastMCP
**server**. This is the operating contract for any agent in this repo. The design
source of truth is `.spec/`; earned lessons are in `.spec/lessons.md` — read both at
session start.

## Context

Four layers, top calls down only: **CLI/MCP** (`indexed.cli` / `indexed.mcp`) →
**Services + core facade** (`indexed.core`) → **Engine** (FAISS, embeddings,
persistence) → **Infra** (config, connectors, parsing, utils, protocols).

```
src/indexed/           the single package (one wheel: indexed-sh)
  core/                engine facade + services + indexes
  connectors/          files/jira/confluence/outline readers + converters
  config/              ConfigService (singleton) + TOML/.env resolution + config CLI
  parsing/             Docling / tree-sitter chunking
  protocols/           typed contracts (models.py) + protocols — the leaf
  utils/               logging · retry · batching
  cli/                 Typer app · composition.py (the single wiring site)
  mcp/                 FastMCP server
tests/                 unit/ · system/ · characterization/ · benchmarks/
.spec/                 design source of truth (root specs + features/<name>/)
```

Config priority (low→high): defaults → `~/.indexed/config.toml` →
`./.indexed/config.toml` → `INDEXED__*` env → CLI args. Secrets in `.env`, never TOML.
Collections persist under `~/.indexed/data/collections/<name>/`
(`manifest.json`/`documents.json`/`chunks.json`/`index.faiss`).

```bash
uv sync --all-groups
uv run indexed index create my-docs --source files --source-path ./docs
uv run indexed index search "query" --collection my-docs
uv run indexed-mcp run
```

## Rules

**MUST** — run the full Workflow cycle; read `.spec/` before coding and cite it; run
everything via `uv run` from the PROJECT ROOT; keep ty clean (0 diagnostics) and
ruff clean; hold coverage >85% and run the full suite before any push; commit
`uv.lock` with dependency changes; keep the four module edges (`core ↛ connectors`,
`connectors ↛ core`, and `config`/`utils`/`parsing`/`protocols` never import up); route
config through `ConfigService`; lazy-load heavy ML imports inside functions; bump
`updated:` on every spec you touch and COMPOUND lessons in the same cycle.

**NEVER** — use `pip`/`poetry` or activate a venv; proceed past a gate without
confirmation; skip tests/coverage/types before pushing; import heavy ML libs at module
top; hardcode config values; create a file when editing one works; exceed 50 chars in a
commit subject or add a body/footer; leave a spec drifting from the code; over-comment.

**Commit** (only when asked; one line, ≤50 chars, imperative):
`<type>(<scope>): <subject>` — feat/fix/refactor/perf/style/test/docs/build/ci/chore.

## Learnings

Earned defaults live in **`.spec/lessons.md`** — read at session start, apply without
being asked, and add a lesson after every correction. Load-bearing highlights: lazy ML
imports keep startup <1s; ty must be fully clean tree-wide (0 diagnostics, no baseline);
coverage is measured on installed packages (`--cov=src`); `ConfigService` is a singleton
(respect the priority chain); connectors are Protocol-based with `from_manifest`; core is
consumed only through the `core.v1.engine` facade, with `composition.py` the single wiring
site; FAISS Flat is correct for <100k docs; spec drift is the main failure mode — fix the
spec in the same cycle; a comment is one line of *why*, never an essay; Rich silently drops
a bracketed `[dotted.key]` from any `typer.Option(help=...)` string (parsed as a markup
tag, not printed) — write config keys unbracketed in help text. Dependency
lock reconciliation can leave metadata stale after temporary resolver
constraints are removed; run `uv lock` against the final `pyproject.toml`.
KISS wins.

Agent skills are **not vendored** — they install from `skills-lock.json` via `npx skills`
(`npx skills list` shows the set). The root `CLAUDE.md`/`WARP.md` are symlinks to this
file (multi-tool compatibility).

<!-- vibe:instructions:start -->
<!-- Managed by vibe (merge-agents.sh). Edits inside these markers are
     replaced on the next setup.apply / install. Content outside the markers
     (above this line, or inside vibe:active-rules) is user-owned. -->

This project runs the **vibe flow** — a spec-first workflow harness. `.spec/` is the
durable memory; sessions are ephemeral. Read the specs before you write code.

## Session start

1. Read `.spec/lessons.md` and `.spec/plan.md`. (The spec half owns `.spec/`; a
   flow-only install has no tree — the flow still runs, the specs are just absent.)
2. Identify the feature you are working on and load its specs:
   `.spec/features/<name>/{product,tech,plan}.md`.
3. If `.agents/skills/vibe/state.json` exists and you are continuing a flow session,
   read `{flow, phase, feature}` and resume the linked `vibe` skill. A missing cursor
   means `idle` — proceed with the specs; a missing cursor is not an error.

## Driving the flow

- `/flow <flow.phase> [feature] [confirm]` transitions the state machine. Pass the feature
  name to carry it into the cursor; add the literal `confirm` token to cross a gated edge
  (the two human gates below). Never edit `state.json` by hand.
- Under the hood `/flow` runs
  `bash .agents/skills/vibe/scripts/set-state.sh <flow.phase> [feature]`. That script is a
  *writer*, not a gate — it moves the cursor but enforces no approval. The gate teeth live
  in the `/flow` command and the hooks, not the writer.
- Per-turn **orders** for the current state come from the linked `vibe` skill, resolved by
  `orders.sh`. Follow the current state's orders over any delegated skill's own prose.

## Working model

```
ASK → read .spec/ → PLAN → CONFIRM → IMPL → verify → compound
```

Most transitions auto-advance. Two edges are **human gates** — stop and get explicit
approval before crossing: plan → impl, and verify → ship. Everything else flows without
pausing to ask.

**Output: brief technical English** — answer first, then the detail. One idea per
sentence, active voice, no filler or hedging; compress receipts and subagent
summaries. Never compress security warnings, irreversible-action confirmations, or
code/paths/commands — those stay full and byte-exact.

## Write policy

Which paths this harness restricts, and in which states, is **data**:
`content/policy.json`, read by `detect-context.sh decide` (which defaults to `idle`
when `state.json` is absent). The rules are rendered rule-by-rule into the
`vibe:rules` block below — this section states no state list of its own, because a
second hand-written copy is a copy that can disagree with the enforcer. Check any
path before writing it:

```bash
bash .agents/skills/vibe/scripts/detect-context.sh decide <path>
```

## Precedence

The cursor owns sequencing and artifact destinations; delegated skills own method. When a
delegated skill's text names its own artifact path or hands off elsewhere, the current
state's orders win: write to the state's surface, transition only via `set-state.sh`. Scope
edits are not a state — edit within the current state's write surface and stay put.
`set-state.sh idle` is always legal: abort ends any flow.

## Injected rules

Standing rules are authored as content blocks and composed into channels: the
per-turn prompt, session start, and the `vibe:rules` block below. Configure them in
this repo's root `vibe.json` — add, remove, reorder, disable, or define your own —
never by editing the block, which is regenerated.

## Commands

```bash
# Spec validation — run before claiming done (spec half; absent on --only flow)
bash .agents/skills/spec/scripts/validate.sh
# Write policy for a path (works without state.json)
bash .agents/skills/vibe/scripts/detect-context.sh decide <path>
# Health-check the harness wiring (hooks, cursor, machine)
bash .agents/skills/vibe/scripts/doctor.sh
# Injection config: what each channel composes, and lint it
node .agents/skills/vibe/engine/cli.mjs render --list
node .agents/skills/vibe/engine/cli.mjs render --check
# Re-render the AGENTS.md rules block after editing vibe.json
node .agents/skills/vibe/engine/cli.mjs render agents-md --write
```

## Enforcement is partial — do not trust it blindly

- The `pre-tool-use-guard` hook only intercepts `Edit`, `Write`, and `NotebookEdit` tool
  calls. Shell redirection (`>`, `tee`, `sed -i`) bypasses it — honoring the write
  invariants there is a **convention**, backed only by a warn-only Bash sniffer.
- `set-state.sh` writes the cursor; it does not gate. Approvals are enforced by `/flow` and
  the hooks, not by the writer.
- The Stop receipt tooth (a `*.verify` state needs a fresh evidence receipt) fires only when
  the hooks are wired into the platform (e.g. `.claude/settings.json`). No wiring, no tooth.

## Degrade

Scripts graceful-degrade: `jq` is recommended but optional (a pure-bash path keeps the
cursor byte-identical), and other agents may edit concurrently — touch only your own files
and prefer warn over hard-fail.
<!-- vibe:instructions:end -->

<!-- vibe:rules -->
_Managed by vibe — rendered from the `agents-md` channel by `vibe render agents-md --write`. Edit the blocks or `vibe.json`, not this region._

## Write invariants

Every write this harness restricts is one rule in `content/policy.json`. The
list below is RENDERED from that file — the same data
`detect-context.sh decide` enforces — so the prose and the enforcer cannot
disagree. Edit the rules, never this text.

- `.agents/skills/vibe/state.json` — otherwise: block — state.json is written only via set-state.sh, never by direct edit
- `.spec/lessons.md` — `feature.compound`, `setup.apply`, `strategy.spec`, `quick.verify`: allow; otherwise: block — .spec/lessons.md is writable only during feature.compound, setup.apply, strategy.spec, or quick.verify (current: the current state)
- `.spec/product.md`, `.spec/tech.md`, `.spec/design.md`, `.spec/plan.md` — `strategy.spec`, `feature.compound`, `setup.apply`: allow; otherwise: block — root .spec specs are writable only during strategy.spec, feature.compound, or setup.apply (current: the current state)
- `.spec/features/*` — `feature.impl`, `quick.fix`: warn — .spec/features edits are frozen during impl/fix — route back to feature.design/plan to change scope (current: the current state); otherwise: allow
- `CLAUDE.md`, `AGENTS.md` — otherwise: warn — CLAUDE.md/AGENTS.md active-rules block is generated by regen-active-rules.sh; edits inside the markers are overwritten next compound
- `src/*`, `tests/*` — `feature.verify`: warn — verify writes no src — route findings back to impl (set-state.sh feature.impl); `quick.verify`: warn — verify writes no src — route findings back to fix (set-state.sh quick.fix); `feature.impl`, `quick.fix`, `setup.apply`: allow; otherwise: warn — source/test edits outside an impl/fix state (current: the current state)

Check a path before writing it:

```bash
bash .agents/skills/vibe/scripts/detect-context.sh decide <path>
```

## Delegating to sub-agents

Model tiers for ANY delegated work — Agent-tool calls and Workflow-script `agent()`
calls alike. Set the `model` parameter explicitly on every call; never omit it
(omission silently inherits the session model):

- `haiku` — mechanical bulk work: renames, boilerplate, format conversion, log triage.
- `sonnet` — default for well-specified implementation with clear acceptance criteria.
- `opus` — genuinely tricky work: concurrency, subtle algorithms, adversarial
  verify/judge panels, gnarly debugging.
- `fable` — rare; only when independence from your context is the point (e.g.
  adversarial review of your own plan or a large diff). If the complexity of the task
  warrants a Fable sub-agent, ALWAYS check with me first — never spawn one unprompted.

When unsure between tiers, pick the cheaper and escalate on failure.

## Dynamic workflows (Workflow tool)

Applies to ALL sessions, any model. Dynamic workflows do not need to be avoided —
reach for the Workflow tool when a task has 3+ independent parallelizable subtasks or
would benefit from a pipeline/judge panel.

Standing rule on opt-in: if ultracode is NOT on for the session (no "ultracode"
keyword, no toggle, no orchestration request in my own words), plan first — propose
the workflow in one or two sentences with the rough shape and cost, and wait for my
reply; my "yes" is the opt-in. If ultracode IS on, invoke directly.

**Agent models inside workflow scripts:** every `agent()` call MUST set the `model`
parameter explicitly, chosen per "Delegating to sub-agents" above — with one
tightening: NEVER use `fable` agents in a dynamic workflow, not even with approval.
Only `haiku`, `sonnet`, or `opus`. If a Fable review is warranted, it happens AFTER
the workflow completes, as a standalone Agent-tool call (ask first, per above) —
never as a workflow stage.
<!-- /vibe:rules -->
