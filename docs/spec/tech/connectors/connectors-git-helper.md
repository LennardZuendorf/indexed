---
type: tech
updated: 2026-11-22
applies: src/indexed/utils/git_meta.py
---

# Query-Time Git Helper (`utils/git_meta.py`)

Indexing is not the only consumer of git: `search --changed-since` and
`--git-provenance` ask the *query* side the same questions. The shared helper lives in
`src/indexed/utils/git_meta.py` — `utils` is the only layer both `core` and
`connectors` may import (a connector-local helper would break the import edges).
