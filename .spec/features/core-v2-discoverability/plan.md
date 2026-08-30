---
type: feature-plan
feature: core-v2-discoverability
sibling: tech.md
parent: ../../plan.md
updated: 2026-08-30
---

# Feature: Core v2 Discoverability — Implementation Plan

Fix the five discoverability/consistency gaps from
[issue #188](https://github.com/LennardZuendorf/indexed/issues/188), plus two
same-shape sibling defects folded in on maintainer request: the config.toml
`[core] engine` path (R6, same raw-dump defect as #188's `config set`
finding, one more surface) and the `search`/`inspect`/`update`/`remove`
`--help` docstring loss (R7, same mechanism as #188's `migrate` finding).
Seven requirements, five units — R6 rides with R3's unit, R7 rides with R5's.
Units are independent (disjoint files) and can be worked in any order or in
parallel. No P1/P2/P3 severity tiering — none of these are data-loss/crash
defects, all are discoverability/UX gaps on a feature (Core v2) that already
works correctly.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Starts now — Feature 16 (Core v2) is `DONE`. Depends on no
other feature's units; every fix site already exists on `main`.

---

## Problem Frame

PR #162's review confirmed Core v2's safety story is solid but its
discoverability is not: `--engine` is invisible exactly where a v2-curious
user would look for it (`index create --help`); reranking exists only as an
undocumented TOML key and, once given a flag, must not silently no-op on a
v1 search; the same invalid-engine-value error reads different ways
depending on which of *four* surfaces (`--engine` flag, env var, `config
set`, hand-edited `config.toml`) catches it; README never mentions v2
exists; and `migrate`'s carefully-written safety docstring — like its three
siblings' `Examples:` blocks — is discarded by an explicit Typer `help=`
override, so the one command designed to reassure a nervous user before a
data-changing op shows only a generic one-liner. Small, disjoint fixes.

---

## Requirements Trace

| ID | Requirement | Unit |
|---|---|---|
| R1 | [Engine flag is visible where a v2 adopter looks for it](product.md#requirement-engine-flag-is-visible-where-a-v2-adopter-looks-for-it) | core-v2-discoverability/1 |
| R2 | [Reranking has a discoverable CLI flag](product.md#requirement-reranking-has-a-discoverable-cli-flag) | core-v2-discoverability/2 |
| R3 | [config set reports the same clean engine error as the flag and env paths](product.md#requirement-config-set-reports-the-same-clean-engine-error-as-the-flag-and-env-paths) | core-v2-discoverability/3 |
| R4 | [README documents Core v2's existence](product.md#requirement-readme-documents-core-v2s-existence) | core-v2-discoverability/4 |
| R5 | [index migrate help text shows the safety explanation](product.md#requirement-index-migrate-help-text-shows-the-safety-explanation) | core-v2-discoverability/5 |
| R6 | [config.toml core.engine reports the same clean error too](product.md#requirement-core-engine-in-configtoml-reports-the-same-clean-error-too) | core-v2-discoverability/3 |
| R7 | [command --help shows each command's full guidance](product.md#requirement-command---help-shows-each-commands-full-guidance-not-a-generic-one-liner) | core-v2-discoverability/5 |

---

## Key Technical Decisions

1. **R1 mirrors the existing `local` pattern exactly** (`EngineOpt` alias →
   threaded through the 4 create shells → `_create`/`execute_create_command`
   → subcommand value overrides the context-derived one only when explicitly
   set). No new abstraction — reuse the shape already proven for `--local`.
2. **R1's misplaced-option hint is descoped.** Surfacing `--engine` on
   `index create` resolves the issue's concrete repro; a generic Click
   `UsageError` intercept is a bigger systemic change not required by #188
   (tech.md Open Question 1).
3. **R2 threads a single optional `rerank` kwarg through the facade**, v1
   ignoring it silently at the type level (no param to accept it) rather than
   erroring — matches how `--engine` on existing-collection ops already
   degrades gracefully when not applicable.
4. **R3 and R6 both reuse `composition.normalize_engine_selector` directly**
   instead of extracting a message from pydantic's `ValidationError` —
   guarantees byte-identical error text across all four surfaces (`--engine`
   flag, env var, `config set`, config.toml), not just similarly-shaped text.
   Confirmed no import-layering violation for R3: `config/commands/` is
   exempt from the config-package purity rule. R6 goes further and drops
   pydantic from the config.toml path entirely, reading the raw value via
   `ConfigService.get("core.engine")` instead of `bind()`.
5. **R7 extends R5's exact fix** (drop the `help=` override in
   `knowledge/cli.py`) to `search`/`inspect`/`update`/`remove` — same
   mechanism, same file, no reason to fix it on `migrate` only and leave it
   latent on its siblings. Folded into unit 5, not a separate unit.
6. **R1's generic misplaced-option hint stays descoped** (Open Question 1,
   resolved) — R1's own fix already resolves #188's concrete repro, and R2's
   `--rerank`-has-no-effect hint covers the in-scope "don't let a flag
   silently do nothing" case.

---

## Unit IDs

Units are `core-v2-discoverability/n`, assigned once and never renumbered.
All five are independent (disjoint files); cite IDs in commits (`fix(cli):
core-v2-discoverability/1 …`).

---

### core-v2-discoverability/1 — `--engine` on `index create`

**Goal:** `indexed index create files --engine v2 ...` works; `index create
--help` / `index create files --help` show `--engine`.

**Requirements:** R1

**Dependencies:** —

**Files:**

```
src/indexed/cli/knowledge/commands/_create_options.py    # new EngineOpt
src/indexed/cli/knowledge/commands/_create_commands.py   # engine param on 4 shells
src/indexed/cli/knowledge/commands/create.py              # _create() forwards engine
src/indexed/cli/knowledge/commands/_create_helpers.py     # execute_create_command override
```

**Test scenarios:**

- `index create files --engine v2 --path ./docs` succeeds, collection is v2 (system test, e.g. `tests/system/`).
- `index create files --help` output contains `--engine`.
- `indexed --engine v2 index create files --path ./docs` (root-level only, no subcommand flag) behaves identically to today — regression, not new.
- Existing-collection replay semantics unchanged: subcommand `--engine` on an *existing* collection name still takes the raw-flag-only path (no full resolver chain), per the existing `collection_already_exists` branch.

**Verification:** unit tests in `tests/unit/indexed_cli/knowledge/commands/` for the option threading; a system test for the end-to-end CLI parse + create.

---

### core-v2-discoverability/2 — `--rerank`/`--no-rerank` on `index search`

**Goal:** reranking is a documented, overridable CLI flag for v2 searches,
and never silently no-ops.

**Requirements:** R2

**Dependencies:** —

**Files:**

```
src/indexed/cli/knowledge/commands/search.py    # new --rerank/--no-rerank option + v1-no-effect hint
src/indexed/core/engine.py                       # search() facade forwards rerank to v2 only
src/indexed/core/v2/retrieval.py                  # search() overrides resolve_rerank_config().enabled
```

**Test scenarios:**

- `[core.v2.rerank] enabled=false` + `--rerank` on a v2 collection → results are reranked for that call; config.toml unchanged.
- No flag passed → behavior identical to today (config decides).
- `--rerank` explicitly passed, all searched collections are v1 → no crash, and a one-line hint is printed (not a silent no-op); resolved via `core/versioning.py::detect_engine_version` per searched collection (see tech.md R2 for the exact check).
- `--rerank` on a mixed v1+v2 multi-collection search → no hint (at least one collection is v2, so the flag did apply somewhere).
- `index search --help` shows `--rerank/--no-rerank`.

**Verification:** unit tests in `tests/unit/indexed/core/v2/test_retrieval.py` (or sibling) for the override; CLI option test in the search command test file.

---

### core-v2-discoverability/3 — Clean engine error on every surface

**Goal:** identical single-line message across all four surfaces — `--engine`
flag, env var, `config set core.engine`, and a hand-edited `config.toml`.

**Requirements:** R3, R6

**Dependencies:** —

**Files:**

```
src/indexed/config/commands/set.py    # core.engine special case: reuse composition.normalize_engine_selector
src/indexed/cli/composition.py         # resolve_engine_selector: raw config_service.get("core.engine") instead of bind()
```

**Test scenarios:**

- `indexed config set core.engine v3` prints exactly `Invalid engine 'v3'; expected one of: 1, 2, v1, v2` (single line), exit 1.
- `indexed config set core.engine v2` still succeeds and stores the normalized `"2"`.
- A `config.toml` with `[core]\nengine = "v3"` (bypassing `config set`) hits the same single-line message when a command resolves the default engine for a new collection.
- A `config.toml` with no `[core]` section (or an unset `engine` key) still falls back to the default `"1"`, unchanged from today.
- Existing `config set core.engine` tests continue to pass (adjust assertions on error text where they currently assert the old multi-line dump, if any).

**Verification:** unit tests in `tests/unit/indexed/config/` and
`tests/unit/indexed_cli/` (or wherever `resolve_engine_selector` is
currently tested) asserting the exact message string on both surfaces.

---

### core-v2-discoverability/4 — README Core v2 footprint

**Goal:** `--engine` and `index migrate` appear in README's `## Usage`.

**Requirements:** R4

**Dependencies:** —

**Files:**

```
README.md
```

**Test scenarios:**

- Manual read-through: `## Usage` includes one `--engine` example and one `index migrate` example, matching existing style (no new prose section, no docs-site duplication).

**Verification:** manual review (no automated test for README prose); `bash .agents/skills/spec/scripts/validate.sh` not applicable here (README is not `.spec/`).

---

### core-v2-discoverability/5 — Every knowledge command's `--help` shows its own docstring

**Goal:** `indexed index migrate --help` renders the full safety explanation +
examples; `search`/`inspect`/`update`/`remove` get the same fix for
consistency (same file, same mechanism).

**Requirements:** R5, R7

**Dependencies:** —

**Files:**

```
src/indexed/cli/knowledge/cli.py               # drop help= override on all 5 registrations (lines 17-21)
src/indexed/cli/knowledge/commands/migrate.py  # optional: delete dead module-level Typer app
```

**Test scenarios:**

- `indexed index migrate --help` output contains "v1-backup" and "rollback-safe" (or equivalent wording from the docstring) and the `Examples:` block.
- `indexed index search --help`, `indexed index inspect --help`, `indexed index remove --help` each show their own `Examples:` block.
- `indexed index update --help` shows its (currently one-line) docstring — no regression, sets up future content to actually surface.
- `indexed index --help`'s one-line listing for all five commands still reads sensibly (each uses its docstring's first line as short-help — verified readable in tech.md R7).
- Any existing test asserting the old literal one-line help strings (`"Search collections"`, `"Inspect collections"`, `"Update collections"`, `"Remove collections"`, `"Migrate a v1 collection to v2"`) is updated to the new docstring-derived text.

**Verification:** CLI help-output test (`tests/unit/indexed_cli/` or
system-level `--help` snapshot, whichever pattern the repo already uses for
other commands' help text, if any); grep `tests/` for the old literal
strings first.

---

## Progress

| Unit | Status |
|---|---|
| core-v2-discoverability/1 | TODO |
| core-v2-discoverability/2 | TODO |
| core-v2-discoverability/3 | TODO |
| core-v2-discoverability/4 | TODO |
| core-v2-discoverability/5 | TODO |

**Not started — awaiting CONFIRM.** This plan was produced by investigating
issue #188 via 4 parallel research subagents against `main` (2026-08-30); all
file:line anchors in tech.md were re-verified by direct reads after the
subagent pass. Both Open Questions were then resolved on maintainer
follow-up (same day): rerank-on-v1 UX gets a print-a-hint fix (folded into
R2/unit 2), and the two sibling defects originally flagged as descoped
follow-ups (config.toml `[core] engine` raw dump; `search`/`inspect`/
`update`/`remove` losing their `--help` docstrings) are now in scope as R6
(unit 3) and R7 (unit 5). Only Open Question 1 (R1's generic misplaced-option
hint) stays descoped, by explicit maintainer choice.
