---
type: feature-tech
feature: core-v2-rendering-fixes
sibling: product.md
parent: ../../tech.md
updated: 2026-09-02
---

# Feature: Core v2 Rendering Fixes — Architecture

How each issue #187 finding is fixed: the confirmed defect site (file:line at
HEAD `7b63412` on `claude/issue-187-review-fixes-b2mutf`), the mechanism, and the
fix shape. Line numbers are anchors — verify against the file before editing.
Every item below was independently confirmed present at HEAD by direct code
reading (four parallel investigation passes), not inferred from the review doc
alone.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Files

```
src/indexed/cli/app.py                                          # top-level IndexedError catch prints bare text (R1)
src/indexed/cli/utils/components/alerts.py                      # print_error() — the panel pattern to reuse (R1)
src/indexed/cli/utils/components/theme.py                       # get_detail_card_width() hardcoded 60 (R2)
src/indexed/cli/utils/components/cards.py                       # create_detail_card / create_info_rows_with_spacing (R2, R7)
src/indexed/connectors/files/schema.py                          # normalize_patterns eagerly translates globs to regex (R3)
src/indexed/cli/knowledge/commands/update_service.py             # displays the already-translated pattern verbatim (R3)
src/indexed/cli/knowledge/commands/_create_options.py            # --respect-gitignore/--no-respect-gitignore flag text (R4)
src/indexed/cli/knowledge/commands/search_render.py              # _is_content_free applied to Top Result only; no scoreKind label (R5, R6)
src/indexed/cli/knowledge/commands/inspect.py                    # list view Columns-wraps cards; engine groups unsorted (R7, R8)
src/indexed/core/engine.py                                       # _group_names_by_engine / inspect() / status() dict-order groups (R8)
```

---

## Implementation Detail

### R1 — engine-mismatch errors bypass the panel (CONFIRMED)

`EngineMismatchError`/`UnknownEngineVersionError` (`core/errors.py:19,38`) subclass
`CoreError` → `IndexedError`. No per-command `try/except` catches them — e.g.
`search.py:280,302` call `svc_search(...)` unguarded, and `update_service.py:371-377`
deliberately `except CoreError: raise` to let them escape to the single top-level
handler. That handler is `app.py:250`, inside `main()`'s
`except IndexedError as exc:` block:

```python
_shared_console.print(escape(format_cli_error(exc)), style=get_error_style())
```

— bare styled text, not a panel. The panel pattern to match already exists:
`print_error(message: str)` at `cli/utils/components/alerts.py:63-82` builds a
`Text` with the `✗` icon and renders via
`Panel(..., border_style=get_error_style(), padding=get_card_padding(), width=get_detail_card_width())`
— this is what `migrate.py:144` (`print_error(f"Failed to migrate '{collection}': {e}")`)
already uses, and what the issue holds up as the standard to match.

**Fix:** in `app.py:250`, replace the bare `console.print(...)` call with
`print_error(escape(format_cli_error(exc)))` (or the equivalent `Panel`
construction), keeping the existing `escape()` and `exit_code_for(exc)`/`sys.exit`
flow unchanged. Single fix point — no per-command changes needed.

### R2 — detail cards hardcoded to 60 columns (CONFIRMED)

`get_detail_card_width()` at `theme.py:53-55` returns a literal `60`. No dynamic
sizing exists anywhere in the codebase (`console.width`/`get_terminal_size`/
`console.size` : zero hits in `src/indexed`). `get_grid_card_min_width()`
(`theme.py:58-60`, `30`) is a separate fixed minimum, not evidence of an existing
dynamic pattern. `create_detail_card()` (`cards.py:105-128`) is the single funnel —
it's the only caller of `get_detail_card_width()`'s result via
`create_info_card(..., width=...)` (line 126) — and every detail-card call site
routes through it: `inspect.py:161,187`, `migrate.py:197`, `config/commands/
{set.py:84,166; get.py:106}`, `cli/utils/conflict_prompt.py:82`,
`search_render.py:284`. `print_success/print_error/print_warning/print_info`
(`alerts.py:58,80,102,124`) also call `get_detail_card_width()` directly, so
fixing the one function fixes R1's panels too.

**Fix:** change `get_detail_card_width()` to derive from the live terminal (the
shared `console` singleton in `cli/utils/console.py`, or
`shutil.get_terminal_size()`), clamped to a sane `[min, max]` range (e.g.
`[60, 100]`) so narrow terminals still don't overflow and very wide ones aren't
absurdly stretched. No call-site changes required.

### R3 — raw regex leaks into "Included Patterns" (CONFIRMED — root cause traced past the display layer)

The leak is **not** a display-layer string-join bug on a `re.Pattern` object (that
would repr as `re.compile('(?s:.*)\\Z')`, not the bare `(?s:.*)\Z` the issue
reproduces). It's a plain **string** — the literal output of `fnmatch.translate()`
— that was already substituted for the user's original pattern at config-validation
time, upstream of display:

- `connectors/files/schema.py:66-84`, `FileSystemConfig.normalize_patterns`
  (a `field_validator(mode="before")`): for each pattern, tries `re.compile(bare)`;
  on `re.error` (a bare glob like `"*"` or `"*.py"` isn't valid regex — `"*"` alone
  raises "nothing to repeat"), falls back to `prefix + fnmatch.translate(bare)`
  (line 83) — and **that translated string is what's kept**, not the original.
- This translated form flows unchanged: `FilesDocumentReader.__init__`
  (`files_document_reader.py:69`) stores it as `self.include_patterns`, which is
  persisted into the manifest verbatim at line 168
  (`"includePatterns": self.include_patterns`).
- `update_service.py:86-89` reads it back from the manifest and joins it directly:
  ```python
  include_patterns: list[str] = reader_config.get("includePatterns") or ["*"]
  positive = [p for p in include_patterns if not p.startswith("!")]
  patterns_display = "* (all files)" if positive == ["*"] else ", ".join(positive)
  ```
  The `positive == ["*"]` special case is **dead code** for any real manifest —
  by the time a pattern reaches here, `"*"` has already become
  `"(?s:.*)\Z"` upstream, so the literal string `"*"` can never survive to this
  comparison. This exactly explains the reported symptom.
- `_compile()` (`files_document_reader.py:90-96`) already independently
  re-derives the match pattern from a raw string via the identical
  try-regex/except-translate logic used for *matching* — meaning the eager
  translation in the schema validator is not needed for correctness, only for
  early validation that the pattern is at least parseable one way or the other.
- Why `index create files` doesn't show this row at all: its summary path
  (`_create_helpers.py:97 execute_create_command`) never calls
  `_display_collection_update_header()` — that helper (and this bug) is unique to
  `update_service.py`.

**Fix (two parts, both small):**
1. In `schema.py:normalize_patterns`, stop keeping the translated form for the
   glob branch — validate parseability (`fnmatch.translate(bare)` still called to
   confirm it doesn't raise) but store `prefix + bare` (the original text), since
   `_compile()` at match time already re-derives the working regex from the raw
   string via the same fallback. This makes `positive == ["*"]` (and any custom
   glob) display correctly for every *newly written* manifest, with no schema
   version bump — old manifests with already-translated patterns still match
   correctly (`_compile` accepts a valid-regex string as-is).
2. Defensive display-time fallback in `update_service.py` for *already-persisted*
   collections written under the old behavior: recognize
   `fnmatch.translate("*")`'s known output as equivalent to the default and label
   it `"* (all files)"` too, so existing collections' most common case (unchanged
   default patterns) renders correctly immediately, without requiring a
   create/update cycle.

No test currently covers this; new tests belong in
`tests/unit/indexed/connectors/files/` (schema validator) and
`tests/unit/indexed/knowledge/commands/test_update.py` (display).

### R4 — `--help` mid-word truncation (CONFIRMED — reproduced live)

Reproduced directly: `COLUMNS=80 uv run indexed index create files --help` renders

```
│ --respect-gitignore      --no-respect-gitign…          Respect .gitignore    │
```

No custom Rich/Click help formatter exists in this codebase (`rich_click` is not a
dependency; `grep` for `MAX_WIDTH`/`max_content_width`/custom column config in
`cli/` returns nothing but an unrelated `STYLE_COMMANDS_TABLE_FIRST_COLUMN`
constant at `app.py:57`). This is Typer's stock `rich_utils` option-table
renderer: the "negative flag" column's width is sized to fit the panel's other
options (`--no-fail-fast` = 14 chars, `--no-cache` = 10 chars both fit), and
`--no-respect-gitignore` (22 chars) is the one outlier that overflows it, so Rich's
default `overflow="ellipsis"` truncates it mid-word. The option is defined at
`_create_options.py:126`:
`typer.Option("--respect-gitignore/--no-respect-gitignore", help=...)`.

**Blast radius check for a rename:** the literal flag string
`--respect-gitignore`/`--no-respect-gitignore` appears at exactly one code site
(`_create_options.py:126`) plus two docstring comments in
`test_create.py:123,203` (referencing requirement R9 by number, not asserting the
flag text). The Python-side identifier `respect_gitignore` (used across 8 source +
3 test files as the config/param name) does **not** need to change — only the
user-facing flag string.

**Fix (recommended, flagged for CONFIRM — this is a public CLI flag rename, even
though `respect_gitignore` internals stay the same):** shorten the flag pair to
something within the width budget other flags already fit (e.g.
`--gitignore/--no-gitignore`, whose negative form at 14 chars matches
`--no-fail-fast`). Alternative considered and not recommended: patching Typer's
internal `rich_utils` column-width calculation — higher risk (vendored upstream
code, not owned by this repo) for a one-flag problem. The project is pre-1.0
alpha (`plan.md`: "Breaking changes still allowed"), so a flag rename is in
scope.

### R5 — "Other Matches" outranks "Top Result" (CONFIRMED — existing test encodes the bug)

`search_render.py`:
- `_is_content_free` defined at lines 61-83.
- Only call site: line 205 —
  `top = next((c for c in all_chunks if not _is_content_free(c)), all_chunks[0])`.
- "Other Matches" build: line 218 — `others = [c for c in all_chunks if c is not top][:4]`.
  No `_is_content_free` call on this path; it only excludes the exact `top` object
  by identity. `all_chunks` is pre-sorted best-first (line 193), so any
  content-free chunk(s) skipped by the `next()` on line 205 survive unfiltered
  into `others`, ranked above wherever `top` actually landed.

**Existing test currently asserts the buggy behavior as correct:**
`tests/unit/indexed/knowledge/commands/test_search.py:834-878`,
`test_other_matches_excludes_promoted_top` — builds chunks scored `0.1`
(content-free), `0.3` (real), `0.5` (real); top becomes `0.3`; asserts
`others == [0.1, 0.5]` (line 878). This assertion must change as part of the fix.

**Fix:** build one filtered pool feeding both sections:
```python
non_free = [c for c in all_chunks if not _is_content_free(c)]
top = non_free[0] if non_free else all_chunks[0]
others = [c for c in (non_free or all_chunks) if c is not top][:4]
```
Preserves the existing all-content-free fallback
(`test_top_result_falls_back_to_first_chunk_when_all_content_free`, line 796) and
the existing `[No excerpt available]` messaging (line 307).

### R6 — no scoreKind label on rendered scores (CONFIRMED — data already available, just not threaded through)

`scoreKind` is produced at `core/v2/retrieval.py:214,218` (`"cosine"` from
manifest, or `RERANK_SCORE_KIND = "rerank"` from `core/v2/manifest.py:39`). The
CLI reads it at `search_render.py:139` but immediately collapses it to a bool and
discards the string:
`higher_is_better_by_collection[collection_name] = collection_results.get("scoreKind") in _HIGHER_IS_BETTER`.
Score is rendered with no label at the meta-card "Score"/"Relevance" rows
(lines 260-266, 275) and the compact-list score (lines 327-331, 339) — both fed
only the boolean dict (call sites at lines 209/230/246/320), never the raw string.

**Fix:** thread the raw `scoreKind` string alongside the boolean (e.g. a parallel
`score_kind_by_collection: Dict[str, str]`) into
`_show_top_result_split_cards`/`_show_compact_match`, and append a label to the
rendered score string, e.g. `f"{score:.4f} ({kind})"`. No `scoreKind: "rerank"`
case exists yet in `test_search.py` — add one.

### R7 — inspect list view truncates `Path` that the detail view shows in full (CONFIRMED)

Not a `Table.add_column("Path", ...)` bug — `Path` is a row inside a generic
2-column grid, not a dedicated column, and the truncation comes from the
**layout container** the list view uses that the detail view doesn't:

- List view: `inspect.py:96-129` (`_show_brief_list`). Each collection becomes
  `create_info_card(title=coll.name, rows=rows)` (line 118, `width=None` → auto),
  and all cards are wrapped in `Columns(panels, equal=True, expand=True)`
  (line 122).
- Row rendering: `cards.py:39-55` (`create_info_rows_with_spacing`), line 44:
  `table.add_column(justify="right", ratio=2)` — no `no_wrap`/`overflow`/
  `max_width`, so it inherits Rich's `Column` default `overflow="ellipsis"`.
- Detail view (contrast): `inspect.py:174-189` (`format_collection_detail`) calls
  `create_detail_card(...)` and `console.print(card)` directly — one card, never
  `Columns`-wrapped. `create_detail_card` fixes `width=get_detail_card_width()`
  (R2's hardcoded-60 bug — a separate, already-scoped issue, not the cause here).

**Mechanism:** `Columns(equal=True, expand=True)` measures each panel's natural
width, forces every panel to the widest one, then fits as many equal columns as
possible into the terminal width — with N collections, each card gets roughly
`terminal_width / N`, squeezing the `ratio=2` value column below what the path
needs. The detail view is never squeezed this way. Reproduced: 3 collections at a
140-column terminal truncated a 37-character path to `.../my-project…`, while the
same collection's detail view showed it in full.

**Fix:** either (a) give the Path row's value column `no_wrap=True` with an
explicit `overflow="fold"`/no truncation and let the card widen instead of the
text truncating, or (b) special-case the `Path` row to render below the label
(full width) rather than in the constrained right-hand value column when in the
`Columns`-wrapped list layout. Prefer (a) if it doesn't break the existing
side-by-side card layout for short values — verify against
`tests/unit/indexed/knowledge/commands/test_inspect.py` (no truncation/width
coverage today; add it here).

### R8 — inspect's engine-group order is unstable (CONFIRMED — reproduced)

- `core/engine.py:207-239` (`_group_names_by_engine`): line 226,
  `groups: dict[EngineVersion, List[str]] = {}`; line 238,
  `groups.setdefault(version, []).append(name)`, iterating names from
  `resolved = collection_names or _existing_collection_names(...)`.
- Name source `_existing_collection_names` (`engine.py:120-142`), line 135:
  `for child in sorted(base.iterdir())` — alphabetical by collection name, **not**
  by engine.
- Consumers: `inspect()` (`engine.py:609-642`), lines 635, 639-641 —
  `for grp_version, grp_names in groups.items(): out.extend(...)`. Same pattern in
  `status()` at lines 563-569 (search) and 599-606.

**Mechanism:** dict insertion order (Python 3.7+ guarantee) = the engine version of
whichever alphabetically-first collection name is encountered first — not a
stable key. Reproduced: before migration, groups = `[('1', ['beta','gamma'])]`;
after migrating alphabetically-first `alpha` to v2, groups =
`[('2', ['alpha']), ('1', ['beta','gamma'])]` — the entire v1 group drops below a
brand-new single-item v2 group.

**Fix:** `for grp_version, grp_names in sorted(groups.items()):` (ascending
version string) at all three sites — `inspect()` line 640, `status()` line 568,
and the search-listing block at lines 563-569. No engine-registry change needed.
Regression-test home: `tests/unit/indexed/core/test_engine_facade_v2.py` — extend
`test_mixed_v1_v2_status_lists_both` (line 232) to assert order, since it
currently doesn't.

---

## Key Technical Decisions

1. **R2 and R7 share a fix point (`cards.py`) but touch different functions** —
   `create_detail_card`/`get_detail_card_width` (R2) vs.
   `create_info_rows_with_spacing` (R7). Independent, but land as separate commits
   with care about merge order if worked in parallel.
2. **R3's true fix is in the connector schema, not the CLI display layer** — the
   review titled this a "rendering" bug, but the display code
   (`update_service.py`) is a symptom; the eager-translation validator in
   `connectors/files/schema.py` is the cause. Fixing only the display layer (e.g.
   detecting `(?s:.*)\Z` and relabeling it) would leave every *custom* glob
   pattern (not just the default) still showing raw regex — the schema fix is
   the general one.
3. **R4 is the one item needing an explicit human call before IMPL** — it's a
   public CLI flag rename (low blast radius, confirmed: one code site + two
   comments), not a pure rendering tweak. Recommended default:
   `--gitignore/--no-gitignore`. Flagged in `plan.md` as an open question.
4. **Every unit ships a red→green regression test**, matching each confirmed
   trigger above — including correcting the one existing test (R5) that currently
   encodes the bug as expected behavior.
