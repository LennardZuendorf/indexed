# PR #162 Review — Core V2 (LlamaIndex Engine)

**PR:** [LennardZuendorf/indexed#162](https://github.com/LennardZuendorf/indexed/pull/162) — `claude/indexed-core-v2` → `main`
**Reviewed at:** `7b1ea42` (merge-base with `main`: `9ad936f`)
**Date:** 2026-08-29

## Method

Seven independent review agents ran against a live checkout of the PR branch (dependencies
synced, embedding model pre-cached), each in its own isolated workspace, executing real CLI
commands rather than reading the diff alone:

| Dimension | Model | Mode |
|---|---|---|
| Code quality | Sonnet | diff read + live code inspection |
| Architecture | Opus | diff read + live probes against the facade |
| v1 engine e2e | Sonnet | manual CLI functional + visual test |
| v2 engine e2e | Opus | manual CLI functional + visual test, incl. live fault-injected rollback |
| Other commands (config/MCP) | Sonnet | manual CLI + live MCP stdio client |
| Product/UX | Sonnet | manual CLI walkthrough against `.spec/product.md` |
| Verify gate | Haiku | independent re-run of ruff/ty/pytest/import-graph |

The single most severe finding below (`create` silently flips a collection's engine) was
independently reproduced twice: once by the architecture agent calling the facade directly,
and once by me at the plain CLI level. The manifest-version blast-radius bug and the raw
pydantic error leak were each found independently by two different agents.

## Recommendation

**Do not merge as-is.** The core deliverable — the v2 engine itself, and the two bugs the
PR's own description claims to have fixed — is real and verified to a high standard (see
"What's confirmed solid" below, including relevance parity measured bit-for-bit and a rollback
verified via live fault injection, not just by reading the code). But this round of review found
one **confirmed silent data-loss bug** (P1-1) and two further correctness P1s, plus a cluster of
P2s concentrated in the opt-in reranking feature and the `--simple-output` JSON contract. None
of these require rearchitecting — they're contained, fixable defects — but P1-1 in particular
should never ship.

## Automated verify gate (independently re-run)

| Check | Result |
|---|---|
| `ruff check .` | ✅ clean |
| `ruff format --check .` | ✅ 341 files already formatted |
| `ty check src/indexed` | ✅ 0 diagnostics |
| `pytest -q --cov=src/indexed` | ✅ **1843 passed**, 1 skipped, 93.30% coverage (PR claimed 1835 — this run passed 8 more) |
| `check_imports.py` | ✅ passes (see architecture findings — the rule it enforces is narrower than the spec contract) |
| `.spec/` `validate.sh` | not present in this worktree (expected, not vendored) |

The gate is genuinely green. The issues below are things the gate does not — and largely
cannot — catch.

---

## P1 — Blocking

### P1-1. `index create` silently overwrites an existing collection's engine — confirmed live, reproducible data loss

`update` and `clear` both call `_resolve_existing_engine` and raise `EngineMismatchError` when
an explicit/implicit selector conflicts with a collection's on-disk manifest version. `create`
is the one routed operation that never checks — it validates only the requested engine and
dispatches. Since both engines build-aside and swap the **entire** collection directory into
place, re-running `create` against an existing name is a full replacement, not a merge.

Reproduced independently twice — by the architecture agent calling the facade directly, and by
me at the CLI level:

```
$ indexed --local --engine v2 index create files --collection flip-test --path ./corpus --force
✓ Collection 'flip-test' created with 2 documents from files (./corpus)
$ python3 -c "import json;print(json.load(open('.indexed/data/collections/flip-test/manifest.json'))['version'])"
2

$ indexed --local index create files --collection flip-test --path ./corpus --force   # no --engine
✓ Collection 'flip-test' created with 2 documents from files (./corpus)
$ python3 -c "import json;print(json.load(open('.indexed/data/collections/flip-test/manifest.json')).get('version'))"
None   # <- silently flipped back to v1, v2 index gone
```

**Scenario:** a user migrates `docs` to v2, later re-runs `indexed index create docs --source
files --source-path ./docs` (muscle memory, no `--engine`), is shown only a generic "Collection
already exists. Overwrite?" prompt with no mention of engine, confirms, and their v2 collection
is silently destroyed and replaced with a v1 one built from a `create`-time default the user
never chose. This is exactly the class of bug `EngineMismatchError` exists to prevent, on the
one code path that doesn't check for it.

**Fix shape:** `create` should call the same `_resolve_existing_engine` check as `update`/`clear`
before dispatching when the target name already exists.

### P1-2. Bulk `--engine` update aborts the whole batch, breaking its own documented contract

`run_update_loop`'s docstring states a per-collection failure must never abort the remaining
collections ("every collection is attempted and failures are collected" — foundation/6 E8).
The new `except CoreError: raise` in the engine-routing path breaks that guarantee, and nothing
upstream filters collections by engine before the loop runs:

```python
# src/indexed/cli/knowledge/commands/update_service.py:371-377
except CoreError:
    # An engine-routing precondition failure ... let it propagate ...
    raise
```

Once v1 and v2 collections coexist (the normal post-migration state this PR enables), running
`indexed update --engine v2` with no collection name hits the first mismatched collection and
hard-aborts — collections already updated get no final summary, and everything after the
failure point is never touched regardless of its own engine.

**Fix shape:** filter the "update all" candidate list by engine before the loop, or catch
`CoreError` per-item and fold it into the existing failure-collection mechanism.

### P1-3. MCP server startup can crash on a malformed config value it never uses

`mcp/server.py`'s `lifespan()` unconditionally calls `resolve_engine_selector(None,
config_service)` and stores the result in `LifespanState` — but grep confirms zero consumers of
`state["engine"]` anywhere in `mcp/tools.py` or `mcp/resources.py`. `resolve_engine_selector`
deliberately re-raises on a malformed `[core] engine` config value or bad
`INDEXED__CORE__ENGINE` env var (correct behavior for `create`), but this call is **not**
wrapped the way every other config read in the same function is (`_get_config` swallows
exceptions and returns defaults, with a comment explicitly citing "rather than letting a
malformed/unreadable config.toml crash server startup"). A write-time-only setting can now take
down a read-only MCP server (no `create` tool exists over MCP) at startup.

**Fix shape:** either wrap the call the same way `_get_config` is wrapped, or delete the dead
`engine` field from `LifespanState` entirely if nothing needs it yet.

---

## P2 — Should fix before merge

### Reranking (opt-in, but broken in three ways when enabled)

- **Breaks the "one comparable relevance scale" the PR itself claims (R11).**
  `_HIGHER_IS_BETTER = frozenset({"cosine", "rerank"})` treats a raw, unbounded cross-encoder
  logit as if it were already a cosine similarity in [0,1] and passes it through unchanged.
  Measured logits ranged −11.23 to +6.27 in testing; every v2 chunk with a positive logit floats
  above every v1 result regardless of actual relevance, and every v2 chunk with a negative logit
  sinks below all of them — verified with a real relevant v2 chunk ranked 34th, below a page of
  irrelevant v1 chunks, in mixed search.
- **Reranked scores are mislabeled `"cosine"`, not `"rerank"`, in the consumer-facing envelope.**
  `retrieval.py` correctly tags `scoreKind: "rerank"` internally, but `mcp/formatting.py`
  derives the label from the `higher_is_better` boolean instead of forwarding the real kind, so
  both the MCP JSON envelope and (by extension) any agent consuming it are told a value like
  6.27 is a cosine similarity.
- **Corrupts `--simple-output` JSON.** Enabling rerank causes an HF-Hub rate-limit warning to be
  written to stdout ahead of the JSON body (`indexed --simple-output index search ... 2>/dev/null`
  still fails to parse as JSON) — `--simple-output` is documented as machine-readable output.

### Manifest-version blast radius — found independently by both the architecture agent and the v2 e2e agent

One collection with an unrecognized `version` marker (e.g. a collection written by a future
`indexed` release, then opened by an older install) makes `index inspect` and `index search`
fail **entirely for every collection**, not just the unreadable one — strictly worse than how
the same code already handles a completely unparseable manifest (which is silently omitted, not
fatal). This directly contradicts `retrieval.py`'s own stated per-collection-failure contract.

### `--simple-output` JSON contract is inconsistently honored

- `config get --simple-output core.engine` skips the "effective default" resolution the
  rich-text path applies (`config get core.engine` shows `1 (default)`; the JSON path returns
  `null`), silently disagreeing with the code's own comment that `core.engine` "always has an
  effective value even when unset."
- `index remove --simple-output` on a missing collection ignores `--simple-output` entirely and
  prints a Rich panel instead of JSON — the sibling commands (`update`/`search`/`migrate`) all
  get this right in the same situation.

### Config validation is inconsistent between surfaces — found independently by both the product agent and the v2 e2e agent

`config set core.engine <bad-value>` leaks a raw, multi-line pydantic `ValidationError` dump
(`str(exc)` on a pydantic error, not the custom validator message) instead of the clean
`Invalid engine 'v3'; expected one of: 1, 2, v1, v2` the `--engine` flag and env-var paths
produce for the identical input. More broadly, `resolve_embedding_config`/
`resolve_search_config`/`resolve_rerank_config` in `core/v2/_common.py` wrap config reads in a
bare `except Exception: return DefaultConfig()` — an out-of-range value like
`core.v2.search.score_threshold=5.0` (accepted by `config set`, which only warns, doesn't block)
is silently discarded on every search with zero signal, inconsistent with the engine selector's
deliberately fail-loud design.

### Import-boundary contract is narrower than the spec, and this PR adds the first violation above the facade

The spec states "no code above the facade may import `core.v1.*` or `core.v2.*` directly," but
`check_imports.py`'s only deep rule is `core/v2 ↛ core/v1`; there is no rule for `cli`/`mcp`
reaching into `core.v1.*`/`core.v2.*`, and `mcp` isn't in the forbidden-edges map at all. This
PR adds the first such violation: `cli/composition.py` now imports `core.v2.config_models`
directly at module scope (alongside pre-existing v1 violations in `composition.py`, `init.py`,
`app.py`, `create.py`, and `mcp/server.py`). The gate passes cleanly while the contract is
broken, and `CoreEngineConfig` — the facade-level `[core] engine` setting — was placed inside
the frozen `core/v1/config_models.py`, so retiring v1 later would take the engine selector with
it.

### `--engine` is invisible from the `--help` a user would actually check

`--engine` only exists as a root-level flag; it doesn't appear in `index create --help` or
`index create files --help`, and placing it after the subcommand (where those help texts imply
options go) fails with a bare `No such option: --engine`.

### v1 "Top Result" can display a worse-scored match than "Other Matches" below it

Reproducible on low-signal queries (empty string, nonsense terms): the headline "Top Result"
panel appears to apply this PR's new content-free-chunk filter (`_is_content_free`, a genuine,
correct improvement on its own), but the "Other Search Query Matches" list below it does not
apply the same filter — so the list can show a strictly better-scored entry than the one
labeled "best match" just above it. This is v1 output, but the filter that likely introduced the
inconsistency is new in this PR (`search_render.py`).

### `_is_content_free` doesn't cover an absolute-path chunk (not a v2 regression, but the fix is incomplete)

Confirmed present identically in v1 and v2 for the same source content — a chunk whose
`indexedData` is a raw absolute filesystem path can still be promoted as the "Top Result
Excerpt," leaking local directory layout. Pre-existing in the file connector, out of scope as a
PR-introduced bug, but worth folding into the same fix since this PR already touched this exact
function for a closely related case.

---

## P3 — Polish (not blocking)

- `mcp inspect` reports only aggregate tool/resource counts, with no engine info and no
  component names — no way to confirm which engine an MCP server resolved at startup from the
  tool itself.
- `mcp inspect`'s `mcp_version` is always `"Unknown"` (pre-existing, not introduced by this PR).
- An invalid root `--engine` value ignores `--simple-output` and prints plain text.
- Migration reports `backup_purged=True` even when `shutil.rmtree(..., ignore_errors=True)`
  silently failed to remove the backup (no existence check afterward, unlike `persist.py`'s
  `replace_dir`).
- `config set core.engine <bad> --dry-run` shows no error — the `CoreEngineConfig` validation
  block sits after the dry-run early-return.
- `_unified_relevance`/`_HIGHER_IS_BETTER` are duplicated verbatim between `search_render.py`
  and `mcp/formatting.py` (both files' own comments acknowledge this) — a future change to one
  silently diverges from the other.
- Detail cards are hardcoded to 60 columns (`theme.py`), truncating the engine/model descriptor
  on `inspect`/`migrate` panels regardless of actual terminal width.
- Engine-mismatch errors print as bare styled text with no `✗` panel, unlike every other CLI
  error (including migration's own errors).
- `index update` leaks a raw compiled regex object (`(?s:.*)\Z`) into its "Included Patterns"
  summary row, misaligned against the rows around it.
- `index create files --help`'s option table misaligns and mid-word-truncates
  `--no-respect-gitignore` at 80 columns; not confirmed pre-existing.
- `index inspect` (list view) truncates a `Path` value that fits and displays in full in
  `inspect <name>` (detail view), for the same collection.
- `index update` gives no add/remove breakdown, and `core/v2/ingestion.py` has zero log calls at
  any verbosity, so the PR's advertised hash-based incremental logic is invisible to a user even
  with `--verbose`.
- `inspect`'s collection listing order depends on which collection happened to be created first
  per engine group, so adding one collection can reorder the entire list.
- Reranking has no CLI flag and isn't mentioned in `index search --help` — the only way to
  discover or enable it is `config set core.v2.rerank.enabled true`.
- Query-echo markup escaping renders a visible backslash (`list\[int]`) in the search header —
  correct behavior (no crash, per the R7 regression guard) but slightly rough presentation.
- Migration folder discovery's `.v1-backup` exclusion pattern is duplicated in four places
  across `core/engine.py` and `core/v2/_common.py`/v1's own discovery sites, and the copies
  already disagree in one place — a retained backup can surface as a phantom searchable
  collection named `<name>.v1-backup` after the original is removed.
- v2's embedding-provider and version-pin fields are recorded in the manifest but never read
  back or dispatched on (unlike the vector-store field, which fails loud on an unknown value) —
  latent risk once a second embedding provider exists, not a bug today with only one provider.

---

## What's confirmed solid — don't second-guess this

- **Relevance parity is real, not just claimed.** Measured bit-for-bit: v1's squared-L2
  converted via `1 - d²/2` matches v2's native cosine to 6 decimal places across all 18 chunks of
  a shared test corpus, in identical rank order — the PR's headline "metadata was polluting v2
  embeddings" fix genuinely holds.
- **Rollback was verified live, not by reading the code.** The v2 e2e agent monkeypatched
  `migration._swap` to raise `OSError` mid-migration against a real v1 collection and confirmed
  a byte-identical restore (14/14 files, sha256-verified) with no leftover staging or backup
  directories.
- Migration dry-run is genuinely inert, backups are correctly hidden from `inspect`/`search`,
  `--purge-backup` only fires after a confirmed successful swap, and every migration error path
  (already-v2, missing collection, pre-existing backup) gives a clear, actionable message.
- Engine-mismatch guards work correctly (both directions) for `update`/`search`/`status`/
  `inspect` — just not for `create` (P1-1).
- `core/v2` is genuinely isolated from `core/v1` at the level `check_imports.py` actually checks
  (a real, self-tested AST rule), and neither package imports shared dataclasses from the other.
- v1 is functionally unaffected: full lifecycle (create/inspect/search/update/remove) regression
  clean, both known regression-guarded cases (`list[int]`, empty query) still don't crash.
- Env-var and `config set` engine-selector crashes (the PR's second claimed fix) are genuinely
  fixed, verified on both paths.
- The MCP server was driven live over real stdio (not just read) against genuine v1 and v2
  collections — `search`, `search_collection`, and all three resources returned correct,
  sanely-ranked, correctly-formatted results (outside the rerank-specific bugs above).
- Lazy ML-import discipline is honored throughout the v2 code — startup stays fast (~2.3s cold).
- Lockfile/worktree hygiene: no unintended writes to the reviewed worktree across any agent's
  testing (confirmed via `git status --porcelain`).

## Product/UX summary

The v1/v2 coexistence itself is well-scoped for this project's stated solo-dev/small-team
target user (v1 stays default, v2 adds zero ambient complexity unless summoned), and the
migration command's safety UX — dry-run preview, explicit backup path, specific
next-command-to-run error messages — is genuinely good, verified through real use rather than
just reading the docstring. The gaps are all discoverability/consistency, covered above
(`--engine` invisible from subcommand help, raw pydantic leak, reranking undiscoverable). No
CHANGELOG exists in the repo to have skipped, and the feature has no footprint in the README,
which is a real but low-severity gap given the project already points to an external docs site.

## Not covered by this round

- Jira/Confluence/Outline connectors under v2, and `--from-source` migration (no credentials
  available in this sandbox — only the `files` connector was exercised).
- MCP over HTTP/SSE/streamable-http transports (only stdio was exercised).
- Concurrency (two processes updating/migrating the same collection simultaneously).
- Realistic-scale corpora — testing used small synthetic corpora (6-8 files); the ~4x on-disk
  growth observed for v2 vs v1 on identical content was noted but not investigated as a defect.
- The `UnknownVectorStoreError` path (only one store implementation exists today, so nothing to
  dispatch between in a live test).
