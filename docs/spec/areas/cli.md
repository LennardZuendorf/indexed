---
type: area
updated: 2026-11-22
code: [src/indexed/cli]
---

# CLI

| Feature | Status | Description |
|---------|--------|-------------|
| **Create Collections** | ✅ Shipped | `indexed index create` |
| **Search** | ✅ Shipped | `indexed index search` |
| **Update** | ✅ Shipped | `indexed index update` |
| **Inspect** | ✅ Shipped | `indexed index inspect` |
| **Remove** | ✅ Shipped | `indexed index remove` |
| **Config Management** | ✅ Shipped | `get`, `set`, `validate` commands |
| **System Info** | ✅ Shipped | `indexed info` |
| **Engine Selection** | ✅ Shipped | `--engine v1/v2` on `index create` (root, group, and leaf flags) — new collections only |
| **Migrate to v2** | ✅ Shipped | `indexed index migrate` — dry-run/backup/rollback-safe v1→v2 conversion |
| **Shared Collections** | ✅ Shipped | `indexed storage migrate` — stable collection ids in the global store; dry-run, resume, rollback, and `--on-collision adopt` so two projects read one on-disk index |
| Interactive TUI | 📋 Planned | Full-screen interactive mode |
| Progress Indicators | ⚠️ Partial | Spinners exist, bars planned |
