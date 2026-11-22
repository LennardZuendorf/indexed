---
type: tech
updated: 2026-11-22
applies: "src/indexed/parsing/**"
---

# Token window & tokenizer acquisition

`_model_window.py` is the parsing package's whole view of the embedding model's
window: `DEFAULT_MODEL_MAX_SEQ_LENGTH = 256` (must track the embedder's default
model, see [Model cache contract](../core/core-model-cache-contract.md)) and the tokenizer those
chunkers count with (`sentence-transformers/all-MiniLM-L6-v2`).

**Parsing runs before the embedder's model acquisition**, so on a clean install
the tokenizer is not in the shared HF cache yet. The load is therefore two-step:
cache-only first (`local_files_only=True`, so a warm run never touches the
network), then — only when that misses and the environment is not offline
(`HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE`) — one real download of the tokenizer
files, which the later embedding-model acquisition reuses. This keeps the first
run token-aware instead of silently degrading it.

Degradation contract when the tokenizer cannot be had at all (offline with a
cold cache, unreachable Hub): the failure is **cached for the process** and
reported **once, at WARNING, without a traceback and without internal bug ids**;
`count_tokens` falls back to a character estimate and `get_markdown_chunker`
falls back to `HierarchicalChunker`. Without the cached failure, every chunk and
every line re-attempted the load, and a clean first run printed 40+ tracebacks.

`transformers` is imported lazily inside the load, and that import is often the
process's first Hub user — `enforce_third_party_policy("huggingface_hub")` runs
right after it, or the Hub's one-time notice prints twice (raw + Loguru, #211).

**The first import is serialised and retried once.** Two threads can first-import
`transformers` at the same time — the MCP watcher's catch-up runs in
`asyncio.to_thread` while the first `search` loads the embedder (#335). The
losing thread then sees a half-initialised module, so `_import_auto_tokenizer`
holds a module-level `threading.Lock` and retries the import once on
`ImportError` after a short settle delay — the other thread has normally
finished by then. A persistent `ImportError` means the install itself is broken:
it keeps the one-line WARNING but must not blame the model cache with "run
`indexed init`", which cannot fix it. The MCP server also calls
`prewarm_tokenizer()` before it starts watchers, so the first import happens on
the main thread by construction (see `features/file-watcher/tech.md` § MCP
server wiring).

`indexed init` downloads the whole repository (weights + tokenizer) up front, so
after it every command — including `index create` — runs fully offline.
