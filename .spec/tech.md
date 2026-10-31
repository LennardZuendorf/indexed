---
type: entrypoint
scope: tech
children: [tech-app.md, tech-core.md, tech-config.md, tech-connectors.md, tech-parsing.md]
updated: 2026-10-31
---

# Tech Spec: indexed

High-level architecture summary. Cross-cutting concerns + per-component pointers.
Component internals live in the branch docs below.

**For product decisions (what/why), see [product.md](product.md).**

---

## Component Specs

One tech branch doc per `src/indexed/` subpackage:

| Subpackage | Branch doc | Covers |
|-----------|-----------|--------|
| `src/indexed/cli/`, `src/indexed/mcp/` | [tech-app.md](tech-app.md) | CLI architecture, storage-mode, Rich UI, logging, MCP server |
| `src/indexed/core/` | [tech-core.md](tech-core.md) | engine, embedding, FAISS, persistence, search perf |
| `src/indexed/config/` | [tech-config.md](tech-config.md) | config resolution, .env hierarchy, storage layout, schema versioning |
| `src/indexed/connectors/` | [tech-connectors.md](tech-connectors.md) | connector protocol, implemented connectors, change tracking |
| `src/indexed/parsing/` | [tech-parsing.md](tech-parsing.md) | ParsingModule, Docling, tree-sitter |

`src/indexed/utils/` (logging, retry, batching) is a thin shared foundation — no
separate doc; helpers are imported by every layer. `src/indexed/protocols/` (typed
contracts + connector protocols, the leaf) has no separate doc either — covered
inline below (§ Protocols Subpackage) and in tech-core.md / tech-connectors.md.

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────┐
│                   User Interfaces                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   CLI App   │  │  MCP Server │  │  Python API │     │
│  │   (Typer)   │  │  (FastMCP)  │  │   (Index)   │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
└─────────┼─────────────────┼─────────────────┼───────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │        Service Layer               │
          │  CollectionService                 │
          │  SearchService                     │
          │  InspectService                    │
          │  UpdateService                     │
          │  ClearService                      │
          └─────────────────┬─────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │         Engine Layer               │
          │  DocumentCollectionCreator         │
          │  DocumentCollectionSearcher        │
          │  FaissIndexer                      │
          │  SentenceEmbedder                  │
          │  DiskPersister                     │
          └─────────────────┬─────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │     Infrastructure Layer           │
          │  Connectors (protocol-based)       │
          │  ConfigService (singleton)         │
          │  Utilities (logging, retry, etc.)  │
          └────────────────────────────────────┘
```

Layer detail: app → [tech-app.md](tech-app.md); engine → [tech-core.md](tech-core.md);
connectors → [tech-connectors.md](tech-connectors.md); config → [tech-config.md](tech-config.md).

---

## Tech Stack

| Library | Version | Purpose |
|---------|---------|---------|
| **Python** | 3.11+ | Language runtime |
| **uv** | 0.5+ | Package manager |
| **FAISS** | latest | Vector similarity search |
| **sentence-transformers** | latest | Embedding generation |
| **Typer** | 0.26+ | CLI framework |
| **Rich** | 15.0+ | Terminal UI |
| **FastMCP** | 3.4+, <4 | MCP server |
| **Pydantic** | 2.13+ | Validation |
| **Docling / tree-sitter** | latest | Document & code parsing |
| **ruff** | 0.16.2 | Linter + formatter |
| **ty** | 0.0.58 | Type checker |
| **pytest** | 9.1+ | Testing |

### Package Structure

Single package, one wheel (`indexed-sh`); no workspace, no `una`:

```text
indexed/
├── src/indexed/
│   ├── cli/                  # Typer app; composition.py is the single wiring site
│   ├── mcp/                  # FastMCP server
│   ├── core/                 # Indexing & search engine; facade in core/__init__.py
│   ├── connectors/           # Source connectors (files/jira/confluence/outline)
│   ├── config/                # Config management (ConfigService singleton)
│   ├── parsing/               # Shared parsing module (Docling, tree-sitter)
│   ├── protocols/             # Typed contracts + connector protocols — the leaf
│   └── utils/                 # Shared utilities (logging, retry, batching)
└── tests/                     # Test suite
```

**Build system:** a single `hatchling` build produces one wheel.

---

## Data Flow

Cross-component pipelines. Component internals: [tech-core.md](tech-core.md),
[tech-connectors.md](tech-connectors.md), [tech-parsing.md](tech-parsing.md).

### Indexing Pipeline

```text
Source API → Reader → Converter → Chunker → Embedder → Indexer → Persister
```

1. **Reader** fetches documents from source (Jira API, file system, etc.)
2. **Converter** transforms to standardized `Document` objects
3. **Chunker** splits into token-window chunks (≤ embedder `max_seq_length`, 256 for the default model — never silently truncated; see [tech-parsing.md](tech-parsing.md))
4. **Embedder** generates vectors (384-dim via `all-MiniLM-L6-v2`)
5. **Indexer** builds FAISS index (`IndexFlatL2` default)
6. **Persister** saves to disk atomically

### Search Pipeline

```text
Query → Embedder → FAISS Search → Result Mapper → Formatter
```

1. **Embedder** converts query text to vector (same model as indexing)
2. **FAISS Search** finds K nearest neighbors (squared L2 distance in [0, 4]; lower = closer)
3. **Result Mapper** looks up chunks, documents, metadata
4. **Formatter** outputs as card/table/compact/JSON

---

## Testing Strategy

**Target:** >85% coverage on `core`/`connectors`/`config`/`parsing`/`protocols`/
`utils`. `cli`/`mcp` (UI chrome) are exempt from the gate — see § Post-Simplify
Structural Rules and `[tool.coverage.run]` in `pyproject.toml`.

```text
tests/
├── unit/              # tests/unit/{indexed,utils,scripts}/ — indexed/ mirrors src/indexed/'s subpackages
├── system/            # integration tests
├── characterization/  # behavior-net harness (regression-guards fixed bugs)
└── benchmarks/        # performance tests
```

```bash
uv run pytest -q                              # all
uv run pytest tests/unit/indexed/core/ -q     # one subpackage
uv run pytest -q --cov=src/indexed --cov-report=html
```

### CI Benchmarking

Performance regressions are caught in CI, not via local scripts. The former
`.benchmarks/benchmark_baseline.py` / `benchmark_compare.py` (baseline capture +
diff logic) were deleted and replaced by the GitHub Marketplace action
[`pytest Benchmark Baseline Check`](https://github.com/marketplace/actions/pytest-benchmark-baseline-check)
(`lennardzuendorf/pytest-bench-action`), wired in
`.github/workflows/python-benchmark.yml`.

The action runs `tests/system` + `tests/benchmarks` with `--benchmark-only`,
compares against a per-branch JSON baseline committed under
`.benchmarks/baselines/` (the general `.benchmarks/*.json` ignore carries a
`!baselines/**` exception — negating just the dir, not `**`, leaves files
inside still matched by `*.json` and silently un-stageable), posts one PR
comment per run (deletes any prior bot
comment matching the report header before posting, so re-runs don't spam the
thread), and fails the job on a tolerance-exceeding regression.

**Contract: a PR run measures and gates, it never writes.** The pull_request
job holds `contents: read` and `pull-requests: write` — nothing else. The
action's own update path is still there upstream: when a run drifts past
`update-tolerance`, when the comparison is skipped for a hardware mismatch
(exit 3) or when the base branch has no baseline at all, it stages
`.benchmarks/baselines/main.json` and pushes a `[skip ci]` commit onto the PR
head. With no write scope that push cannot succeed (`continue-on-error` turns
it into a warning), so the PR head is the SHA that was measured — the
untested-head defect of issue #253 cannot recur. `update-tolerance: 1000`
additionally keeps ordinary drift from even staging the commit, for clean logs;
it is not the guarantee, because no tolerance value covers the exit-3 and
no-baseline cases — the read-only token does.

**Only a baseline-only PR may move main's baseline.** A PR that changes code
must not touch that file: its gate would otherwise compare against numbers the
PR itself wrote, so a regression would land as the new reference instead of
failing. `.github/workflows/baseline-guard.yml` enforces both halves — it fails
a code-changing PR that rewrites the file, and passes a PR whose only change is
a baseline *rewrite*. The door is deliberately not "nothing but that file": a
PR that deletes it also changes nothing else, yet removing main's baseline
leaves the next run logging "No baseline found for base branch 'main' —
skipping cross-branch comparison" and passing green, so the performance gate
silently stops gating (the same class of damage as an untested head). The guard
therefore requires the file to be present at HEAD before it opens the door, and
fails a deletion with an explicit message. Because the benchmark job can no
longer add a `[skip ci]` commit, the guard's remedy ("restore the file, re-run
the benchmark job") now converges; a re-run cannot re-add it.

**Refresh lane.** `.github/workflows/python-benchmark.yml` is also
`workflow_dispatch`-able, and its `refresh-baseline` job runs only when
dispatched on `main` (that job alone opts into `contents: write` +
`pull-requests: write`). It re-measures through the same pinned action and the
same `&benchmark-inputs` inputs as the gate; since the action's update path is
pull_request-only, its "Save baseline" step only rewrites the file in the
workspace. If that differs from `main`'s copy, the job force-pushes it to
`chore/benchmark-baseline-refresh` and opens (or updates) one PR changing
nothing but the baseline. A >20% slowdown against `main`'s previous numbers
fails the run before that step — adopt numbers only once a slowdown is
understood as expected. Nothing refreshes on `push` to `main`: one refresh PR
per merge would be noise, so moving the baseline stays a deliberate maintainer
action.

**A skipped comparison is a failed check, not a pass (#267).** With
`enforce-same-node` at its `"false"` default the action's hardware-mismatch path
(exit 3) logs a `::warning::` and reports `regression-detected=false`, so the job
returned **green while comparing nothing** on every PR after GitHub rotated the
`ubuntu-latest` CPU (EPYC 7763 → 9V74, 2026-10). The gate job therefore has a
step that fails it, writes both CPU fingerprints (the committed baseline's and
this run's) to the log and the job summary, and names the repair.
`enforce-same-node: "true"` is deliberately not the fix: on a heterogeneous
fleet it reds PRs at random with no remedy, which teaches everyone to ignore the
check. The step reds exactly one honest case — *this machine cannot be compared,
so there is no verdict*. It is **not** gated on the action's
`comparison-skipped` output, because that output is only written by the compare
steps: when main has no committed baseline at all, `compare-main` never runs,
the flag stays `false`, and a flag-gated step is skipped — a green job with no
cross-branch verdict, the very defect being fixed. It runs whenever the
benchmark step itself succeeded, and the fingerprints plus the baseline fetch
decide the rest; the bootstrap case is then reported explicitly ("no committed
baseline on 'main', dispatch … to record one") instead of dying on a `git
show`. The reference it reads is `origin/<base branch>`, never `HEAD`: the
action's update path ends in a `EndBug/add-and-commit` that commits its own
numbers **locally** even when the push is denied by `contents: read`, so inside
that job HEAD's baseline is the run's own measurement and a HEAD-based guard
would compare the run with itself, agree, and return green (observed on PR
#268's first run — the same self-referential defect as #253, one layer up). The
step decides from the fingerprints rather than from the flag alone: the action's
`comparison-skipped` is also set by the *sequential* comparison, so it only
fails when this run's machine differs from main's baseline — when they match,
the cross-branch verdict stands and the job stays green (and the notice says
which of the two comparisons was skipped, rather than claiming one was). A
matching fingerprint is necessary but **not** sufficient for a valid verdict:
two runs on different nodes of the same CPU model put
`test_parse_large_markdown` at 690 ms, 922 ms and 943 ms, so per-node variance
alone can red a clean diff — the guard cannot detect that, and the same-job A/B
below is what removes it.

**Fleet rotation is repairable: `accept_cpu_change`.** The refresh lane refuses
a fingerprint change by default, because adopting another machine's numbers
would poison the very reference the gate compares against. `workflow_dispatch`
takes `accept_cpu_change: true`, which lets the refresh proceed, forces the
refresh PR even when the numbers moved less than `DRIFT_PCT`, and records old vs
new fingerprint in the job summary, the refresh PR body and its title. That PR's
table is a
**measurement, not a verdict** — a cross-CPU diff cannot say whether code got
slower — and it exists so the next PR run compares like with like. Without that
input no mechanism in the repo can re-record a rotated baseline. That repair
cannot deadlock on the check it repairs: `.benchmarks/**` is not in this
workflow's `paths` filter, so the baseline-only refresh PR triggers no benchmark
run at all, and the guard (below) is the only check it faces.

Configured in this repo via `cross-branch-tolerance: 20`, the inert
`update-tolerance: 1000`, and a per-test `threshold-map` (max seconds per
benchmark name substring). A regression can be waived per-PR via the
`benchmark-override` label (`override-label`, explicitly set here) — the
regression still shows in the PR comment but doesn't fail the job; the
repo-wide tolerance is untouched.

A `concurrency` group (keyed on PR number, else ref; `cancel-in-progress: true`)
prevents overlapping runs from racing each other.

**Known upstream gap:** the action exposes no `update-baseline: false` switch,
which is why this repo scopes write permission instead of switching the path
off. If a release adds one, prefer it over `update-tolerance: 1000` and drop
that value.

Pinned to an exact release tag (`@v1.0.2`), not the floating `@v1` major tag —
the floating tag raced with upstream's own release-automation retagging and
briefly 404'd mid-release (`unable to find version v1`). Bump the pin by hand
on new releases instead.

**Resolved (v1.0.0):** comparability used to key on the runner hostname
(`machine_info.node`), which GitHub-hosted runners randomize per job, so
cross-run comparisons false-positived as regressions. `v1.0.0` gates on a
CPU/system fingerprint instead (`cpu.brand_raw` + arch + core count + `system`),
so `ubuntu-latest` runs on the same CPU model compare cleanly; a genuine
hardware mismatch now skips with `comparison-skipped` (or hard-fails if
`enforce-same-node: "true"`, unset here) instead of hard-failing by default.
Not configured in this repo: `enforce-same-node` (defaults `"false"`; the skip
is turned into a job failure by the workflow step above, which can name both
fingerprints and the repair — the action's own hard-fail cannot).

---

## Build & Distribution

### Wheel

A single `hatchling` build packages `src/indexed/` into one wheel — no bundling
step, no per-package builds.

```bash
uv build --out-dir dist
# → dist/indexed_sh-<version>-py3-none-any.whl   (wheel)
# → dist/indexed_sh-<version>.tar.gz             (sdist)
uv run python scripts/validate_wheel.py dist/*.whl   # PyPI archive validator (wheel only), also in CI
uv run --with twine twine check --strict dist/*      # metadata render check (wheel + sdist), also in CI
```

### Release

The GitHub Release **tag** is the version, decided at release time — no manual
pre-bump in a PR. `pyproject.toml` declares `dynamic = ["version"]` and
**hatch-vcs** resolves the version from `git describe` at build time, so no
version string is stored in the repo at all. On `release: published`, the build
job checks out the tag at `fetch-depth: 0` (hatch-vcs needs the tags), builds,
asserts the built dists carry the tag version, validates (validate_wheel +
`twine check --strict`), and publishes wheel + sdist to PyPI via OIDC trusted
publishing (no token). There is **no backmerge job**: `main` has no version to
drift, so nothing has to be written back. Still no `sync_version.py`.

`uv.lock`'s root-package entry simply omits the `version` field (uv reports the
change as `indexed-sh v0.0.5 -> (dynamic)`; no such token is written to the
file), so the lock does not churn per commit.

Off-tag builds use the `post-release` scheme (`raw-options` in
`[tool.hatch.version]`), yielding `<last-tag>.post<N>+g<sha>` — e.g.
`0.0.7.post4+g5d98c95` for four commits past `v0.0.7`, plus a `.dYYYYMMDD`
suffix when the tree is dirty. It anchors on the **last** tag rather than
guessing the next one; the default `guess-next-dev` would claim `0.0.8.devN`,
which is wrong whenever the next release isn't a patch bump. The `+g<sha>`
local segment is also a tripwire: PyPI rejects local versions, and the release
job's assert catches the mismatch before upload.

`python-ci.yml`, `python-cov.yml`, and `python-release-ci.yml` check out at
`fetch-depth: 0`. On a shallow tagless checkout hatch-vcs resolves to
`0.0.0.postN+g<sha>` with only a `UserWarning`, and `validate_wheel.py` and
`twine check --strict` both still pass — a wrong version that goes green.
`python-benchmark.yml` is the exception: `pytest-bench-action` checks out at a
hardcoded `fetch-depth: 2` that no input overrides, so its install carries a
non-tag version. Nothing in the benchmark suite reads the version, so this is
tolerated rather than fixed.

Building from a tree with **no** `.git` (GitHub's auto-generated source tarball,
a vendored copy) resolves to the `fallback_version` of `0.0.0`. Without that
fallback hatch-vcs raises `LookupError` and the build dies — a regression
against the old static version. The fallback also supplies the base when git is
readable but no tag is reachable, which is why a shallow checkout reads
`0.0.0.postN+g<sha>` rather than `0.0.postN+g<sha>` — but it never yields a bare
`0.0.0` there, so the release assert still catches it. Measured with the current
config:

| checkout | built version |
| --- | --- |
| `HEAD` == tag, clean | exact tag version |
| tags reachable, off-tag | `0.0.7.post3+g21083d3d9` |
| shallow, tagless, clean | `0.0.0.post2+ga0347642e` |
| no `.git` | `0.0.0` |

---

## Architectural Rules

Hard constraints across all code — v2 core, new connectors, surviving infrastructure.

### Post-Simplify Structural Rules

Promoted from the retired Feature 14 (Simplify) tech spec as of simplify/6 —
normative root rules from here on,
independent of Feature 14's own DONE/PLANNED status ([plan.md](plan.md) §
Feature Sequence). The single-package collapse, `check_imports.py` gate,
scoped coverage config, and one `AGENTS.md` are already live in the tree; the
remaining Simplify units (residual dead-code/test cleanup) converge the rest
of the codebase toward these same rules rather than establishing new ones.

- **One package, four module edges** (`cli`/`mcp` → `core`|`connectors`|`config`;
  `core ↛ connectors`; `connectors ↛ core`; `config`/`utils`/`parsing`/`protocols`
  never import up), enforced by `scripts/check_imports.py`. One `pyproject.toml`,
  one wheel (`indexed-sh`), no `una`, no per-package builds, no `sync_version.py`.
- **No phantom generality.** No abstraction (registry/factory/multi-impl loop)
  over a single implementation. One indexer, one progress protocol, no dead DTOs
  or re-export shims.
- **Behavior-only tests.** Keep behavior/system/benchmark tests + the
  characterization harness; no mechanism tests (registry membership, shims,
  protocol stubs, Rich markup, migration). **Coverage gate is scoped to
  `core`/`connectors`/`config`/`parsing`/`protocols`/`utils`; UI chrome
  (`cli`/`mcp`) is exempt** (see `[tool.coverage.run]` in `pyproject.toml`).
- **One root `AGENTS.md`** (≤100 lines); agent skills install from
  `skills-lock.json`, never vendored.

### Dependency Direction

```text
┌──────────────────────────────────────────────────────┐
│  CLI / MCP (src/indexed/cli/, src/indexed/mcp/)      │  ← UI only, thin commands
│  May import: core (facade), connectors.registry,     │
│  config, protocols, utils                            │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Core Engine (src/indexed/core/)                     │  ← Business logic
│  May import: protocols, config, utils                │
│  MUST NOT import: CLI, MCP, concrete connectors      │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Connectors (src/indexed/connectors/)                │  ← Data source adapters
│  May import: protocols, config, utils, parsing       │
│  MUST NOT import: core engine, CLI, MCP              │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│  Config, Utils, Parsing, Protocols (infrastructure)  │  ← Shared foundation
│  MUST NOT import: anything above                     │
└──────────────────────────────────────────────────────┘
```

- Dependencies flow **downward only** — never import from a higher layer
- Core engine receives connectors via **dependency injection**, never imports concrete implementations
- Protocols/interfaces live in the lowest layer that needs them
- Circular dependency → extract the shared interface into a lower package

### File Size Limits

| File type | Max lines | Action when exceeded |
|-----------|-----------|---------------------|
| CLI command file | 150 | Extract business logic to a service module |
| Service module | 300 | Split by responsibility |
| Any module | 400 | Split into submodules or extract helpers |

### Config Registration

Config specs are registered **explicitly** during app initialization, never at import time:

```python
# CORRECT — explicit registration function
def register_config(config_service: ConfigService) -> None:
    config_service.register(SearchConfig, path="core.v2.search")

# WRONG — import-time side effect in __init__.py
_svc = ConfigService.instance()      # side effect at import
_svc.register(SearchConfig, ...)     # silent if fails
```

### Error Handling

All exceptions inherit from `IndexedError`:

```text
IndexedError
├── ConfigurationError
│   └── ConfigValidationError
├── StorageError
│   └── StorageConflictError
├── CLIError
└── MCPError
```

- All package exceptions MUST inherit from `IndexedError`
- NEVER use bare `except Exception: pass` — always log or re-raise
- CLI layer catches `IndexedError` subtypes → user-friendly message + exit code
- MCP layer catches `IndexedError` subtypes → structured error dict
- Unexpected exceptions propagate with full traceback
- Missing/corrupt collections **fail loud**: they raise `IndexedError` and are
  **omitted from status** (never zero-filled into a fake-healthy placeholder); the
  CLI exits **non-zero** (via `exit_code_for`) with a clean message — never a raw
  traceback, never a success exit on failure
- The MCP boundary **envelopes every exception** (not only `IndexedError`) and
  surfaces per-collection failures in the result envelope — never a silent
  "0 matches" — and must not serve **stale** cached results after a re-index

### No Dual Code Paths

If a value is accessible via dependency injection (lifespan state, constructor arg)
**and** via a global/singleton, pick one path. Never maintain both with fallback logic.

### No Import-Time Side Effects

Module-level code must not call singleton accessors, register config specs, set up
logging, or mutate global state. All initialization happens in explicit
`setup_*()` / `register_*()` functions called by the app entry point.

### Thin Commands, Fat Services

```text
Command (parse args + format output) → Service (orchestrate) → Engine (execute)
```

A command file branching on business rules is a sign logic needs extraction.

### Protocols Subpackage (`indexed.protocols`)

Shared connector contracts, **typed data models**, and cross-layer DTOs live in the
**leaf** subpackage `src/indexed/protocols/` (import `indexed.protocols`) — the only
import-legal home, since `core`/`connectors`/`config` may not import one another but all
may import `protocols`. Engine-only DTOs stay in core.

- **Typed data contracts** (`protocols/models.py`): `Manifest`, `ConvertedDocument`,
  `Chunk`, `CollectionSearchResult` (+ `DocumentMatch`/`MatchedChunk`) and `SourceConfig`.
  They round-trip today's on-disk **camelCase JSON byte-stable** (fields declared in
  on-disk key order, dumped `by_alias=True`, `exclude_none=True`) — the on-disk v1 format
  is the **compatibility boundary**, so a v2 engine reads the same collections. The engine
  reads/writes these models, never `dict["stringKey"]`; a field mismatch is a ty error,
  not a runtime `KeyError`.
- **Corrected connector protocols** (`protocols/connectors.py`): `DocumentReader` declares
  exactly what the engine calls — `get_number_of_documents` / `read_all_documents` /
  `get_reader_details`; `DocumentConverter` declares `convert`. A connector missing one is
  a ty error, not a runtime `AttributeError`. `BaseConnector` also declares
  `from_manifest(manifest, config, *, storage_path) -> ConnectorRun` — each connector owns
  its manifest keys and incremental cutoff, so **core's update path has no per-source /
  `localFiles` branches**.
- `SourceConfig`, `ProgressUpdate`, `ProgressCallback`, `PhasedProgressCallback` (the
  progress callbacks are today's dual system; Feature 14 collapses them to one `Progress`
  protocol).

`core` and `connectors` both depend on `protocols`; neither imports the other's
concrete types for wiring.

### Core Facade & App Composition Root

**Core is consumed only through the version-dispatching facade `indexed.core.engine`**
— `create` / `update` / `search` / `inspect` / `status` / `clear` / `collection_exists`
(+ the shared models): 13 names, the same surface as the former `core.v1.engine`, plus an
`engine=` selector. The facade (lazy `__getattr__`) routes every call to the v1 or v2
engine. For existing collections the on-disk manifest `version` marker is **authoritative**
— an explicit selector may only confirm it or fail with `EngineMismatchError`; selectors
(flag > env > config > default) choose the engine for **new** collections only. A collection
with no `version` key is v1. The unrecognized-version contract now SPLITS by op, per the
final review of issue #186:

- `create` / `update` / `clear` (via `_resolve_existing_engine`) still **fail loud** —
  `UnknownEngineVersionError`, never a silent v1 fallback, collection untouched.
- `search` / `status` / `inspect` (via `_group_names_by_engine`) instead **omit** the
  unrecognized-version collection from its batch (a warning is logged) rather than
  aborting the whole call. `search()`'s return type is a dict keyed by collection name, so
  it CAN and does carry the omission back as a per-collection `{"error": <message>}` entry
  (the same convention `core/v2/retrieval.py` and v1's `search_service.py` already use for
  a per-collection failure inside a batch); `status()`/`inspect()` return plain lists with
  no per-item error slot, so they purely omit it with a logged warning — unchanged.

No code above the facade may import `core.v1.*` or `core.v2.*` directly (to mock a
facade-resolved symbol in tests, patch the facade attribute) — this is now CI-enforced by
`scripts/check_imports.py`'s `cli/mcp ↛ core.v1, core.v2` rule, not merely a documented
convention. `src/indexed/core/facade_config.py` is part of this facade surface: it holds
`CoreEngineConfig` ([core] engine, the default-engine selector for NEW collections) plus 7
lazily re-exported v1 config-model/utility symbols, so cli/mcp files never import
`core.v1.*`/`core.v2.*` for those either. `config/commands/` is a separate, pre-existing
exemption in `check_imports.py` (`_EXEMPT_DIRS`) — same composition-adjacent rationale as
`config/cli.py` and `cli/composition.py` — so a file there (e.g. `config/commands/
_helpers.py`) importing `core.v1.config_models` directly is expected, not a facade gap.
(v2 ships over a **new version-marked on-disk format**, not v1's — the earlier "same
format" swap premise was superseded by core-v2 ADR-1; v1's format stays frozen.)

**`src/indexed/cli/composition.py` is the single wiring site** — it folds in the
removed `bootstrap.py` + `runtime.py` + `connector_wiring.py`. It:

- builds the connector registry and hands the facade **two REQUIRED callables** —
  `connector_factory` (create-time) and `manifest_factory` (update-time). No
  `Callable | None` + `missing_wiring_error` on the happy path; a missing wiring is a
  `TypeError`/ty error at the call site, not a runtime guard.
- owns `resolve_collections_context(mode_override)` — the **single** storage-path resolver
  for CLI and MCP — and calls `register_app_config` itself, so registered config specs
  survive the singleton reset a non-None `mode_override` forces. Do not revive heuristics
  like "prefer local if non-empty collections dir", and do not add a per-caller defensive
  re-register for callers that go through it.

Each connector's `from_manifest` owns its manifest keys, so core carries no per-type
branches; `composition.manifest_factory` is a one-line registry dispatch.

### Import-Graph CI

`scripts/check_imports.py` (also run in CI, alongside `scripts/check_sizes.py`)
AST-walks `src/indexed` and fails on forbidden edges — the four rules above,
expanded:

| From | Must NOT import |
|------|-----------------|
| `core` | `connectors`, `cli`, `mcp` |
| `connectors` | `core`, `cli`, `mcp` |
| `config`, `parsing`, `utils`, `protocols` | `core`, `connectors`, `cli`, `mcp` |

`cli`/`mcp` sit at the top of the stack and may import any subpackage — they have
no forbidden edge of their own. Run `python scripts/check_imports.py --self-test`
to verify a synthetic forbidden edge is still caught.

### HTTP Retry Policy

Transient HTTP statuses are centralized in `utils/retry.py`:

```python
TRANSIENT_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})
```

`execute_with_retry` re-raises immediately on non-transient HTTP errors (e.g. 404).
Connector readers use this helper — do not duplicate status-code tuples.

---

## Open Technical Questions

1. **Index sharding** — handle >10M documents? Shard by source? Date range? Needs benchmarking.
2. **Embedding versioning** — model update migration? Store model version in manifest? Auto re-index?
3. **Concurrent writes** — no locking on collection updates today. File locking? Atomic swap?
4. **Query caching** — cache query embeddings? Deduplicate identical queries? Invalidation?
5. **Connector reliability** — transient API failures: retry with backoff? Circuit breaker?
6. **Multi-user server mode** — DB instead of JSON files? PostgreSQL + pgvector? SQLite?
7. **CI benchmark runner stability** — the CPU-fingerprint gate handles the
   hostname randomization (see tech.md § CI Benchmarking); `override-label` is
   configured, a skipped comparison now fails the gate (#267), and a fleet
   rotation is repairable via `accept_cpu_change`. **Answered, 2026-10-31:** the
   hosted fleet *does* alternate — four jobs of one PR (same code) landed on
   `AMD EPYC 9V74`, `AMD EPYC 7763` (twice) and `INTEL(R) XEON(R) PLATINUM
   8573C` within an hour, producing two green and two red verdicts from the same
   diff. So a committed cross-run baseline cannot be a stable PR gate, and
   `test_parse_large_markdown` moving +10.4 % and +33.6 % against the same
   baseline on the same CPU model rules out "just raise the tolerance". The
   durable design — measure the merge base and the PR head back-to-back in the
   same job so hardware cancels, keeping the committed baseline as a coarse
   `main` drift alarm — is **proposed and awaiting a decision** (board card
   `t_37f94f47`, ~2× the job cost). Not implemented.
