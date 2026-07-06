---
type: feature-plan
feature: right-sizing
sibling: tech.md
parent: ../../plan.md
updated: 2026-07-06
---

# Feature: Right-Sizing — Implementation Plan

Nine units. Unit 0 (critical correctness fixes) ships first and stands alone —
it repairs the reproduced corruption/data-loss/secret/recall bugs the deep hunt
found, valuable even if the collapse never happens. Then: fix remaining broken
behavior, one mechanical workspace collapse, semantic shrinks in final
coordinates, tests and process last. Each unit leaves the suite green and the
CLI/MCP usable — no long-lived broken states.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Starts immediately (Feature 11/12 are DONE). The v2 core
rewrite feature starts only when this feature is DONE.

---

## Problem Frame

The audit ([research.md](research.md)) found ~3k LOC of good engine carrying
~18k LOC of packaging/wiring/chrome, ~25k LOC of tests (much of it mechanism),
and ~15k LOC of process apparatus — plus live bugs (dead exit codes,
unreachable MCP envelope, config.toml mutated at runtime). Order is chosen so
behavior fixes aren't entangled with the rename, and so every semantic change
after unit 2 is reviewed against the final layout.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Single package](product.md#requirement-r1--single-package) | right-sizing/2 |
| R2 | [Typed data contracts](product.md#requirement-r2--typed-data-contracts) | right-sizing/3 |
| R3 | [Config is read-mostly](product.md#requirement-r3--config-is-read-mostly) | right-sizing/1, right-sizing/4 |
| R4 | [Honest failure behavior](product.md#requirement-r4--honest-failure-behavior) | right-sizing/1 |
| R5 | [No phantom generality](product.md#requirement-r5--no-phantom-generality) | right-sizing/3, right-sizing/5 |
| R6 | [Right-sized CLI](product.md#requirement-r6--right-sized-cli) | right-sizing/6 |
| R7 | [Tests assert behavior](product.md#requirement-r7--tests-assert-behavior) | right-sizing/7 |
| R8 | [Right-sized process](product.md#requirement-r8--right-sized-process) | right-sizing/8 |
| R9 | [Core swap seam preserved](product.md#requirement-r9--core-swap-seam-preserved) | right-sizing/2, right-sizing/3, right-sizing/5 |
| R10 | [Data-path correctness](product.md#requirement-r10--data-path-correctness) | right-sizing/0 (+ chunker contract lands in right-sizing/3) |

---

## Key Technical Decisions

1. **Behavior fixes before the rename** — bug diffs stay reviewable and
   bisectable on the old tree.
2. **Collapse is one zero-logic commit** (`git mv` + import rewrites) so
   `git log --follow` survives and review is mechanical.
3. **Disk format is the compatibility boundary**, not Python APIs — models
   round-trip today's camelCase JSON; existing collections never re-index.
4. **Connectors own their manifests** (`from_manifest`) — deletes app-layer
   populate blocks, the env-var channel, private reaches, and core's
   `localFiles` branch in one move.
5. **Delete tests by category, suite green between categories** — mechanism
   tests go, behavior tests stay; anything ambiguous stays.

---

## Unit IDs

Units are `right-sizing/n`, assigned once, never renumbered. Cite in commits:
`refactor: right-sizing/2 collapse workspace`.

---

### right-sizing/0 — Critical correctness fixes (ship first, independent of the collapse)

**Goal:** Stop the bleeding. Fix the reproduced corruption/data-loss/secret/
crash bugs from the deep hunt — these hurt the author *today* and are
independent of the structural work, so they ship first on the current tree (or
cherry-pick to a patch release). Full evidence + line refs:
[research.md](research.md) § Correctness bugs.

**Requirements:** R10 (+ R3 secret/destroy items)

**Dependencies:** —

**Batches (each independently verifiable):**

```
A. Search recall (the product is broken):
   - parsing: replace HierarchicalChunker with a token-aware chunker (HybridChunker
     or a size-bounded splitter); make max_tokens actually bound chunk size;
     honor the embedder's max_seq_length (256). Fixes bugs #1,#3,#4.
   - core: code_chunker slice by the byte buffer, not the decoded str (#2).
   - core: raise max_chunks independently of max_docs; backfill after score
     filter so max_docs is honored (#5). Fix score_threshold scale+range+desc (#6).
B. Corruption / destruction:
   - core: persist FAISS in the deletions-only + explicit-deletions paths (#7).
   - core: guard zero-chunk batches in embedder + faiss_indexer (#9).
   - config: atomic write (tmp→fsync→rename) + reject unserializable values
     BEFORE truncating; this alone kills `config set null` file-loss (#8).
C. Secrets:
   - config CLI: route sensitive fields through set_value/.env; mask in inspect;
     stop echoing (#11). Don't bake INDEXED__* overrides into save_raw (#11).
   - connectors: fix _url_guard to parse authority the way the HTTP client does
     (or strip credentials on off-origin) (#12); .env writer quotes values (#31).
D. Connector content loss:
   - Jira/Confluence async readers: follow_redirects=True, don't raise on 3xx (#13).
   - git change-tracker: compare stored content hashes; unquote git C-quoted
     paths (#14). ADF/storage-format: keep mention/link/media/image text (#15).
E. Fail-loud + honest CLI:
   - InspectService omits (not zero-fills) missing collections; callers error
     with non-zero exit (#19,#22). Escape/disable Rich markup on user/content
     strings (#23). Stop resetting the logger to WARNING (#24). Don't persist
     create overrides before success; normalize/validate paths; strip+normalize
     URLs for cloud detection (#25,#26,#27,#29). update: don't abort the loop,
     set exit code on failure (#28).
F. MCP:
   - remove/relax ResponseCachingMiddleware or add invalidation (#17). Surface
     per-collection errors instead of dropping them (#18,#21).
G. Config wiring truth:
   - register storage under the path the CLI reads, or read what's registered;
     delete or wire the dead indexing/embedding/storage sections; unify batch
     size; make CLI honor [core.v1.search] or stop templating it (#20).
```

**Test scenarios:** one regression test per R10 scenario (large-doc recall,
delete-then-search, `config set null` leaves file intact, secret→.env not TOML,
missing collection → clean error + non-zero exit); markup-injection query;
`--verbose` actually verbose; Jira Cloud attachment indexed against a stub 302.

**Verification:** `uv run pytest -q` green with the new regression tests; manual
repro of each reproduced bug now passing; `sha256(config.toml)` stable across a
failing `config set`.

**Note:** batch A's chunker change defines the document/chunk contract, so its
*final* form lands with the typed models in right-sizing/3 — but the behavioral
fix ships here first. Everything in unit 0 is valuable even if the collapse
never happens.

---

### right-sizing/1 — Fix broken behavior (rot that survives any structure)

**Goal:** Exit codes work; MCP envelope always fires; runtime flows stop
writing to config.toml; Outline env-var side-channel removed.

**Requirements:** R3, R4

**Dependencies:** —

**Files:**

```
apps/indexed/src/indexed/app.py                     # sys.exit(exit_code_for(exc))
apps/indexed/src/indexed/mcp/{tools,resources}.py   # except Exception → envelope
packages/indexed-config/src/indexed_config/service.py  # in-memory override overlay
apps/indexed/src/indexed/bootstrap.py               # overrides, not .set()
apps/indexed/src/indexed/connector_wiring.py        # overrides; drop os.environ channel
```

**Test scenarios:**

- Handled `IndexedError` → process exit code matches `EXIT_CODES` (subprocess test).
- Corrupt manifest → MCP `search` returns envelope, not raw exception.
- `index update` on jira/confluence/outline fixtures → config.toml byte-identical
  before/after; incremental cutoff still applied (assert on constructed query).

**Verification:** `uv run pytest -q` green; new subprocess exit-code test; a
`sha256(config.toml)` before/after assertion in the update tests.

---

### right-sizing/2 — Collapse the workspace

**Goal:** One package `indexed`, one `pyproject.toml`; una, per-package
pyprojects, `sync_version.py`, protocols-as-a-package gone; slim import check.

**Requirements:** R1, R9

**Dependencies:** right-sizing/1

**Files:**

```
pyproject.toml                       # single; hatchling; console scripts
src/indexed/{core,connectors,config,parsing,mcp,cli,models.py,protocols.py,utils.py}
scripts/check_imports.py             # 4 edges, replaces check_import_graph.py
tests/**                             # import-path rewrite only
```

**Test scenarios:**

- `uv build` → one wheel; clean-venv install runs `indexed --help`, `indexed-mcp --help`.
- Full suite green with only import-path changes.
- `check_imports.py` fails on a deliberately-added forbidden edge (negative test).

**Verification:** `uv run pytest -q`; wheel smoke script output pasted;
`git log --follow` shows history preserved for a sampled moved file.

---

### right-sizing/3 — Typed contracts + connector-owned manifests

**Goal:** `models.py` (Manifest/ConvertedDocument/Chunk/SearchResult) +
corrected protocols wired through the engine; connectors gain `from_manifest`;
`composition.py` replaces bootstrap/connector_wiring/runtime; DI callable soup
→ two required params; core's `localFiles` branch and engine→services import
gone.

**Requirements:** R2, R5 (dead DTO/registry deletions), R9

**Dependencies:** right-sizing/2

**Files:**

```
src/indexed/models.py  src/indexed/protocols.py
src/indexed/core/{creator,services}.py        # annotate; facade signatures
src/indexed/connectors/*/connector.py         # from_manifest per source
src/indexed/connectors/registry.py            # delete CONFIG_REGISTRY etc.
src/indexed/cli/composition.py                # the one wiring module
```

**Test scenarios:**

- Manifest fixtures from all four sources round-trip byte-stable.
- `isinstance(reader, DocumentReader)` true for every shipped reader.
- `update` works identically for all four sources through `from_manifest`
  (localFiles keeps deletions + change-tracker state saving).
- mypy on `core/` + `models.py` + `protocols.py`: 0 errors (new strict island).

**Verification:** `uv run pytest -q`; `uv run mypy src/indexed/core src/indexed/models.py src/indexed/protocols.py` clean; grep proves dead symbols gone.

---

### right-sizing/4 — Config shrink

**Goal:** `indexed/config/` at ~450 LOC: one path/mode implementation, cached
`get_config()`, in-memory overrides formalized, Registry/Provider/`bind()`
deleted, `get_raw` alias gone; both module-level singletons replaced.

**Requirements:** R3, R5

**Dependencies:** right-sizing/3

**Files:**

```
src/indexed/config/__init__.py  src/indexed/config/storage.py
src/indexed/core/services.py          # drop search-service module singleton
callers of ConfigService.instance()   # → get_config()
```

**Test scenarios:**

- Mode resolution matrix (flag / workspace pref / `.indexed` present / default)
  unchanged — reuse existing behavior tests.
- Secrets still route to `.env`; `.gitignore` guard still fires in local mode.
- `wc -l src/indexed/config` ≤ ~500.

**Verification:** `uv run pytest -q tests/.../config -q` + full suite; LOC check.

---

### right-sizing/5 — Core simplification

**Goal:** Delete indexer registry/factory naming machinery, multi-indexer
plumbing, 500k batching, `_UpdatingCollectionCreator` (→ `post_run` param),
legacy simple progress callback (one `Progress` protocol, enum phase names);
typed `SearchResult` end-to-end; safe re-create via tmp-dir + rename swap;
`IndexedError` subclasses for expected core failures.

**Requirements:** R5, R9

**Dependencies:** right-sizing/3

**Files:**

```
src/indexed/core/{creator,searcher,services,faiss_indexer,persister}.py
src/indexed/core/indexer_{registry,factory}.py   # deleted
src/indexed/{cli,mcp}/**                          # consume SearchResult + Progress
```

**Test scenarios:**

- Existing collection (old naming scheme dirs) still searchable — loader keeps
  reading `indexers[0].name` paths (R9 scenario "existing collections keep working").
- Kill create mid-run (fixture hook) → original collection intact.
- Search returns typed results; MCP formatting consumes them unchanged.

**Verification:** full suite; benchmark suite unchanged within noise
(`uv run pytest tests/benchmarks/ --benchmark-only`); crash-safety test.

---

### right-sizing/6 — CLI shrink

**Goal:** One schema-driven `create` command (992 → ~250); config CLI →
get/set/list/validate (1,959 → ~300); `migration.py` + its tests deleted;
Rich components reduced to those actually rendered; lazy connector-registry
build restores <1s startup for non-connector commands; every command file
≤300 lines.

**Requirements:** R6

**Dependencies:** right-sizing/3

**Files:**

```
src/indexed/cli/commands/create.py     # generic, driven by connector config_spec
src/indexed/cli/config_cli.py          # 4 subcommands
src/indexed/cli/components/**          # prune unused
src/indexed/cli/migration.py           # deleted
src/indexed/cli/composition.py         # registry built only for create/update
```

**Test scenarios:**

- Per-source create parity: flags, prompting of missing required fields,
  credential routing — existing behavior tests repointed, not weakened.
- `time indexed index search --help` (or import-time test) < 1s without
  connector imports.
- `wc -l` gate: no command module > 300.

**Verification:** full suite; startup timing evidence; LOC check output.

---

### right-sizing/7 — Test right-sizing

**Goal:** Delete mechanism tests (registry membership, shims, protocol stubs,
Rich markup, migration); keep behavior/system/benchmarks; coverage gate
re-scoped to `core/`+`connectors/`+`config/` ≥85%; suite target ≤ ~15k LOC.

**Requirements:** R7

**Dependencies:** right-sizing/4, right-sizing/5, right-sizing/6

**Files:**

```
tests/**            # category deletions per research.md § Dead weight
pyproject.toml      # coverage config scope
```

**Test scenarios:**

- Suite green after each deletion category.
- Coverage on scoped modules ≥85%; UI modules exempt.

**Verification:** `uv run pytest -q --cov` output pasted; before/after LOC.

---

### right-sizing/8 — Process right-sizing

**Goal:** One root `AGENTS.md` (≤100 lines) absorbing the per-package ones;
`.agents/skills/` unvendored (installed via `skills-lock.json`); CI = lint +
mypy + test + import-check + wheel smoke; benchmark workflow slimmed to
on-demand; root `.spec/tech-*.md` updated to the single-package reality.

**Requirements:** R8

**Dependencies:** right-sizing/7

**Files:**

```
AGENTS.md  CLAUDE.md symlinks       # one instruction file
.agents/                            # removed from repo
.github/workflows/*.yml             # trimmed
.spec/tech.md .spec/tech-*.md       # COMPOUND: promote merge-marked blocks
```

**Test scenarios:**

- Fresh session bootstrap works from the one AGENTS.md (skills install cleanly).
- CI green on the trimmed workflows.

**Verification:** CI run link; `bash .agents/... validate.sh` equivalent (or
global path) 0 errors on `.spec/`.

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| right-sizing/0 | — (independent; chunker contract informs 3) | — |
| right-sizing/1 | 2 | — |
| right-sizing/2 | 3 | 1 |
| right-sizing/3 | 4, 5, 6 | 2 |
| right-sizing/4 | 7 | 3 |
| right-sizing/5 | 7 | 3 |
| right-sizing/6 | 7 | 3 |
| right-sizing/7 | 8 | 4, 5, 6 |
| right-sizing/8 | — | 7 |

Units 4/5/6 are independent of each other and may run in any order or parallel.

---

## Progress

| Unit | Status |
|---|---|
| right-sizing/0 | NOT STARTED |
| right-sizing/1 | NOT STARTED |
| right-sizing/2 | NOT STARTED |
| right-sizing/3 | NOT STARTED |
| right-sizing/4 | NOT STARTED |
| right-sizing/5 | NOT STARTED |
| right-sizing/6 | NOT STARTED |
| right-sizing/7 | NOT STARTED |
| right-sizing/8 | NOT STARTED |

---

## Open Questions

1. **Keep the dual global/local storage mode?** It drives a large share of
   config complexity (conflict prompts, mode resolution, two .env chains) for
   a single user. Recommendation: keep (it's shipped behavior and useful for
   per-repo indexes), but delete `conflict_prompt.py` UI and rely on the
   simple resolution order. Decide at right-sizing/4.
2. **Async readers.** Jira/Confluence each carry sync + async variants.
   Recommendation: keep exactly one reader per source (async where it exists
   and works, else sync) at right-sizing/3; if attachment throughput regresses
   noticeably, revisit in v2 — do not carry both.
