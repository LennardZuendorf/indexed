---
type: tech
updated: 2026-11-22
applies: "src/indexed/config/**"
---

# Single-Source Config Resolution

Resolves to **one** `config.toml` — local OR global, never both. No merging.

**Mode resolution order** (`WorkspaceManager.resolve_storage_mode()`):

| Priority | Source | Example |
|----------|--------|---------|
| 1 (highest) | CLI `mode_override` | `--local` / `--global` |
| 2 | Workspace preference | global config `[workspace].mode` |
| 3 | Auto-detect | local `.indexed/config.toml` exists → local |
| 4 (lowest) | Default | `"global"` |

Once resolved, `TomlStore.read_for_mode(mode)` reads the single source. Then
`INDEXED__*` env vars and CLI arguments apply on top.
