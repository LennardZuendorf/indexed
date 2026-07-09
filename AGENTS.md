# AGENTS.md — indexed Engineering Guide

**indexed** · Python 3.11+ monorepo (`uv` workspace + `una`) · local-first semantic
search over files/Jira/Confluence/Outline, served by a Typer **CLI** and a FastMCP
**server**. This is the operating contract for any agent in this repo. The design
source of truth is `.spec/`; earned lessons are in `.spec/lessons.md` — read both at
session start.

## Workflow

Run this cycle per unit of work; each phase is a gate you may not skip:

```
ASK → read .spec/ → PLAN → CONFIRM → IMPL → VERIFY → COMPOUND
```

- **ASK / PLAN / CONFIRM** — clarify scope, cite the specs you read, get explicit
  approval before writing code. Scale ceremony to risk: a one-line fix skips PLAN.
- **IMPL** — edit existing files over new ones; test-first where the spec says so.
- **VERIFY** — run the full gate below and show real output. No output, no claim.
- **COMPOUND** — fold changes back into `.spec/` + `.spec/lessons.md`. A change that
  outdates a doc isn't done until the doc is fixed.

Delegate research and multi-file exploration to subagents to keep context clean.

### Verify gate (from PROJECT ROOT, all must pass)

```bash
uv run ruff check . --fix && uv run ruff format
uv run mypy apps/indexed/src packages/*/src   # 0-NEW on touched files (baseline ~220)
uv run pytest -q --cov=src                     # full suite, >85% coverage
python scripts/check_import_graph.py           # module-edge gate
bash .agents/skills/spec/scripts/validate.sh   # only if .spec/ was touched → 0 errors
```

## Context

Four layers, top calls down only: **CLI/MCP** (`apps/indexed`) → **Services + core
facade** (`core.v1.engine`) → **Engine** (FAISS, embeddings, persistence) → **Infra**
(config, connectors, parsing, utils, protocols).

```
apps/indexed/src/indexed/     cli · mcp · composition.py (the single wiring site)
packages/
  indexed-core/               engine facade (core.v1.engine) + services + indexes
  indexed-connectors/         files/jira/confluence/outline readers + converters
  indexed-config/             ConfigService (singleton) + TOML/.env resolution
  indexed-parsing/            Docling / tree-sitter chunking
  indexed-protocols/          typed contracts (models.py) + protocols — the leaf
  utils/                      logging · retry · batching
tests/                        unit/ · system/ · characterization/ · benchmarks/
.spec/                        design source of truth (root specs + features/<name>/)
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
everything via `uv run` from the PROJECT ROOT; keep mypy 0-new on touched files and
ruff clean; hold coverage >85% and run the full suite before any push; commit
`uv.lock` with dependency changes; keep the four module edges (`core ↛ connectors`,
`connectors ↛ core`, and `config`/`utils`/`parsing`/`protocols` never import up); route
config through `ConfigService`; lazy-load heavy ML imports inside functions; bump
`updated:` on every spec you touch and COMPOUND lessons in the same cycle.

**NEVER** — use `pip`/`poetry` or activate a venv; proceed past a gate without
confirmation; skip tests/coverage/types before pushing; import heavy ML libs at module
top; hardcode config values; create a file when editing one works; exceed 50 chars in a
commit subject or add a body/footer; leave a spec drifting from the code.

**Commit** (only when asked; one line, ≤50 chars, imperative):
`<type>(<scope>): <subject>` — feat/fix/refactor/perf/style/test/docs/build/ci/chore.

## Learnings

Earned defaults live in **`.spec/lessons.md`** — read at session start, apply without
being asked, and add a lesson after every correction. Load-bearing highlights: lazy ML
imports keep startup <1s; mypy is 0-new not tree-wide (baseline carries ~220); coverage
is measured on installed packages (`--cov=src`); `ConfigService` is a singleton (respect
the priority chain); connectors are Protocol-based with `from_manifest`; core is consumed
only through the `core.v1.engine` facade, with `composition.py` the single wiring site;
FAISS Flat is correct for <100k docs; spec drift is the main failure mode — fix the spec
in the same cycle. KISS wins.

Agent skills are **not vendored** — they install from `skills-lock.json` via `npx skills`
(`npx skills list` shows the set). The root `CLAUDE.md`/`WARP.md` are symlinks to this
file (multi-tool compatibility).
