---
type: branch
scope: parsing
parent: tech.md
covers: ParsingModule, FileRouter, Docling, tree-sitter CodeChunker, ParsedDocument output
updated: 2026-11-16
---

# Tech Branch: Parsing (`src/indexed/parsing/`)

Reusable parsing module shared across connectors (Files, Confluence, Outline).
Lazy-loaded to keep CLI startup fast.

**Parent: [tech.md](tech.md).** Consumed by [tech-connectors.md](tech-connectors.md).

---

## Components

| Component | Role |
|-----------|------|
| **FileRouter** | Map file extension → parsing strategy (Docling, AST, plaintext, fallback) |
| **DoclingParser** | PDF/DOCX/PPTX/HTML/images via Docling, OCR (RapidOCR default) |
| **CodeChunker** | AST-aware code chunking via tree-sitter (Python, TS, JS, Java, Rust, Go, C, C++) — splits at function/class/method boundaries |
| **PlaintextParser** | Markdown via Docling (structure-aware); other text via paragraph splitting |
| **ParsingModule** | Facade routing files to the correct parser |

---

## Token window & tokenizer acquisition

`_model_window.py` is the parsing package's whole view of the embedding model's
window: `DEFAULT_MODEL_MAX_SEQ_LENGTH = 256` (must track the embedder's default
model, see `tech-core.md` § Model cache contract) and the tokenizer those
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

`indexed init` downloads the whole repository (weights + tokenizer) up front, so
after it every command — including `index create` — runs fully offline.

---

## Output

Framework-free `ParsedDocument` containing `ParsedChunk` objects:
- raw text
- contextualized text (heading/path prefix for embedding)
- metadata
- content hashes
