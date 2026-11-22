---
type: tech
updated: 2026-11-22
applies: "src/indexed/cli/**"
---

# Engine Selection (`--engine`)

Selects v1 vs v2 for a **new** collection only (existing collections are
manifest-authoritative — the facade infers their engine, a conflicting
`--engine` fails loud). Resolution order, highest wins:

1. Leaf-command flag (e.g. `index create files --engine v2`)
2. Group-callback flag (e.g. `index create --engine v2 files`)
3. Root-callback flag (e.g. `indexed --engine v2 index create files`)
4. `INDEXED__CORE__ENGINE` env var
5. `[core] engine` in `config.toml`
6. Built-in default (`v1`)

All three CLI-flag tiers (leaf/group/root) write into the **same** `ctx.obj`
dict — Click hands a child `Context` its parent's `obj` by identity, not a
copy, so a group or leaf callback doing `ctx.obj["engine"] =
normalize_engine_selector(v)` mutates the exact object the root callback
populated. `execute_create_command`'s single `get_context_value("engine")`
read sees whichever tier actually wrote, with no extra resolution code. Each
tier writes **only when the flag was explicitly passed** (guard on
`isinstance(value, str)`), so an unset flag at any level never clobbers a
value set by an outer level with `None`. This is the general pattern for
adding a flag at an intermediate level of the Typer app tree — mirror the
root callback's write, don't invent a new resolution tier or thread a new
parameter through every intermediate function.

All four surfaces that can reject an invalid engine value
(`--engine`, env, `config set core.engine`, hand-edited `config.toml`) share
one normalizer, `composition.normalize_engine_selector` — every surface
raises the identical single-line `Invalid engine 'x'; expected one of: 1, 2,
v1, v2`, never a raw pydantic `ValidationError` dump. `config set`'s
`core.engine` special case and `resolve_engine_selector`'s config.toml
branch both call it directly rather than parsing pydantic's error shape.
