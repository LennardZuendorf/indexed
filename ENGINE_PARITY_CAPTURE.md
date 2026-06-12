# Engine Parity Capture — v1 vs v2 (real CLI + MCP)

**Run:** 2026-06-12 · branch `feat/core-v2-llamaindex` · query `"retry with exponential backoff"`
**Method:** real `uv run indexed` CLI invocations + real FastMCP tool dispatch (in-process).
**Verdict column = mechanical PASS/FAIL of "did it run"; quality + acceptability are for human judgement (see § Judgement items).**

---

## Environment fact that frames everything

All 5 on-disk collections are **v1** — `manifest.json` has no `version` field, so
`detect_collection_engine` classifies them v1:

| Collection | Storage | Engine (auto-detect) |
|------------|---------|----------------------|
| files | global `~/.indexed` | v1 |
| notes | global `~/.indexed` | v1 |
| codebase | local `./.indexed` | v1 |
| test-update | local `./.indexed` | v1 |
| test-utils | local `./.indexed` | v1 |

**There is no v2 collection anywhere.** v2 is the *default* engine but has zero real
local data to search. CLI prefers local storage, so default search hits the 3 local v1 collections.

Resolution precedence (`engine_router.get_effective_engine`):
`--engine flag → root --engine → collection manifest auto-detect → [general] engine → default v2`.
**Explicit `--engine` overrides auto-detection** → forcing v2 onto a v1 store routes the v2 stack at a v1 layout.

---

## CLI — verbatim outcomes

| # | Command | Engine | Verdict | Output |
|---|---------|--------|---------|--------|
| 1 | `index search "…" -c test-utils --compact` | auto→v1 | ✅ | 5 results; `utils/retry.py` #1 |
| 2 | `… -c test-utils --engine v1 --compact` | v1 forced | ✅ | identical to #1 |
| 3 | `… -c test-utils --engine v2 --compact` | v2 forced | ❌ | **raw traceback**, `VectorStoreError`, exit 1 |
| 4 | `index inspect test-utils` | auto→v1 | ✅ | localFiles · 6 docs · 33 chunks · 161.9 KB · 5 days ago |
| 5 | `index inspect test-utils --engine v2` | v2 forced | ⚠️ | exit 0 but **Type=Unknown · 0 docs · 0 chunks** (silent hollow) |
| 6 | `--simple-output index search "…" -c test-utils` | auto→v1 | ✅ | JSON; `utils/retry.py` `execute_with_retry` score 0.7268 |

### CMD3 verbatim tail (forced v2 on v1 store)
```
VectorStoreError: Failed to load collection 'test-utils': No existing
llama_index.vector_stores.faiss.base found at
…/.indexed/data/collections/test-utils/default__vector_store.json.
```
(preceded by a full multi-frame Rich traceback printed to the user)

### CMD5 verbatim (forced v2 inspect on v1 store)
```
╭─ test-utils ─────────────────────────────────────────────╮
│ Type                                             Unknown │
│ Documents                                              0 │
│ Chunks                                                 0 │
│ Size                                            161.9 KB │
╰──────────────────────────────────────────────────────────╯
```

---

## MCP — verbatim outcomes (real FastMCP tools)

| Tool | Bound engine | Verdict | Output |
|------|--------------|---------|--------|
| `search` (all) | v1 | ✅ | 3 collections · 19 docs · 90 chunks; top `packages/utils/CLAUDE.md` backoff §, 0.583 |
| `search_collection("test-utils")` | v1 | ✅ | 6 docs · 30 chunks; `utils/retry.py` 0.7268 |
| `search` (all) | v2 | ⚠️ | clean error dict (see below) — does NOT crash |
| `search_collection("test-utils")` | v2-bound | ✅ | per-collection manifest auto-detect → routes v1 → works (engine-robust) |

### MCP `search` (engine=v2) — what the agent receives
```json
{
  "error": "Failed to load collection 'codebase': No existing llama_index.vector_stores.faiss.base found at …/.indexed/data/collections/codebase/default__vector_store.json."
}
```
`VectorStoreError` ⊂ `CoreV2Error` ⊂ `IndexedError`, so the tool's `except IndexedError`
catches it → graceful dict. (The CLI v2 path lacks this guard → CMD3 traceback.)

---

## § Judgement items (for human — not auto-judged)

1. **No v2 collection on disk.** v2 ships as default but is unexercised on real local data.
   Truly judging v2 search quality requires **building a v2 collection** (a mutation — needs OK).
   Smallest candidate: `packages/utils/src/utils/` (6 files, same source as `test-utils`).
2. **CLI `--engine v2` on a v1 store dumps a raw traceback (exit 1).** The CLI v2 search path
   (`knowledge/commands/search.py::_search_one`) has no graceful handler; the MCP tool does. ❌ inconsistent UX.
3. **CLI `inspect --engine v2` on v1 store → exit 0 + hollow Unknown/0/0.** A *third* distinct
   wrong-engine failure mode (silent, looks like an empty collection). ⚠️
4. **MCP v2 error message is leaky** — `"No existing llama_index.vector_stores.faiss.base … default__vector_store.json"`
   tells the agent nothing actionable (vs. "collection is v1, use --engine v1"). Medium.
5. **`search_collection` is engine-robust** (manifest auto-detect) — good. The vulnerable surface
   is the all-collections `search` when bound to v2 with no v2 stores.
6. **v1 chunk-text artifact**: rank-3 chunk renders `"f\nom .logger import"` — the `# <path>` header
   injection splits the first token of some chunks. Cosmetic but pollutes agent-facing text.

---

## Performance comparison — CLI app code corpus

**Corpus:** `apps/indexed/src/indexed` · 51 docs · 351 chunks (identical both engines).
Built as `cli-v1` (`--engine v1`) and `cli-v2` (`--engine v2`).
Embedding model `all-MiniLM-L6-v2` both sides.

### Build (CLI wall-clock, incl. uv start + model load — what a user feels)
| | v1 | v2 | Δ |
|---|----|----|---|
| build time | **6.54 s** | **8.42 s** | v2 +29% |
| on-disk | 1.6 MB | 1.2 MB | v2 −25% |
| inspect metadata | Updated only | Created + Updated | v2 richer |

### Search latency (in-process, load once, 6 runs; query = engine-routing)
| | v1 | v2 |
|---|----|----|
| cold (1st, incl. index+model load) | **3.42 s** | **5.03 s** |
| warm mean (runs 2–6) | **7.7 ms** | **14.1 ms** |

v2 ~47% slower cold, ~83% slower warm — but both warm calls are sub-15 ms (negligible for interactive use). Both cache the loaded index in-process.

### Result quality (query: "how does engine selection routing choose between v1 and v2")
Both return 5 docs / 12 chunks. Both rank `services/engine_dispatch.py` #1 (correct).
| rank | v1 | v2 |
|---|----|----|
| 1 | engine_dispatch.py (1.164) | engine_dispatch.py (1.308) |
| 2 | info/cli.py (1.252) | **engine_router.py (1.349)** |
| 3 | mcp/server.py (1.256) | mcp/server.py (1.359) |
| 4 | **engine_router.py (1.358)** | info/cli.py (1.412) |
| 5 | engine_router.py (1.394) | engine_router.py (1.476) |

v2 surfaces both routing files (`engine_dispatch` + `engine_router`) in the top 2; v1 buries `engine_router` at #4 below `info/cli.py` and `mcp/server.py`. v2 ordering is more on-topic here. Scores are L2 distances and **not comparable across engines** (different normalization).

**Net:** v2 = better relevance ordering, smaller index, richer metadata; v1 = faster build + faster queries. For interactive CLI/MCP use the latency gap is imperceptible; v2's quality + metadata justify it as default.

---

### Harness note (not a product bug)
In-process FastMCP `Client(mcp)` **segfaults (exit 139)** when the v2 (llama-index + faiss + torch)
stack initializes under the asyncio event loop — even single-engine, isolated process. The CLI v2
path runs fine, so this is a native-lib/event-loop interaction. Automated MCP-v2 e2e must run
**out-of-process / via real stdio**, not the in-memory client.

---

## Fixes applied (2026-06-12)

Design principle: `--engine` stays a **hard override** (matches `engine_router` documented
precedence: flag > manifest auto-detect > config). When a forced engine can't read a store,
every surface now fails with one clean, actionable message instead of a traceback / hollow card /
leaked internals.

| ID | Fix | Files |
|----|-----|-------|
| B4 | New `CollectionEngineMismatchError(VectorStoreError)`; `load_storage_context` classifies v1-store vs corrupt-v2 and raises it (no leaked LlamaIndex paths). `detect_disk_engine()` helper added. | `core/v2/errors.py`, `core/v2/storage.py` |
| B1 | CLI `_search_one` catches `IndexedError` around the v2 call → actionable error + exit 1 (single) / warn+skip (multi), no traceback. | `knowledge/commands/search.py` |
| B3 | v2 `inspect_service.inspect()` raises `CollectionEngineMismatchError` on a non-v2 manifest (was hollow 0/0/Unknown); command renders it. List view always routes per-row (forced engine no longer hollows v1 rows). Dead `_v2_status_to_info` removed. | `core/v2/services/inspect_service.py`, `knowledge/commands/inspect.py` |
| B6 | v2 all-collections search skips non-v2 collections (logs them) instead of dying on the first v1 store → MCP `search` returns valid v2 results in a mixed repo. | `core/v2/services/search_service.py` |
| B5 | v1 chunk-text artifact — **deferred** (v1 is legacy per `.spec/cleanup.md`; not cleaned up here). | — |

### Verification (clean bundle, plain `uv run`)
- B1 `search -c test-utils --engine v2` → `✗ Collection 'test-utils' is a v1 collection, not a v2 store. …` exit 1 (was multi-frame traceback).
- B3 `inspect test-utils --engine v2` → same clean message, exit 1 (was Type=Unknown/0/0, exit 0).
- B6 MCP all-search v2 → returns `cli-v2`, no error (was `{"error": "…faiss.base…"}`, hiding cli-v2).
- Positive controls: real v2 collection `cli-v2` search + inspect work; `inspect --engine v2` list shows all collections correctly.

### Tests / gates
- Added regression tests: `test_errors.py` (mismatch hierarchy + message), `test_storage.py`
  (`detect_disk_engine`, `load_storage_context` classification), `test_services.py` (B6 skip),
  `test_search.py` (B1), `test_inspect.py` (B3 single + list per-row). Updated tests that encoded
  the old forced-engine shortcut behaviour.
- Full suite: **1580 passed, 29 deselected (benchmarks), 1 pre-existing failure**
  (`test_server.py::test_read_collections_static` — a cross-test `ResponseCachingMiddleware` leak;
  verified failing on baseline with changes stashed → NOT introduced here).
- ruff clean; mypy adds **zero** new errors (tree has 247 pre-existing, CI non-blocking).
- `core` bundle rebuilt: `uv sync --reinstall-package indexed-sh --no-cache` (una staleness).
