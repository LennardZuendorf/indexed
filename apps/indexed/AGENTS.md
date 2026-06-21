# apps/indexed — App (CLI + MCP)

> Scope: this package. Workflow, rules, and verify gate live in the root
> [`AGENTS.md`](../../AGENTS.md). Canonical design: [`.spec/tech-app.md`](../../.spec/tech-app.md).

## What this is

The user-facing application: a Typer **CLI** and an embedded **FastMCP** server.
UI layer only — **thin commands, fat services**. Business logic lives in
`indexed-core` services; this package parses args, resolves storage mode, and
formats output. It MUST NOT contain orchestration or engine logic.

## Layer & dependencies

Top of the stack. May import: services, `core`, `indexed_config`, `utils`.
Never imported by anything below it.

## Where to find what

```
src/indexed/
  app.py                 Typer entry + @app.callback (logging, storage-mode → ctx.obj)
  init.py  errors.py     app bootstrap · IndexedError-derived CLI errors
  knowledge/
    cli.py               `index` group
    commands/            create · search · inspect · update · remove (+ _create_helpers)
  config/cli.py          `config` group: inspect · set · validate
  info/cli.py            `info` group
  mcp/
    server.py tools.py   FastMCP server + @mcp.tool (search, list_collections, status)
    resources.py         resource://collections[/status|/{name}]
    cli.py config.py     transport selection (stdio/http/sse) · MCP config
    formatting.py        result formatting for agents
  utils/                 Rich UI (cards, alerts, theme), console, credentials,
                         migration, progress, storage_info — terminal output only
```

## Architecture notes

- **Storage mode** (`global` ~/.indexed vs `local` ./.indexed) resolves once in
  the callback: CLI flag → `config.toml` → `./.indexed/` present → global. Passed
  via `ctx.obj["mode_override"]`. Detail: [`.spec/tech-config.md`](../../.spec/tech-config.md).
- **MCP reuses the same `SearchService` + `ConfigService` as the CLI** — the agent
  sees exactly what the user sees. Transports: stdio (default), http, sse.
- **Startup <1s** via lazy ML imports, deferred service init, module-level
  `__getattr__` lazy loading. Never import torch/transformers at module top.
- **Rich** for all terminal output; teal `#00D4AA` accent. `loguru` logging with
  quiet/verbose/debug levels — stdout is reserved for command results.
- **Command files ≤150 lines** — branch on business rules ⇒ extract to a service.
