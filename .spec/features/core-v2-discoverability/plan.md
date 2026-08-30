---
type: feature-plan
feature: core-v2-discoverability
sibling: tech.md
parent: ../../plan.md
updated: 2026-08-30
---

# Feature: Core v2 Discoverability — Implementation Plan

Fix the five discoverability/consistency gaps from
[issue #188](https://github.com/LennardZuendorf/indexed/issues/188). Units are
independent (disjoint files) and can be worked in any order or in parallel.
No P1/P2/P3 severity tiering — none of these are data-loss/crash defects, all
are discoverability/UX gaps on a feature (Core v2) that already works
correctly.

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
undocumented TOML key; the same invalid-engine-value error reads three
different ways depending on which of three surfaces (`--engine` flag, env
var, `config set`) catches it; README never mentions v2 exists; and
`migrate`'s carefully-written safety docstring is discarded by an explicit
Typer `help=` override, so the one command designed to reassure a nervous
user before a data-changing op shows only a generic one-liner. Five small,
disjoint fixes.

---

## Requirements Trace

| ID | Requirement | Unit |
|---|---|---|
| R1 | [Engine flag is visible where a v2 adopter looks for it](product.md#requirement-engine-flag-is-visible-where-a-v2-adopter-looks-for-it) | core-v2-discoverability/1 |
| R2 | [Reranking has a discoverable CLI flag](product.md#requirement-reranking-has-a-discoverable-cli-flag) | core-v2-discoverability/2 |
| R3 | [config set reports the same clean engine error as the flag and env paths](product.md#requirement-config-set-reports-the-same-clean-engine-error-as-the-flag-and-env-paths) | core-v2-discoverability/3 |
| R4 | [README documents Core v2's existence](product.md#requirement-readme-documents-core-v2s-existence) | core-v2-discoverability/4 |
| R5 | [index migrate help text shows the safety explanation](product.md#requirement-index-migrate-help-text-shows-the-safety-explanation) | core-v2-discoverability/5 |

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
4. **R3 reuses `composition.normalize_engine_selector` directly** instead of
   extracting a message from pydantic's `ValidationError` — guarantees
   byte-identical error text across all three surfaces, not just similarly-
   shaped text. Confirmed no import-layering violation: `config/commands/`
   is exempt from the config-package purity rule.
5. **R3's sibling defect (config.toml `[core] engine` raw dump) and R5's
   sibling pattern (`search`/`update`/`remove` losing their docstrings) are
   explicitly NOT fixed here** — not named in #188, flagged as follow-ups
   (tech.md Open Questions 3-4) rather than silently expanding scope.

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

**Goal:** reranking is a documented, overridable CLI flag for v2 searches.

**Requirements:** R2

**Dependencies:** —

**Files:**

```
src/indexed/cli/knowledge/commands/search.py    # new --rerank/--no-rerank option
src/indexed/core/engine.py                       # search() facade forwards rerank to v2 only
src/indexed/core/v2/retrieval.py                  # search() overrides resolve_rerank_config().enabled
```

**Test scenarios:**

- `[core.v2.rerank] enabled=false` + `--rerank` on a v2 collection → results are reranked for that call; config.toml unchanged.
- No flag passed → behavior identical to today (config decides).
- `--rerank` on a v1-only search → no crash (resolve Open Question 2 for exact UX before implementing).
- `index search --help` shows `--rerank/--no-rerank`.

**Verification:** unit tests in `tests/unit/indexed/core/v2/test_retrieval.py` (or sibling) for the override; CLI option test in the search command test file.

---

### core-v2-discoverability/3 — Clean `config set core.engine` error

**Goal:** identical single-line message across `--engine`, env var, and `config set`.

**Requirements:** R3

**Dependencies:** —

**Files:**

```
src/indexed/config/commands/set.py    # reuse composition.normalize_engine_selector
```

**Test scenarios:**

- `indexed config set core.engine v3` prints exactly `Invalid engine 'v3'; expected one of: 1, 2, v1, v2` (single line), exit 1.
- `indexed config set core.engine v2` still succeeds and stores the normalized `"2"`.
- Existing `config set core.engine` tests continue to pass (adjust assertions on error text where they currently assert the old multi-line dump, if any).

**Verification:** unit test in `tests/unit/indexed/config/` asserting the exact message string.

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

### core-v2-discoverability/5 — `index migrate --help` shows the docstring

**Goal:** `indexed index migrate --help` renders the full safety explanation + examples.

**Requirements:** R5

**Dependencies:** —

**Files:**

```
src/indexed/cli/knowledge/cli.py           # drop help= override on migrate registration
src/indexed/cli/knowledge/commands/migrate.py  # optional: delete dead module-level Typer app
```

**Test scenarios:**

- `indexed index migrate --help` output contains "v1-backup" and "rollback-safe" (or equivalent wording from the docstring) and the `Examples:` block.
- `indexed index --help`'s one-line listing for `migrate` still reads sensibly (uses the docstring's first line as short-help).

**Verification:** CLI help-output test (`tests/unit/indexed_cli/` or system-level `--help` snapshot, whichever pattern the repo already uses for other commands' help text, if any).

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
subagent pass. Two Open Questions (rerank-on-v1 UX; misplaced-option hint)
should be resolved before or during IMPL, not left implicit. See tech.md Open
Questions 3-4 for two related-but-descoped defects worth their own follow-up
issue.
