---
type: tech
updated: 2026-11-22
applies: "src/indexed/config/**"
---

# Config Schema

```toml
[_meta]
schema_version = "1"

[general]
log_level = "INFO"
storage_mode = "global"  # or "local"

[core.v1.indexing]
chunk_size = 512
chunk_overlap = 50
batch_size = 32

[core.v1.embedding]
model_name = "all-MiniLM-L6-v2"

[core.v1.vector_store]
index_type = "IndexFlatL2"

[core.v1.search]
max_docs = 10
max_chunks = 30
include_matched_chunks = true
min_score = 0.0
# Query-time git signals on v2 files collections (all off by default; nothing
# is persisted, so enabling them never requires a re-index).
git_provenance = false        # last-touching commit per result file
git_line_blame = false        # the commit that last touched each chunk's lines
git_rerank = false            # re-rank by recency + churn (+ author, if set)
git_rerank_recency_weight = 0.10
git_rerank_churn_weight = 0.05
# git_rerank_author = "lennard@zuendorf.me"   # name/email substring; unset = off
git_rerank_author_weight = 0.05

[mcp]
log_level = "INFO"
json_logs = false
transport = "stdio"
host = "127.0.0.1"
port = 8000
# Opt-in freshness for localFiles collections while the server runs (off by
# default: no watcher, no extra thread, unchanged startup).
watch_enabled = false
watch_debounce_seconds = 2.0        # quiet period before one update runs
watch_poll_interval_seconds = 2.0   # seconds between scans of the source tree

[watch]
debounce_seconds = 2.0     # quiet period before one update runs
poll_interval_seconds = 2.0  # seconds between scans of the watched tree
```
