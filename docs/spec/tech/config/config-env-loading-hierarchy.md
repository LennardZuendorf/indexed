---
type: tech
updated: 2026-11-22
applies: "src/indexed/config/**"
---

# .env Loading Hierarchy

All `.env` files use `load_dotenv(override=False)` — first loaded wins; real env
vars never overridden.

| Priority | Source | Description |
|----------|--------|-------------|
| 1 (highest) | real `os.environ` | set before process starts, never touched |
| 2 | `.indexed/.env` | from resolved root (local or global), loaded first |
| 3 (lowest) | `CWD/.env` | standard project .env, fills gaps only |

`INDEXED__*` env variables are mapped into the TOML config dict separately (not via `.env`).
