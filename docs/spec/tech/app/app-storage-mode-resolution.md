---
type: tech
updated: 2026-11-22
applies: "src/indexed/cli/**"
---

# Storage Mode Resolution

`Global` (`~/.indexed`) vs `Local` (`./.indexed`). Resolution order:

1. CLI flag `--local` / `--global` (highest)
2. `storage.mode` in `config.toml`
3. Presence of `./.indexed/` → Local
4. Global (fallback)

Full single-source config detail: [tech/config](../config/README.md).
