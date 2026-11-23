---
type: tech
updated: 2026-11-22
applies: "src/indexed/config/**"
---

# Storage Directory Structure

Storage dirs owned by `src/indexed/config/` (`storage.py`). Persistence semantics:
[Persistence Strategy](../core/core-persistence-strategy.md).

```text
~/.indexed/                    # Global mode (default)
├── config.toml
├── .env                       # credentials (not in git)
└── data/collections/{name}/
    ├── manifest.json          # both engines; v2 adds a version + engine block
    ├── state.json             # files connector only (change-tracker baseline;
    │                          #  also read by index freshness, tech/core/core-index-freshness.md)
    ├── storage/               # v2 only (LlamaIndex persist): docstore.json,
    │                          # index_store.json, default__vector_store.json
    ├── documents/<id>.json    # v1 only
    └── indexes/               # v1 only
        ├── index_info.json
        ├── index_document_mapping.json
        └── indexer_FAISS_*/indexer   # binary FAISS index

./.indexed/                    # Local mode (per-project)
├── config.toml
├── .env
├── .gitignore                 # auto-created with ".env" entry
└── data/collections/...
```

**`.gitignore` auto-creation:** `ensure_storage_dirs(is_local=True)` creates a
`.gitignore` containing `.env` (appends `.env` if the file exists but lacks it).
Not applied to `~/.indexed/` (outside git repos).
