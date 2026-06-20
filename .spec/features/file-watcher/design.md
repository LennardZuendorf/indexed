---
type: feature-design
feature: file-watcher
sibling: product.md
parent: ../../design.md
updated: 2026-06-20
---

# Feature: MCP File Watcher — Design

The watcher should feel invisible: freshness is the default, not a chore. The
operator does nothing; agents that want control get a single, fast, honest tool.
Nothing the feature does should ever surprise the operator or pollute the MCP
protocol channel.

**Parent:** [../../design.md](../../design.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

> Root `.spec/design.md` does not exist yet (no cross-cutting design language doc
> in this repo). This feature design stands alone; promote shared interaction
> conventions to a root `design.md` only if a second feature needs them.

---

## Design Intent

- **Fresh by default, quiet by default.** Watching is on without being asked, and
  produces no output on the happy path. The operator notices it only if they look
  for it (status resource) or turn it off (`--no-watch`).
- **Fast acknowledgement over completeness.** The `reindex` tool returns the
  instant work is accepted — a job id, not a finished index. Agents poll for
  completion; they are never blocked on embeddings.
- **Honest state.** Re-index status reports exactly one of `queued`/`running`/
  `done`/`error`, with the error text surfaced verbatim. No optimistic "done"
  before the index is actually swapped and caches cleared.

---

## Interaction Patterns

| Pattern | Use When | Notes |
|---|---|---|
| Silent auto-refresh | Files change under a watched collection | Debounced; one run per burst; no console/protocol output on success |
| Opt-out flag | Operator wants the server static or drives updates externally | `--no-watch` disables only the *auto* watcher; the `reindex` tool still works |
| Fire-and-poll tool | Agent needs a guaranteed-fresh search right now | `reindex(...)` returns a job id immediately; agent reads the collection resource for state |
| Status-on-demand | Agent or operator wants to know what the watcher did | `reindex` state lives on the existing `resource://collection/{name}`, not a new surface |

---

## Language & Copy

- Tool name is the plain verb **`reindex`**; argument is `collection` (optional →
  all file collections). Mirror the existing `search` / `search_collection` tone.
- Accepted response uses `accepted`, `job_id`, `state` — present tense, machine-first.
- Disabled path returns a single clear sentence, e.g.
  `"Re-indexing is disabled (server started with --no-watch)"`, not a stack trace.
- Status field is `reindex` with `state`, `job_id`, `documents_delta`, `error` —
  keys consistent with the surrounding status payload.

## Do's and Don'ts

- Do keep the happy path output-free; let the status resource be the record.
- Do log watcher/indexer activity to **stderr** only — stdout is the stdio MCP
  channel and must stay protocol-clean.
- Do collapse bursts: one re-index per settle window per collection.
- Don't block the agent on a `reindex` call, and don't report `done` before
  caches are invalidated.
- Don't invent a parallel status tool when the collection resource already exists.

## Open Questions

_None — interaction surface is settled; see [tech.md](tech.md) for the response
shapes._
