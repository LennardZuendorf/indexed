---
type: area
updated: 2026-11-22
code: [src/indexed/config]
---

# Configuration

| Feature | Status | Description |
|---------|--------|-------------|
| **TOML Config** | ✅ Shipped | Human-readable config files |
| **Environment Vars** | ✅ Shipped | `INDEXED__*` override system |
| **Credential Management** | ✅ Shipped | Separate .env for secrets |
| **Global/Local Modes** | ✅ Shipped | System-wide or per-project collections |
| **Validation** | ✅ Shipped | Pydantic schema validation |
| **Single-Source Config** | ✅ Shipped | Resolves to one config.toml (no global+local merge) |
| **CWD/.env Support** | ✅ Shipped | Project-level .env loaded as credential fallback |
| **.gitignore Protection** | ✅ Shipped | Local .indexed/ auto-creates .gitignore with .env entry |
| Config Profiles | 📋 Planned | Named config sets (dev, prod, etc.) |
