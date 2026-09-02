---
type: feature-plan
feature: core-v2-rendering-fixes
sibling: tech.md
parent: ../../plan.md
updated: 2026-09-02
---

# Feature: Core v2 Rendering Fixes — Implementation Plan

Fix all eight confirmed [issue #187](https://github.com/LennardZuendorf/indexed/issues/187)
findings behind regression tests. Units are grouped by defect cluster/file overlap
and are independent (disjoint files, except the shared-file note in Unit 1/5), so
they can run in parallel. All eight are P3 polish/consistency — no severity-based
sequencing is needed — except R5 (Unit 4), which corrects a test that currently
encodes the bug as expected behavior, and R4 (Unit 3), which needs a go-ahead on
a public flag rename before coding.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Starts now — Feature 17 (Core v2 discoverability, issue #188) is
`DONE`. Depends on no other feature's units; every fix site already exists on
`claude/issue-187-review-fixes-b2mutf`.

---

## Requirements Trace

| ID | Requirement | Unit |
|---|---|---|
| R1 | [Engine-mismatch errors render as a panel](product.md#requirement-engine-mismatch-errors-render-as-a-panel-like-every-other-cli-error) | rendering-fixes/1 |
| R2 | [Detail cards size to the terminal](product.md#requirement-detail-cards-size-to-the-terminal-not-a-fixed-60-columns) | rendering-fixes/1 |
| R3 | [Included Patterns shows the user's own pattern text](product.md#requirement-index-updates-included-patterns-row-shows-the-users-own-pattern-text) | rendering-fixes/2 |
| R4 | [`--help` renders without mid-word truncation](product.md#requirement-index-create-files---help-renders-its-option-table-without-mid-word-truncation) | rendering-fixes/3 |
| R5 | [Other Matches never outranks Top Result](product.md#requirement-other-search-query-matches-never-outranks-top-result) | rendering-fixes/4 |
| R6 | [Rendered scores are labeled with their scale](product.md#requirement-rendered-scores-are-labeled-with-their-scale) | rendering-fixes/4 |
| R7 | [inspect list view shows Path in full](product.md#requirement-inspect-list-view-shows-a-collections-path-in-full) | rendering-fixes/5 |
| R8 | [inspect's collection groups render in a stable order](product.md#requirement-inspects-collection-groups-render-in-a-stable-order) | rendering-fixes/5 |

---

## Open Question — resolve before coding Unit 3

**R4 fix shape:** rename the CLI-facing flag pair
`--respect-gitignore/--no-respect-gitignore` → recommended
`--gitignore/--no-gitignore` (blast radius confirmed tiny: one code site,
`_create_options.py:126`, plus two non-functional docstring comments in
`test_create.py`; the internal `respect_gitignore` param/config name is untouched).
Alternative (patching Typer's vendored `rich_utils` column-width calculation) is
not recommended — higher risk for a single-flag problem. **Needs a yes/no from the
repo owner before Unit 3 starts**, since it's a public CLI surface change even
though the project is pre-1.0 alpha.

---

## Unit IDs

Units are `rendering-fixes/n`, assigned once and never renumbered. Cite IDs in
commits (`fix(cli): rendering-fixes/1 …`).

---

### rendering-fixes/1 — CLI panel & card-width consistency

**Severity:** P3 · **Goal:** engine-mismatch errors render as a `✗` panel; detail
cards size to the terminal instead of a fixed 60 columns.

**Requirements:** R1, R2

**Dependencies:** —

**Files:**

```
src/indexed/cli/app.py                       # top-level IndexedError catch: use print_error, not bare console.print
src/indexed/cli/utils/components/theme.py    # get_detail_card_width(): derive from terminal, clamp [min,max]
```

**Test scenarios:**

- `EngineMismatchError` raised from a command reaches `main()` and renders inside a bordered panel (assert on `Panel`/border chars in captured output, not just message text).
- `get_detail_card_width()` returns a value proportional to a mocked wide terminal, and stays clamped at the floor for a mocked narrow one.
- `inspect <name>` on a v2 collection with a long model descriptor renders on one line at a wide terminal.

**Verification:** new tests in `tests/unit/indexed/test_app.py::TestMainFunction` (R1) and `tests/unit/indexed/cli/utils/test_markup_safety.py` or a new sibling file (R2, `create_detail_card` is already exercised there).

---

### rendering-fixes/2 — Included Patterns display fix

**Severity:** P3 · **Goal:** `index update`'s "Included Patterns" row shows the
user's own pattern text, never an `fnmatch.translate()` regex string — fixed at
the root (schema validator), with a defensive fallback for already-persisted
collections.

**Requirements:** R3

**Dependencies:** —

**Files:**

```
src/indexed/connectors/files/schema.py             # normalize_patterns: keep original text, not the translated form
src/indexed/cli/knowledge/commands/update_service.py  # defensive default-wildcard recognition for legacy manifests
```

**Test scenarios:**

- New collection created with default patterns (`*`): manifest's `includePatterns` stores `["*"]`, not `["(?s:.*)\\Z"]`; `update` displays `"* (all files)"`.
- New collection created with a custom glob (`*.py`): manifest stores `["*.py"]`; `update` displays `"*.py"`, not its translated regex form.
- A manifest already carrying the legacy translated default (simulated) still displays `"* (all files)"` via the display-time fallback.
- Matching behavior is unchanged for both old-style and new-style persisted patterns (`_compile()` still resolves correctly either way).

**Verification:** new tests in `tests/unit/indexed/connectors/files/` (schema) and `tests/unit/indexed/knowledge/commands/test_update.py` (display).

---

### rendering-fixes/3 — `--help` truncation fix

**Severity:** P3 · **Goal:** `index create files --help` renders the gitignore
flag pair in full at 80 columns.

**Requirements:** R4

**Dependencies:** Open Question above must be resolved first.

**Files:**

```
src/indexed/cli/knowledge/commands/_create_options.py   # flag string rename
```

**Test scenarios:**

- `indexed index create files --help` at a redirected/mocked 80-column terminal contains the full flag name with no `…` truncation.
- The renamed flag still round-trips correctly (`--gitignore` / `--no-gitignore` both set `respect_gitignore` as before) — extend existing gitignore-support tests, don't duplicate them.

**Verification:** `tests/unit/indexed/connectors/files/test_gitignore_support.py`, `tests/unit/indexed/knowledge/commands/test_create.py` (update the two R9 docstring references to the new flag text).

---

### rendering-fixes/4 — Search result correctness (content-free filter parity + score labels)

**Severity:** P3 · **Goal:** "Other Matches" never outranks a filtered "Top
Result"; rendered scores carry a cosine/rerank label.

**Requirements:** R5, R6

**Dependencies:** —

**Files:**

```
src/indexed/cli/knowledge/commands/search_render.py   # shared content-free-filtered pool; thread scoreKind into render calls
```

**Test scenarios:**

- Mixed content-free/real chunks: "Other Matches" contains no content-free chunk that outranks "Top Result" (**corrects** the existing `test_other_matches_excludes_promoted_top` assertion at `test_search.py:878`, which currently expects the buggy ordering).
- All-content-free edge case: Top Result still falls back to the first chunk, no crash, no empty state (`test_top_result_falls_back_to_first_chunk_when_all_content_free` stays green).
- A result with `scoreKind: "rerank"` renders a distinguishing label; a `scoreKind: "cosine"` result does not get mislabeled.

**Verification:** `tests/unit/indexed/knowledge/commands/test_search.py`, class `TestFormatSearchResults`.

---

### rendering-fixes/5 — inspect list-view path + stable group order

**Severity:** P3 · **Goal:** list-view `Path` renders as fully as the detail
view; engine groups sort deterministically.

**Requirements:** R7, R8

**Dependencies:** —

**Files:**

```
src/indexed/cli/knowledge/commands/inspect.py       # (indirect — consumes cards.py / engine.py; no logic change expected here)
src/indexed/cli/utils/components/cards.py           # create_info_rows_with_spacing: stop ellipsis-truncating Path row
src/indexed/core/engine.py                          # sorted(groups.items()) at inspect()/status() group-emission sites
```

**Test scenarios:**

- Three collections listed together via `index inspect` (no name): a long path that renders in full in `index inspect <name>` also renders in full in the list view.
- `_group_names_by_engine` output consumed by `inspect()`/`status()` emits groups in ascending engine-version order regardless of collection creation/migration order (extend `test_engine_facade_v2.py::test_mixed_v1_v2_status_lists_both` to assert order).

**Verification:** `tests/unit/indexed/knowledge/commands/test_inspect.py` (new — no truncation coverage exists today), `tests/unit/indexed/core/test_engine_facade_v2.py`.

---

## Verification (whole feature)

Full gate from repo root, must pass after every unit and again at the end:

```bash
uv run ruff check . --fix && uv run ruff format
uv run ty check src/indexed
uv run pytest -q --cov=src/indexed
python scripts/check_imports.py
```

## Compound

On completion: add a `## Feature 18: Core v2 rendering fixes (issue #187)` row to
root `.spec/plan.md`'s Feature Sequence table; fold any load-bearing pattern
(e.g. "detail-card width must derive from the terminal, never hardcode") into
`.spec/lessons.md`; retire this feature folder once merged, per the precedent set
when `review-remediation` was retired into root tech specs.
