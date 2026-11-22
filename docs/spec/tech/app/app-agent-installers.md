---
type: tech
updated: 2026-11-22
applies: "src/indexed/cli/**"
---

# Coding-agent installers (`install claude-code`, `install codex`)

One command per host registers the MCP server, the `index-use` skill and a
nudge hook, and `--remove` takes exactly those back out. Each host gets its own
module (`install.py`, `install_codex.py`); the shared helpers (command
resolution, payload loading, atomic writes, `Change` planning) live in
`install.py` and are imported, never duplicated.

Host differences are load-bearing, not cosmetic:

- **Claude Code**: JSON config (`~/.claude.json` + `~/.claude/settings.json`),
  one JSON merge per file, hooks matched on `Grep|Glob`.
- **Codex**: TOML config (`~/.codex/config.toml`) edited as **text** — only the
  `[mcp_servers.indexed]` block and the hook-trust table are rewritten, so the
  user's comments and spacing survive byte for byte (`codex mcp add` cannot do
  this). Every write to that file, the trust-hash one included, goes through the
  raw (newline-preserving) helpers, so a CRLF file still comes back byte for
  byte after `--remove`. Hooks live in `hooks.json`, matched on the shell tool
  name, and Codex runs no hook until it is trusted: the installer reads the hash
  Codex computed back from `hooks/list` and records it in `hooks.state` instead
  of inventing one.

Both hooks only ever emit `additionalContext` — no `permissionDecision` — and
are silent when indexed has no collections, so they cannot change a user's
permission flow. Payloads ship in the wheel via `pyproject.toml` `force-include`;
the CI `Installer smoke` steps exercise install → upgrade → remove against a
config that already holds another tool's keys.
