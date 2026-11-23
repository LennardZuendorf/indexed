---
type: tech
updated: 2026-11-22
applies: "src/indexed/config/**"
---

# Schema Versioning

`config.toml` carries `[_meta] schema_version`. `TomlStore.read()` extracts it
(`CURRENT_SCHEMA_VERSION = "1"`); writes ensure `_meta` is present. Provides a
migration path when config namespaces change (e.g. `core.v1.*` → `core.v2.*`).
