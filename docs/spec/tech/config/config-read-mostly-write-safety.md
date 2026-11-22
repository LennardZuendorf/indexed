---
type: tech
updated: 2026-11-22
applies: "src/indexed/config/**"
---

# Read-Mostly Config & Write Safety

`config.toml` is **user-owned**: `create` / `update` / `search` never write it.
CLI-arg overrides, date-stamped incremental queries, and cutoffs live in an
**in-memory overlay** (`ConfigService.set_overlay`); `INDEXED__*` env values are
applied on top but **never** baked back into TOML. Only `indexed config set`
persists, and it writes **atomically** — serialize → validate → tmp → `fsync` →
`os.replace` — rejecting unserializable input (e.g. `null`) **before** the target
file is touched, so a bad value can never truncate `config.toml`.

**Secrets** (`_is_sensitive_key`) route to the resolved `.env`, never TOML; they
are **quoted** so a value containing ` #` or `${...}` survives a dotenv reload
intact, and are **masked** on `config inspect` / `set` output.
