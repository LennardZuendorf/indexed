---
type: feature-product
feature: mcp-request-scope
sibling: tech.md
parent: ../../product.md
updated: 2026-11-26
---

# Feature: MCP Request Scope — Product

**Parent:** issue [#345](https://github.com/LennardZuendorf/indexed/issues/345) ·
milestone [#229](https://github.com/LennardZuendorf/indexed/issues/229) ·
builds on [workspace-selection](../workspace-selection/product.md).

## Problem

One `indexed mcp run` process serves many agent clients — one per editor
window, one per CLI agent, several at once. Until now the process resolved *one*
workspace at startup from its own working directory and reused it forever, so
the workspace of whichever client happened to configure the server last decided
what **every** client searched. Two agents in two repositories shared one
answer, and neither could tell.

## Outcome

Every MCP request carries its own scope. The client declares the directories it
is working in (MCP **roots**); for each request the server takes those roots,
finds the nearest committed `indexed.toml` at or above them, and serves exactly
that definition's selection from the one global store. Two clients connected to
the same long-lived server see two different, correct answers — and neither can
see the other's collections.

The server never falls back: no roots, no definition, or roots that disagree are
an error the agent can read, not an unfiltered store.

## Requirements

- **R1 — Scope is per request, never process state.** Each tool call and each
  resource read resolves scope from that request's own roots. Nothing is carried
  over from the previous request, the server's CWD or its startup config.
- **R2 — One definition, resolved like the CLI and the LSP.** The same discovery
  rule (`find_definition`: nearest `indexed.toml`, stopping before `$HOME`) and
  the same resolver. Two clients in two worktrees of one repository, on branches
  with different definitions, each see their own.
- **R3 — Search and status agree.** `search`, `search_collection`, the
  `resource://collections*` resources and the per-collection resource all apply
  the same scope to the same request; there is no path where search is scoped but
  status is not.
- **R4 — Fail closed, loud and named.** A request with no roots, no definition,
  or two conflicting definitions gets a documented error envelope naming the
  error type and zero collections. It never inherits another request's scope and
  never widens to the whole store.
- **R5 — MCP scope is a boundary, unlike the CLI's default.** On the CLI a
  missing definition means "every collection" (workspace-selection R4) and an
  explicit `--collection` outside the selection still runs with a warning
  (R5). The MCP server is shared by unrelated projects, so there absence and
  out-of-scope names are errors. This divergence is deliberate and documented;
  the parity claim covers a workspace that *has* a definition.

## Non-goals

- Multi-user authentication, per-request quotas, per-request engine/search
  overrides — [#229](https://github.com/LennardZuendorf/indexed/issues/229).
- Installer/plugin lifecycle changes ([#348](https://github.com/LennardZuendorf/indexed/issues/348)):
  making each generated MCP client config advertise roots is installer work, not
  resolution work. This feature states the requirement; the installer follows.
- Writing scope: the server never creates or edits an `indexed.toml`.
