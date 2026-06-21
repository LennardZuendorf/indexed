# AGENTS.md — indexed Engineering Guide

**Repository:** indexed v0.1.0 · Python monorepo (uv + una)
**Last Updated:** 2026-06-21

This is the operating contract for any agent working in this repo. Read it
fully before acting. The four sections are load-bearing:

- **[Workflow](#workflow)** — the cycle you MUST run in. Non-negotiable.
- **[Context](#context)** — what the system is and how it is built.
- **[Rules](#rules)** — hard constraints. Violating these breaks the repo.
- **[Learnings](#learnings)** — earned best practices. Apply them by default.

---

## Workflow

**You operate in a strict, repeating cycle. Do not skip steps. Do not write
code outside it.**

```
ASK → read .spec/ → PLAN → CONFIRM → IMPL → VERIFY → COMPOUND
└──────────────────────── repeat per unit of work ───────────────────────┘
```

Each phase is a gate. You may not advance until the current gate is satisfied.

| Phase | You MUST | Gate to pass |
|-------|----------|--------------|
| **ASK** | Clarify requirements. Surface assumptions. Ask, don't guess. | Scope is unambiguous. |
| **read .spec/** | Beyond the session-start orientation read, load the **scope-specific** specs for this task — the relevant `tech-*.md` + the feature spec. | You can cite what you read. |
| **PLAN** | Break work into testable units. Cite spec/unit IDs. Present approach + reasoning. | A written plan exists. |
| **CONFIRM** | Get **explicit** user approval of the plan. | User said go. |
| **IMPL** | Implement step-by-step. Test-first where specified. Edit existing files over creating new ones. | Code matches the approved plan. |
| **VERIFY** | Run the full quality gate (below). Show real output. Never claim success without evidence. | All gates green. |
| **COMPOUND** | Fold learnings and tech changes back in: `.spec/` + `lessons.md` + the affected `AGENTS.md`. Promote/clean feature specs. | Docs reflect reality. |

**Scale the gate to the task.** A one-sentence diff (typo, log line, rename)
skips PLAN/CONFIRM — just fix it and VERIFY. Plan when the approach is
uncertain, the change spans files, or architecture is in play. Don't
over-ceremony trivial work; don't under-plan risky work.

**Delegate to subagents.** Offload research, codebase exploration, and parallel
analysis to subagents — they keep the main context clean and report back
findings. Reach for them on anything that reads many files. One focused task
per subagent.

### Session start (every session, in order)

1. Read `.spec/plan.md` and `.spec/lessons.md`.
2. Identify the feature/task in scope and load its specs.
3. Route by intent (table below). Then enter the cycle at **ASK**.

### Routing by intent

| Intent | Load first | Tool |
|--------|-----------|------|
| Understand the project | `.spec/product.md`, `.spec/tech.md` | — |
| Build a named feature | `.spec/features/<name>/` + root `plan.md` | `feature-dev` skill |
| Small bounded fix | relevant feature/`tech-*` spec | direct, minimal |
| Spec / design work | `.spec/**` | `/spec` skill |
| Debug a failure | reproduce first | `systematic-debugging` skill |

### Verify gate (run from PROJECT ROOT, all must pass)

```bash
uv run ruff check . --fix && uv run ruff format   # lint + format
uv run mypy src/                                   # strict types, 0 errors
uv run pytest -q --cov=src                         # full suite, >85% coverage
bash .agents/skills/spec/scripts/validate.sh       # if .spec/ was touched → 0 errors
```

**Evidence before assertions, always.** "Done", "fixed", and "passing" are
claims that require pasted command output. No output, no claim.

### Commit (only when asked; one line, ≤50 chars, imperative)

```
<type>(<scope>): <subject>      # feat fix refactor perf style test docs build ci chore revert
```

Run the full suite before any push — monorepo integrity is critical.

---

## Context

### What indexed is

A local-first semantic search engine over your documents (files, Jira,
Confluence). It chunks and embeds documents into a FAISS vector index, then
serves search via a Typer **CLI** and a **FastMCP** server that exposes
collections to AI agents.

### Stack

Python 3.11+ · `uv` 0.5+ (workspace) · `una` (wheel bundling) · FAISS ·
sentence-transformers · Typer 0.15 · FastMCP · Pydantic 2.10.
Tooling: ruff 0.9 (lint+format) · mypy 1.14 (strict) · pytest 8.3 + pytest-cov.

### Layout — where to find what

```
apps/indexed/src/indexed/
  cli/                 CLI commands (Typer)            entry: main.py
  mcp/                 FastMCP server implementation
packages/
  indexed-core/src/core/
    indexing/          FAISS indexer + collection creator + disk persister
    search/            SearchService (query → embed → FAISS → format)
    models/            domain models (documents, chunks, manifests)
  indexed-connectors/src/connectors/
    jira/ confluence/ files/   source adapters (BaseConnector protocol)
  indexed-config/src/indexed_config/
    service.py         ConfigService (singleton)
    models.py          Pydantic config models
  indexed-parsing/     document parsing/chunking
  utils/src/utils/     logging.py · retry.py · batching.py
tests/                 unit/ (mirrors packages) · system/ (integration) · benchmarks/
.spec/                 design source of truth (see below)
pyproject.toml         workspace root · uv.lock (ALWAYS commit)
```

### Architecture (4 layers, top calls down only)

`CLI/MCP (apps/indexed)` → `Service (core: orchestration, factories)` →
`Engine (core: FAISS, embeddings, persistence)` → `Infra (config, connectors, utils)`.

- **Index pipeline:** Config → Connector (read → convert/chunk) → CollectionCreator (embed → FaissIndexer → DiskPersister).
- **Search pipeline:** `SearchService.search(query, collections)` → per-collection load cached searcher → embed query → FAISS search → map to chunks → format (json/table/cards).

### Configuration (increasing priority)

Pydantic defaults → `~/.indexed/config.toml` → `./.indexed/config.toml` →
env `INDEXED__section__key=value` → CLI args. Secrets live in `.env`, never in
TOML. Collections persist under `~/.indexed/data/collections/<name>/`
(`manifest.json`, `documents.json`, `chunks.json`, `index.faiss`); local mode
uses `./.indexed/`.

### `.spec/` — design source of truth

Two layers: **root** (`product.md`, `tech.md`, `plan.md` + `tech-<component>.md`
per package: app/core/config/connectors/parsing) stays high-level with no
backlog; **feature** (`features/<name>/`) is branch-scoped, promoted to root on
completion, then deleted before merge. **Code is truth** — specs describe
intent, not a second copy of the code. `docs/` holds only the logo, not docs.

### Essential commands

```bash
uv sync --all-groups                      # install everything
uv run indexed --help                     # CLI
uv run indexed index create my-docs --source files --source-path ./docs
uv run indexed index search "query" --collection my-docs
uv run indexed-mcp run                     # MCP server (stdio); --transport http --port 8000
HATCH_BUILD_HOOKS_ENABLE=1 uvx --from build pyproject-build --installer=uv --outdir=dist --wheel apps/indexed
```

### Skills & plugins

`feature-dev` (plugin) for multi-file features; `/spec` for spec work; plus the
superpowers skills for the matching phase — `brainstorming`,
`systematic-debugging`, `test-driven-development`, `writing-plans`,
`writing-skills`, `verification-before-completion`, and more. Full set:
`npx skills list` (installed via `skills-lock.json`).

---

## Rules

**MUST**

- Run the full **Workflow cycle**; never write code without an approved plan/spec.
- Read `.spec/` before writing code, and cite what you read.
- Run every command with `uv run`, from the **PROJECT ROOT**.
- Keep mypy strict at **0 errors** and ruff clean on every commit.
- Hold test coverage **>85%**; run the **full** suite before any push.
- Keep commands thin: branch on business rules → extract to a service. File-size
  limits (CLI ≤150 / service ≤300 / module ≤400) live in `.spec/tech.md`.
- Commit `uv.lock` with dependency changes.
- Bump `updated:` on every spec you touch; keep parent↔child cross-refs alive.
- **Compound** every earned learning and tech adjustment back into these files in
  the same cycle: lessons → root `AGENTS.md` (Learnings) + `.spec/lessons.md`;
  architecture/structure changes → the affected package `AGENTS.md` + its
  `.spec/tech-*.md`. A change that outdates a doc isn't done until the doc is updated.
- Lazy-load heavy ML imports (sentence-transformers/torch) inside functions.

**NEVER**

- Use `pip`/`pipenv`/`poetry`, activate venvs manually, or run `una sync`.
- Proceed past a gate without user confirmation.
- Skip tests, coverage, or type checks before pushing.
- Import heavy ML libraries at module top level.
- Hardcode config values — go through `ConfigService`.
- Create files when editing an existing one works.
- Exceed 50 chars in a commit subject, or add a body/footer.
- Put specs in `docs/`, or leave a feature spec behind after merge.
- Let an `AGENTS.md` or spec drift from the code — never ship a change that
  outdates a doc without updating it in the same cycle.

### Run & test patterns

Everything runs through `uv run` from the project root.

```bash
# Run
uv run pytest -q                              # full suite (quiet)
uv run pytest -v                              # verbose
uv run pytest tests/unit/indexed_core/ -q     # one package
uv run pytest -q -k search                    # by keyword
uv run pytest -q --cov=src --cov-report=html  # coverage report
uv run pytest tests/benchmarks/ --benchmark-only   # benchmarks only

# Quality (must be clean before any push)
uv run ruff check . --fix && uv run ruff format
uv run mypy src/
```

- **Tests mirror packages.** Put a test under `tests/unit/<package>/`; shared
  fixtures live in `tests/conftest.py`. `system/` is integration, `benchmarks/`
  is performance.
- **Use `tmp_path`** for any filesystem/collection state — never write to real
  `~/.indexed/`. Build collections via `DocumentCollectionCreator(storage_path=tmp_path)`.
- **Test-first** where the feature spec says so; cover the new branch, not just
  the happy path. Keep the suite **>85%**.
- **Mock the network, not the engine** — stub connectors (Jira/Confluence) at
  the `read_documents` boundary; let FAISS/embeddings run on small fixtures.

---

## Learnings

Earned defaults — apply without being asked.

- **Lazy loading is why startup is <1s.** PyTorch/Transformers cost 500ms+ at
  import. Load them inside `get_embedder()`-style functions, never at module top.
- **Coverage is measured on installed packages**, not source paths — run from
  root with `--cov=src` so the monorepo packages resolve correctly.
- **Config is a singleton.** `ConfigService.get_instance()` — don't re-parse or
  thread config manually; respect the priority chain (CLI > env > workspace > global > defaults).
- **Connectors are Protocol-based.** New sources implement `BaseConnector`
  (`read_documents` / `convert_documents`); keep reader and converter separate.
- **FAISS Flat index is correct for <100k docs.** Batch embeddings (default 32);
  cache searchers for repeat queries; persist to disk after creation.
- **Spec drift is the main failure mode.** When a decision changes mid-work,
  update the spec in the same cycle (COMPOUND) — a stale spec is worse than none.
- **Correction → lesson.** After any user correction, record the pattern in
  `.spec/lessons.md` so the same mistake never repeats. Review it at session start.
- **KISS wins.** Prefer the simple, readable solution that matches surrounding
  code over a clever one. Quality over speed.

---

**Remember:** ASK → read `.spec/` → PLAN → CONFIRM → IMPL → VERIFY → COMPOUND.
Run the cycle. Show evidence. Keep it simple.
