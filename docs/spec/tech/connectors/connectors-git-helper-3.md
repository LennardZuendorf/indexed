---
type: tech
updated: 2026-11-22
applies: src/indexed/utils/git_meta.py
---

# Query-Time Git Helper (`utils/git_meta.py`) (3)

Active configured storage roots are excluded from file traversal and explicit incremental files. When the storage root equals the source root, only its `data` directory is excluded.

File inventory traversal fails on filesystem errors or a replaced source root; it never classifies an incomplete inventory as deletions.
