---
type: feature-tech
feature: lsp-tier0
sibling: product.md
parent: ../../plan.md
updated: 2026-11-10
---

# `indexed lsp` — Tier 0 (architecture)

## Modules

| File | Responsibility |
|------|----------------|
| `src/indexed/lsp/protocol.py` | LSP base protocol: `Content-Length` framing, JSON-RPC error codes, message builders. I/O only, no policy. |
| `src/indexed/lsp/backend.py` | The engine seam: collection status (cached, TTL 2 s), source-root ownership of a file, one-collection search through `indexed.core.engine` only. |
| `src/indexed/lsp/results.py` | Provenance → LSP: LSP ranges, `SymbolInformation` list, hover markdown. Locator and chunk access come from `indexed.utils.provenance`. |
| `src/indexed/lsp/server.py` | Dispatch: lifecycle (`initialize`/`initialized`/`shutdown`/`exit`), the two capabilities, error mapping, the stdio loop. |
| `src/indexed/cli/lsp.py` | The `indexed lsp` command: resolve storage, construct the backend, hand over stdio. |

Layer position: `indexed/lsp` is a **presentation surface**, a peer of
`indexed/cli` and `indexed/mcp`. `scripts/check_imports.py` treats it as an
"up" layer — nothing below may import it, and it may use only the core facade
(never `core.v1.*` / `core.v2.*`).

## Protocol behaviour

- Framing is `Content-Length: N\r\n\r\n<utf-8 json>`, implemented locally
  because the MCP stdio transport is newline-delimited. A frame that cannot be
  decoded — bad JSON, missing header, a body cut short — is answered with
  `ParseError` / `InvalidRequest` and the session continues. A declared length
  over `MAX_CONTENT_LENGTH` (8 MiB) is refused *before* its body is read, so it
  is answered with `InvalidRequest` and ends the session (exit 1): the unread
  body cannot be skipped, and parsing it as headers would answer garbage
  instead of the client's next request. EOF without `exit` ends the process
  with the same code `exit` would: 0 after a `shutdown`, 1 otherwise. stdout
  is redirected to stderr during dispatch, so a stray `print` in the engine
  cannot corrupt a frame.
- Notifications are never answered — no response at all, not even the reserved
  `"id": null` (JSON-RPC 2.0 §4.1). An `initialize` sent without an id does not
  start the session, so the client's real request still works; a `shutdown`
  without an id records the shutdown (a following `exit` is clean) but is not
  answered.
- State machine: requests before `initialize` → `ServerNotInitialized`
  (-32002); a second `initialize` → `InvalidRequest`; after `shutdown` →
  `InvalidRequest` (-32600); `exit` after `shutdown` → 0, `exit` without it
  → 1. Unknown request → `MethodNotFound`; unknown notification → ignored
  (the protocol forbids answering one).
- `initialize` result: `textDocumentSync: 0` (no document state),
  `hoverProvider: true`, `workspaceSymbolProvider: true`, plus `serverInfo`.
  No other capability is ever advertised. (Tier 1 adds `definitionProvider`
  on the same server — see [../lsp-tier1/tech.md](../lsp-tier1/tech.md).)

## Provenance mapping

One normaliser, two vocabularies. Locators are built by
`indexed.utils.provenance.build_locator` — the same function behind the
`indexed.search/1` payload (`indexed.mcp.formatting` re-exports it), so the LSP
cannot drift into a third shape; chunk text/metadata access is shared the same
way (`chunk_parts`, `strip_context_prefix`). `results.py` owns only what is
LSP-specific: 0-based ranges and payload shapes.

| Chunk metadata | Locator | LSP |
|---|---|---|
| `start_line`/`end_line` (+ `file_path`) | `line_span`, 1-based inclusive (metadata itself is 0-based) | range start `(start, 0)`, end `(end, len(last indexed line))` |
| `page` | `page` | range `0,0` (position unknown at line level) |
| `headings` | `headings` (blanks dropped) | range `0,0`, symbol kind Namespace |
| none | `document` | range `0,0`, symbol kind File |

The end character is the length of the chunk's own last line — the indexed
extent — not the current file's: a file edited after indexing cannot stretch a
range over content the hit never covered.

`location.uri` is a real URI, not a string concatenation: a `file://` url is
re-emitted through `Path.as_uri()`, so a space or a non-ASCII character is
percent-encoded and strict clients (Helix's `url::Url`) can parse it. A relative
chunk `file_path` resolves against the owning collection's
`manifest.reader.basePath`, never the server process's cwd.

Code chunks embed `# <path>\n` for the embedder, plaintext chunks the bare
`<path>\n`; either prefix is stripped from hover text and from the payload
`text` field, because the locator already states the path. Chunk 0 (the path
stub) is never emitted as a symbol.

Hover carries **no `range`**: LSP defines `Hover.range` in the hovered document,
and the top hit may live in another file, so claiming a range would underline
unrelated text. The provenance line states the real locator instead, and the
score line leads with the shared `unified_relevance` (a raw L2 distance is
smaller when the match is better, so printing it bare reads inverted).

## Cost discipline

A language server is called while a human types:

- collection status **and** each collection's `manifest.reader.basePath` are
  cached for `STATUS_TTL_SECONDS` (2 s), so a burst of keystrokes reads
  manifests once while a manifest that appears or is repointed still shows up
  without restarting the editor;
- hover searches **only** the collection whose `basePath` contains the file
  (longest prefix wins), never every collection — a half-recovered collection
  stays out of the keystroke path (issue #126). Surfacing a Jira or Confluence
  hit from a code file's hover would need that cross-collection query on every
  keystroke and is **deferred to Tier 1**; in Tier 0 `workspace/symbol` is the
  cross-collection surface;
- symbol queries are capped (`SYMBOL_LIMIT` 50) and hover text is truncated
  (`MAX_HOVER_CHARS` 1200).

Known cold-start cost, not hidden: the first `workspace/symbol` after the
process starts pays the embedding-model load and collection recovery (measured
~2.4 s on a real store, ~0.01 s for subsequent queries in the same session).
Tier 0 sends no `$/progress`, so a client shows its own spinner.

## Failure behaviour

Engine errors are mapped to `INTERNAL_ERROR` with the original message and the
session keeps serving: one unreadable collection must not take down the editor's
server. A hover on a file no collection owns returns `null` (an empty hover),
never invented content. The one unrecoverable input is a frame whose declared
length exceeds `MAX_CONTENT_LENGTH`: it is answered with `InvalidRequest` and
ends the session, because its body is never read (see Protocol behaviour).

## Testing

- Unit: framing round-trips and malformed/oversized frames (including the
  stream's fate after each); locator provenance through the shared builder;
  ranges and percent-encoded file URIs; symbol/hover goldens (including
  freshness ages); dispatch/lifecycle/error codes, and no response to a
  notification; backend caching, ownership and search scoping.
- System: one out-of-process stdio session against a real FAISS collection
  driving Tier 0 points 1–4 and writing `lsp-transcript.json` — the transcript
  is the regression test, because the protocol is the contract. Point 5 (the
  documented client snippet) lives in the docs site, `indexed-web`
  `content/docs/reference/lsp-commands.mdx`.
