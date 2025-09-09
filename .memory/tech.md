# Tech Stack and Style Rules

## Languages and Runtime
- Python >= 3.13

## Package and Build
- Dependency manager: uv
- Project metadata: pyproject.toml

## Key Libraries
- faiss-cpu (vector index/search; IndexFlatL2 wrapped by `FaissIndexer`)
- sentence-transformers (embeddings via `SentenceTransformer`)
- unstructured[all-docs] (file parsing for local files)
- requests (HTTP calls to Jira/Confluence)
- bs4 (HTML parsing where needed)
- mcp (MCP stdio integration)
- typer (single unified CLI framework)
- pydantic-settings (typed config loading from TOML + env)
- langchain (present as dependency; not central in core flows)

## Indexers and Embeddings
- Indexer: FAISS `IndexIDMap(IndexFlatL2)`
- Preconfigured embedding models:
  - sentence-transformers/all-MiniLM-L6-v2
  - sentence-transformers/all-mpnet-base-v2
  - sentence-transformers/multi-qa-distilbert-cos-v1
- Indexer naming convention: `indexer_FAISS_IndexFlatL2__embeddings_<model-id>`

## Data and Persistence
- Collections: `./data/collections/<collectionName>`
- Cache for source readers: `./data/caches/<hash>`
- Persistence via `DiskPersister` (text, pickle-serialized binaries, folder ops)

## CLI and Execution
- Single CLI (Typer) entrypoint: `indexed`
  - Example: `uv run indexed init`
- Scripts retained for backward compatibility: create/update/search/MCP adapters
- MCP server: stdio via `FastMCP`, integrated under `indexed mcp`

## Configuration Plan
- Primary store: TOML (`./config.toml`, git-ignored). Optional user-level: `~/.config/indexed/config.toml`.
- Loader: pydantic-settings with `TomlConfigSettingsSource` + `.env` for secrets.
- Precedence (highest → lowest): CLI flags (init kwargs) → env/.env → user TOML → project TOML → defaults.
- Secrets: keep tokens/emails/passwords in env; do not persist in TOML.
- Persistence: atomic write (temp file + `os.replace`), keep `.bak`.
- Runtime overrides: flags override for current invocation; persist only on `source add/remove` commands.

## Coding Style and Conventions
- Modular wiring via factories (readers/converters/indexers/persister)
- Use utilities for performance logging and progress bars
- Prefer early returns and clear error messages
- On-disk manifest/mappings are the source of truth
- CLI: Typer prompts and options only (no additional CLI UI libs)
