---
type: lessons
scope: project
updated: 2026-07-08
---

# Lessons Learned

Accumulated mistakes and earned defaults. Read at session start.

---

## Architecture audit (2026-07-03)

- **Graph before polish.** Fix `core→connectors` and extract `indexed-protocols`
  before refactoring services or splitting command files. v2 depends on this.
- **App is the composition root.** Config registration, logging, connector wiring
  belong in `bootstrap.py` + `runtime.py`, never at library import time.
- **`resolve_collections_context()` is the only storage API.** Do not revive
  heuristics like “prefer local if non-empty collections dir”.
- **Singleton `mode_override` must rebuild.** `ConfigService.instance()` recreates
  when `mode_override` changes on a subsequent call; use `reset=True` in tests.
- **Migrate before delete.** Jira Server must use `UnifiedJiraDocumentReader`
  before removing deprecated wrapper modules in `/8`.
- **Registry lookup uses `cfg.type` verbatim.** Do not normalize `jiraCloud` → `jira`
  when resolving connector class — cloud and server connectors differ.
- **`localFiles` sets `sources.files.path`, not `.url`.** in `build_connector()`.
- **Lazy imports after `/5`.** Config classes live in `connectors.*.schema`; package
  `__init__.py` no longer re-exports them — update `create.py` `__getattr__` paths.
- **Empty dict is falsy for registry injection.** `build_connector(..., registry={})`
  falls back to full registry — pass a partial dict with a dummy entry to test unknown types.

---

## Audit remediation (2026-07-05)

- **Verify a gate actually runs.** The documented `uv run mypy src/` never
  executed (no root `src/`), so a branch's mypy debt shipped unguarded — including
  2 real bugs. Gate is `uv run mypy apps/indexed/src packages/*/src`; scope success
  to **0-new on touched files**, never tree-wide green (mypy isn't strict; ~230
  pre-existing untyped-def errors). Baseline the count before editing.
- **One `missing_wiring_error(component)` for DI gaps** (`indexed_config.errors`) →
  `"<component> must be injected by the app layer; see indexed.bootstrap"`. Never
  hand-roll the string; it was copied across 4 core sites + a dead app copy.
- **Factory type aliases live in leaf `factories/_types.py`** (imports only
  `DiskPersister` + protocols — downward). In `services/models` they'd re-introduce
  a services↔factories cycle. Real reader/converter element types (not `Any`)
  cleared 15 mypy errors for free.
- **Keep `update_collection_factory` lazy in `_update_one`.** `collection_service`
  ← `create_collection_factory` ← `documents_collection_creator` ← `services/__init__`
  is a cold-import cycle; hoisting the factory to module load re-enters it. "Trim
  the stale comment" meant fix the comment, keep the lazy import.
- **A public API whose only callers are its mocks is dead.** `core.v1.Index.update()`
  raised on every real call (DI made its factories required, never injected); its
  one prod caller discarded the result. Removed from `__all__`.
- **Assert behaviour, not existence.** `__name__ == 'X'`, `hasattr`, `assert x is
  not None`, `assert mock.set.called`, CWD-relative paths prove nothing. Use `is`,
  `isinstance` vs `@runtime_checkable` protocols, `assert_called_once_with`, and
  anchor test roots to `Path(__file__).resolve().parents[N]` + a zero-files guard.
- **A CI guardrail needs a negative test.** The import-graph gate's `FORBIDDEN`
  omitted `indexed` (so `core→indexed` passed silently) and `_package_for_path`
  ignored its `root` (inert under fixtures). Test that a synthetic bad edge IS caught.

---

## General (from AGENTS.md)

- Lazy-load heavy ML imports inside functions, never at module top level.
- Coverage is measured on installed packages — run `uv run pytest -q --cov=src`
  from project root.
- Spec drift is the main failure mode — update `.spec/` in the same cycle as code.

---

## `is_verbose_mode()` is unreliable at command-function top

**Context:** `create.py` connector commands hoisted the storage indicator to the top
of each function. The original check (`if not is_verbose_mode():`) always returned
`False` there because `setup_root_logger` (which sets the global log level) only runs
inside `execute_create_command`, later in the flow.

**Lesson:** At command-function top, check `verbose` and `log_level` params directly.
`is_verbose_mode()` is only reliable after `setup_root_logger` runs. Tests that mock
`is_verbose_mode` directly pass regardless of timing — they don't expose this bug.

**Fix pattern:** Extract one predicate over the params and reuse it for *every*
pre-setup gate — the storage indicator *and* the connector-heading guards — so they
stay consistent (an `--log-level=INFO` run must suppress both, or neither):
```python
def _is_pre_setup_verbose(verbose: bool, log_level: Optional[str]) -> bool:
    return verbose or (log_level or "").upper() in ("INFO", "DEBUG")

# indicator + `if not _is_pre_setup_verbose(verbose, log_level):` heading guards
```
Pre-setup `logger.info(...)` lines stay gated on `is_verbose_mode()` — they genuinely
cannot fire before `setup_root_logger`, so that check is correct, not a bug.

---

## Share credential-guard helpers, never duplicate them

**Context:** The origin guard block (`is_same_origin` + warning + `return None`) was
added identically to 3 separate reader methods. Any future change to the warning
string or return contract requires touching all three in sync.

**Lesson:** Extract a `warn_if_off_origin(url, base_url) -> bool` helper in the
shared module (`_url_guard.py`). Call sites reduce to a single-line guard:
```python
if not warn_if_off_origin(url, self.base_url):
    return None
```

---

## Loguru module-level import is fine; the lazy-import rule is ML-only

**Context:** Review flagged that loguru was imported at module level in some files
and lazily in others, questioning consistency.

**Lesson:** CLAUDE.md's lazy-import rule targets `sentence-transformers`/`torch` only
(500ms+ penalty). Loguru is a lightweight logger — module-level import is correct and
consistent with `apps/indexed` usage. Lazy-import loguru only inside isolated
connector methods where the import itself is fine either way (no performance cost).

---

## Jira Cloud attachment URLs are intentionally off-origin

**Context:** Applying the origin guard to `AsyncJiraCloudDocumentReader` silently
dropped all Cloud attachments. Jira Cloud serves `att["content"]` from
`api.media.atlassian.com` — off-origin relative to `*.atlassian.net` base URLs.

**Lesson:** When applying a credential-guard to a family of readers, audit each for
CDN/proxy patterns. Cloud APIs often serve content from off-origin CDNs; the threat
model there is different (URLs come from the API, not user-controlled). Exclude
deliberately and document why.

---

## Same-origin checks must compare port, not just scheme + host

**Context:** `is_same_origin` originally ignored the port entirely, so
`https://host:8443/...` matched a `https://host` base and credentials would still be
sent to a different service on the same host. The permissive behavior was justified as
"base URLs rarely store a port."

**Lesson:** Compare the **effective** port — normalize a missing port to the scheme
default (443/80) — instead of dropping it. That keeps `https://host` ≡ `https://host:443`
(the reason ports were skipped) while correctly rejecting non-default ports. A different
port is a different origin for credential purposes; fail closed.

---

## Behavior-net harness (foundation/1, 2026-07-07)

- **Warm the engine via `import core.v1.engine.services` first.** The engine has a
  cold-import cycle (`documents_collection_creator` imports `services.models` →
  `services/__init__` → `collection_service` → `create_collection_factory` → back to
  the creator). In a fresh process, importing a factory / creator / searcher
  **directly** fails cold; importing the `services` **package** first resolves it.
  Any test that touches the engine outside the CLI must warm that import first
  (`tests/characterization/test_lifecycle_cloud.py`, `test_known_bugs.py`). This is
  the same cycle foundation/7 removes by breaking the engine→services upward import.
- **Stub HTTP at the `read_documents` boundary; run FAISS + embeddings for real.**
  The cloud lifecycle nets build the real reader+converter and patch only the HTTP
  client (`jira…Jira`, `confluence…requests.get`, `outline…requests.post` +
  `httpx.AsyncClient`). Drive create via `create_collection_creator`, update via
  `create_collection_updater(manifest_connector_factory=…)`, inspect via
  `InspectService.status`, remove via `collection_service.clear`. A shared mutable
  doc-list backs the stub so `add_update()` grows the source for the update leg.
- **Known-hit, not "no error".** Assert a *specific* document is the top hit and that
  a *different* query ranks a *different* document first. That is what proves recall
  and is exactly what the pruned mechanism tests could not assert.
- **Config isolation patches `Path.home()`**, so the HF model cache can miss on the
  first model-using test of a session and re-download once into the sandbox. Harmless
  where the network is available; gate model-dependent specs on `model_available()`.
- **Verify red bug-specs fail for the RIGHT reason.** Run them with
  `pytest --runxfail --tb=line` and confirm each fails on a genuine assertion about
  the desired behavior (or the bug's own exception) — never a spurious
  `AttributeError`/`ImportError`. A spec that xfails on a typo never flips to xpass
  when the bug is fixed, so it silently stops guarding.
- **Prune only net-covered mechanism tests; promote when unsure.** Registry-membership
  `test_init.py` clones were replaced by one behavior-focused
  `test_connector_registry.py` (public `get_connector_class`/`list_connector_types`)
  before deleting them — "promote into the net, then delete", never delete-first.

---

## Search recall fixes (foundation/2, 2026-07-07)

- **A cross-package layering rule can be honored without duplicating the model.**
  `indexed-parsing` must not import `indexed-core` (its own `CLAUDE.md`), but the
  chunkers still need the embedder's real token window. Resolution: the embedder
  (`SentenceEmbedder.max_seq_length`) stays the single **dynamic** source of truth
  (reads `self.model.max_seq_length` live); `indexed-parsing` gets its own
  `_model_window.py` with a **documented, hardcoded** `DEFAULT_MODEL_MAX_SEQ_LENGTH
  = 256` that must track the embedder's default model. It loads a `transformers`
  tokenizer directly (a third-party ML lib, not "core engine") for real token
  counting/splitting — lazy-loaded exactly like the existing Docling/tree-sitter
  imports in that package. Two numbers, one documented link between them, no
  forbidden import.
- **`HybridChunker` was already the right token-aware chunker** — the
  `DoclingParser` docstring claimed it, the code used `HierarchicalChunker`
  (heading-only, no size bound) instead. Docling's default tokenizer for
  `HybridChunker`/`get_default_tokenizer()` is `sentence-transformers/all-MiniLM-L6-v2`
  itself, so it lines up with this project's default embedding model out of the
  box — build a `HuggingFaceTokenizer(tokenizer=..., max_tokens=...)` explicitly
  with `local_files_only=True` rather than relying on the library default, which
  calls `hf_hub_download`/`AutoTokenizer.from_pretrained` without it (an
  unnecessary network attempt even when cached). Needs the `docling-core[chunking]`
  extra (`transformers` + `semchunk`) — add it to the owning package's
  `pyproject.toml` even if the workspace venv already has it transitively.
- **Real token-bounded splitting beats char-per-token heuristics.** A
  `chars ≈ tokens * 4` estimate is not a safe upper bound for punctuation/number-
  heavy text (logs, code, CSV) — it can undercount tokens and still emit an
  oversize chunk. Split (paragraphs → lines → words → hard char slices) using the
  real tokenizer's count at each level; only fall back to a char-based slice for a
  single unsplittable run with no whitespace at all.
- **FAISS `IndexFlatL2` over-fetching is nearly free.** Its search cost is
  dominated by the O(N·d) distance computation against every vector; asking for
  `k=N` instead of `k=15` barely changes wall time (confirmed against a 10k-vector
  benchmark fixture). This makes "over-fetch the whole index, group, then cap" a
  cheap and robust fix for top-k starvation — no tuning a multiplier constant, no
  risk of an unlucky corpus defeating it — at the documented <100k-doc scale;
  bound it with a ceiling constant for the pathological large-index case.
- **Filter-before-truncate needs the truncation moved, not just reordered.** The
  searcher enforces `max_docs` internally (needed to fix starvation); to let
  `_filter_by_score` backfill filtered-out slots, the caller must ask the searcher
  for `max_docs * OVERFETCH_FACTOR` candidates when a threshold is active, filter
  that wider set, THEN slice to the real `max_docs` — truncating to the final
  count before filtering discards the very candidates that would have backfilled.

## MCP freshness/errors & dead config sections (foundation/6d, 2026-07-07)

- **`resolve_collections_context(mode_override=...)` used to silently wipe
  registered config specs — now fixed at the root.** It calls
  `ConfigService.instance(mode_override=..., reset=mode_override is not None)`
  — `reset=True` unconditionally replaces the singleton (fresh, empty
  `ConfigRegistry`) any time a non-None override is passed, even when the
  override is identical to what's already active. Every knowledge command
  calls this *after* the app callback's `register_app_config`, so a bare
  reset silently dropped every registered spec for the rest of that command —
  including `FaissIndexer._resolve_embedding_batch_size()`, which fell back to
  its hardcoded 128 default in `--local` mode (the mode create/update/tests
  actually use) instead of honoring `core.v1.embedding.batch_size`.
  **Root-cause fix (this task):** `resolve_collections_context` now calls
  `register_app_config(config_service)` itself, right after obtaining/resetting
  the singleton and before returning the `CliContext` — `register_app_config`
  is idempotent (plain dict registration), so this is free for the already-hot
  path and restores the specs for **every** caller (create/update/search/
  inspect/remove/MCP) in one place instead of leaving each caller to guess it
  needs a defensive re-register. `search.py::_load_search_config`'s per-call
  `register_app_config` re-register (the original 6d workaround) has been
  removed as redundant — it now just binds directly, relying on the runtime
  fix. **Do not reintroduce the per-caller defensive re-register pattern**
  for callers that go through `resolve_collections_context`; only call sites
  that build their own `ConfigService.instance()` *without* going through
  `resolve_collections_context` (e.g. `mcp/cli.py::run_impl`, which resolves
  config before any storage-mode override) still need their own explicit
  `register_app_config` call. The remaining "is this settable-but-unread
  knob truly dead" audit for `core.v1.indexing` / the rest of
  `core.v1.embedding` is unchanged — still deferred to foundation/7-9.
- **Two console-output test patterns coexist in `search.py` and don't compose.**
  Some tests monkeypatch `search_cmd.console` (a module-local rebinding) and
  capture via a fake `.print`; but `print_error`/`print_warning` (from
  `utils.components.alerts`) hold their own reference to the *real* shared
  console, so patching `search_cmd.console` never captures their output. To
  assert on `print_error`/`print_warning` calls, patch the name in the calling
  module's namespace instead — `patch.object(search_cmd, "print_error")` — not
  the console object.
- **A settable-but-unread config knob isn't automatically "dead" everywhere.**
  E12 named three sections (`core.v1.indexing`, `core.v1.embedding`,
  `core.v1.storage`) as registered-but-unread. Only `embedding.batch_size` was
  wired into the engine (`FaissIndexer.index_texts`, replacing the hardcoded
  64) because the brief scoped it explicitly and it's a single, low-risk read.
  `core.v1.indexing` (chunk_size/chunk_overlap) and the rest of
  `core.v1.embedding` (model_name/provider/dimension/device) remain registered
  but unread by design — wiring chunk_size risks colliding with foundation/2's
  token-window chunking (which now sizes off the model directly, not this
  config), and wiring model_name is a bigger factory-selection change outside
  this unit's remit. Left as a known residual for whoever does the
  config-architecture pass (foundation/7-9): delete or wire them then, backed
  by the full picture rather than a narrow bugfix task.
- **`ConfigService.set_overlay()` is the right tool for config-dependent unit
  tests.** It's in-memory only (never touches disk), so a test can register a
  spec and set a value without a `tmp_path`/`monkeypatch.chdir` dance — just
  `svc.register(Model, path=...)` then `svc.set_overlay("path.key", value)`.

## Foundation bug-batch closeout (2026-07-07)

- **Additive manifest keys keep old collections loadable (F2).** To add
  `createdTime` without breaking byte-compat: write the new key ONLY in the
  brand-new-collection branch of `__create_manifest_content`; the update branch
  spreads `**existing_manifest` first, so an old manifest without the key
  round-trips untouched and readers use `manifest.get("createdTime")` → `None`.
  Never add a key on the update path (it would rewrite every existing manifest).
- **Guard zero-padded / non-finite words before numeric coercion (F5).**
  `_coerce_value` must not mangle string-typed config values: reject leading-zero
  runs (`^[+-]?0\d`) and non-finite words (`nan`/`inf`) BEFORE `json.loads`/
  `float()`, so `"001"`→`"001"` and `"nan"`→`"nan"` while genuine numerics still
  coerce. Report the real index FILE byte size via `os.path.getsize()` (not the
  FAISS `ntotal` vector count) and compute `avg_doc_size` from the `documents/`
  folder only, excluding the index (F1/F3).
- **Loguru config leaks across CliRunner invocations in one test process.** The
  CLI configures loguru once per process (guarded by `_LOGGING_CONFIGURED`); in a
  test process many `CliRunner` invokes share it, so a command that installs a
  stdout log sink (`create`) leaks it into a later command whose diagnostic logs
  then corrupt stdout (an inspect-error line prepended to `--simple-output`
  JSON), making output assertions order-dependent. Production runs one process
  per command, so it only bites tests. Fix: an autouse conftest fixture that
  `loguru.remove()`s sinks and resets `utils.logger._LOGGING_CONFIGURED = False`
  after each test. Same class of leak as the `simple_output` module global —
  reset both.
- **`url.endswith(".domain")` on a full URL is incomplete-substring sanitization
  (CodeQL `py/incomplete-url-substring-sanitization`, HIGH).** The Atlassian
  Cloud discriminators in the Jira/Confluence readers did
  `base_url.endswith(".atlassian.net")` on the raw URL, so
  `https://evil.com/x.atlassian.net` was misclassified as Cloud (would route
  credentialed requests off-host). Fix: a shared `is_cloud_host(url)` in
  `connectors/_url_guard.py` that extracts the host via the existing
  `_client_host` (the urllib3-accurate authority parse) BEFORE the `.endswith`
  check, with a scheme-less bare-host fallback for back-compat. Always parse the
  host first — the parsed-host form is both correct and what the scanner
  recognizes as sanitized; a bare-string `endswith`/`in` on a URL is not. Mirrors
  `create.py::_is_cloud`. Editing a line CodeQL already (heuristically) flags
  re-fingerprints it as a *new* PR alert even when the edit makes it safer —
  expect the "1 new alert" to be the line you just touched.

---

## Typed data contracts live in the `protocols` leaf, not `core` (foundation/7, 2026-07-08)

- **The typed models (`Manifest`/`ConvertedDocument`/`Chunk`/`CollectionSearchResult`/…)
  belong in `packages/indexed-protocols/src/protocols/models.py`, NOT
  `core/v1/models.py`.** The feature spec's overview (tech.md §1) originally
  placed them under `core.v1`, but that contradicts its own edge list (§5):
  `connectors`/`config`/`protocols` may not import `core`, yet
  `protocols/connectors.py` must reference `ConvertedDocument`/`Manifest` (the
  converter returns `ConvertedDocument`) and readers/converters live in
  `connectors`. `scripts/check_import_graph.py` encodes exactly this
  (`"protocols": {"core", "connectors", "indexed"}` forbidden). The leaf is the
  ONLY import-legal home. `SourceConfig` already lived there — fold the rest in.
  Spec corrected in the same cycle (tech.md §1, tech-core.md).
- **Byte-stability = declare fields in on-disk key order + `by_alias=True`.**
  Pydantic `model_dump(by_alias=True)` emits declared fields in definition order,
  then `extra="allow"` extras in insertion order. Match the writer's key order
  field-for-field and the re-serialized JSON is byte-identical. Assert it with
  `json.dumps(model.to_disk()) == json.dumps(raw)` (order-sensitive), not just
  dict `==`.
- **Optional-key round-trip: pop, don't `exclude_none`.** The manifest's
  `createdTime` is CREATE-only (absent on older collections). A global
  `exclude_none=True` would also drop a legitimately-null *reader* field and
  break byte-stability. Instead dump normally and `pop("createdTime")` only when
  it's `None`. (For `Chunk.metadata`, where no null-valued sibling exists,
  `exclude_none=True` is safe and keeps chunk 0 metadata-free.)
- **Corrected protocols make a mismatch a mypy error.** `DocumentReader` now
  declares `get_number_of_documents`/`read_all_documents`/`get_reader_details`
  (what the creator actually calls) instead of the fictional `read_documents`
  (zero callers). Verify the property with `MYPYPATH=packages/indexed-protocols/src`
  — a standalone `mypy` run on a file outside the configured path silently treats
  `protocols` as `Any` and reports a false "Success".
- **Break the engine→services cycle at the import, not with a lazy import.**
  `documents_collection_creator.py` imported progress types upward from
  `core.v1.engine.services.models`; point it straight at `protocols` (the leaf)
  instead. That removes the cycle the old lazy imports worked around.

---

## Facade + composition switchover (foundation/8, 2026-07-08)

- **One `from_manifest` per connector kills core's per-type branches.** The
  update path was two injected factories + an `if connector_type == "localFiles"`
  branch in core + a 180-line app-layer `_populate_*`/`os.environ` apparatus. It
  collapses to a single `ManifestFactory = Callable[[Manifest, str], ConnectorRun]`
  that dispatches to `registry[m.reader.type].from_manifest(...)`. Core calls it
  once for every source. The empty-query R6.5 fix and the Outline cutoff (an
  in-memory overlay now, not an `os.environ` side-channel) live inside each
  connector's `from_manifest`.
- **The core facade at `core/v1/engine/__init__.py` uses lazy `__getattr__`, not
  eager re-exports.** Eager `from .services import ...` in the package `__init__`
  would fire the full services import on ANY `core.v1.engine.*` submodule import
  and can reintroduce cold-import cycles. A `__getattr__` that imports `services`
  on first attribute access keeps submodule imports cheap and warms in the right
  order. The app imports core ONLY through `core.v1.engine` (never
  `services`/`factories`/`core`), so a v2 engine is a drop-in behind the same
  names over the same disk format (R2).
- **`composition.py` is the single wiring site** — it folds in the old
  `bootstrap.py` + `runtime.py` + `connector_wiring.py` and hands the facade two
  REQUIRED callables (`connector_factory` create-time, `manifest_factory`
  update-time). No `Callable | None` + `missing_wiring_error` on the happy path;
  omission is a `TypeError` at the call site. Keep connector/core imports lazy in
  it for <1s startup.
- **Mocking `sys.modules["core.v1.engine.services"]` no longer intercepts app
  imports that go through the facade.** `from core.v1.engine import X` resolves
  via the engine package's `services` attribute (set once the real module is
  imported), so a sys.modules patch is order-dependent and false-passes in
  isolation. Patch the facade attribute instead:
  `patch.object(core.v1.engine, "X", mock, create=True)`.
