---
type: entrypoint
scope: design
children: []
updated: 2026-06-21
---

# Design Spec: indexed

Cross-cutting interaction and output design language — the conventions every
surface (CLI commands and the MCP server) shares. Visual identity is out of
scope (indexed is a terminal + protocol tool, not a GUI); this doc governs *how
output behaves and reads*, not colour or layout tokens.

**For product decisions (what/why), see [product.md](product.md). For
architecture, see [tech.md](tech.md).**

---

## Interaction Principles

- **Quiet on success, loud on failure.** Commands and background work produce
  minimal noise when things go right; errors are explicit, single-sentence, and
  actionable.
- **Human mode and machine mode are first-class.** Every command renders either a
  Rich human view or a structured machine view (`--simple` / JSON). Neither is an
  afterthought; the machine view is not a downgraded human view.
- **The agent is a user too.** MCP tool/resource payloads are designed for LLM
  consumption — flat, ranked, self-describing — the same care a CLI gives a human.

## Output Modes

| Mode | Surface | Shape |
|---|---|---|
| Rich human | CLI default | Panels, tables, info rows, phased progress (`utils/components`, `utils/progress_bar`) |
| Simple / JSON | CLI `--simple` / scripted | One JSON object per result via `utils/simple_output` (`print_json`) |
| LLM-optimized | MCP tools | Flat, ranked dict with direct text access (`mcp/formatting.format_search_results_for_llm`) |

Choosing a mode is the caller's right; a command MUST honour the resolved mode
end to end and never mix Rich markup into a JSON/stdio stream.

## Channel Discipline

- **stdout is sacred on stdio transports.** When the MCP server runs over stdio,
  stdout carries the protocol; all logs and diagnostics go to **stderr**. No
  feature may print to stdout outside the protocol on that transport.
- **Background work is silent by default.** Long-running or automatic operations
  (e.g. re-indexing) report through a status surface (a resource/field), not by
  emitting unsolicited output.

## Language & Copy

- Verbs are plain and imperative: `search`, `update`, `reindex`, `inspect`.
- Errors are one clear sentence, no stack trace in user-facing copy; the
  underlying exception text may be surfaced verbatim in a structured `error`
  field for machine consumers.
- Status values are a small closed vocabulary, not free text, so agents can
  branch on them.

## Do's and Don'ts

- Do resolve the output mode once and thread it through; render accordingly.
- Do keep MCP payloads flat and ranked for LLMs; include the text the agent needs.
- Don't print progress/Rich output onto a JSON or stdio-protocol stream.
- Don't report success before the underlying state (index, cache) is actually consistent.

---

## Feature Design Docs

Feature-scoped interaction detail lives in `features/<name>/design.md` and parents
to this doc. Active: [features/file-watcher/design.md](features/file-watcher/design.md).
