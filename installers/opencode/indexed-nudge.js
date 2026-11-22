// indexed-install-hook v1 — installed by `indexed install opencode`.
//
// Context nudge for the `indexed` semantic-search MCP server. On every model
// round-trip OpenCode hands plugins the request it is about to send, with the
// system prompt split into blocks, through `session.hook("context")`; when
// indexed actually has collections this plugin appends one short paragraph
// telling the model to search by meaning before falling back to rg/grep.
//
// It ONLY appends one text block to `system`. It registers no
// `permission.hook("evaluate")` and no `tool.hook(...)`, so it cannot allow,
// deny or rewrite a tool call: approval behaviour is exactly what it would be
// without this file. Every read is wrapped in try/catch, so a broken install (a
// deleted collections root, an unreadable file) can never break a session.
//
// Silent when indexed has no collections, so a machine or repo that does not use
// indexed sees no behavioural change and pays no tokens.
//
// Debug: INDEXED_HOOK_LOG=/path/to/log appends one JSON line per firing.
// Remove with `indexed install opencode --remove`.
//
// `{{COLLECTIONS_ROOT}}` below is an install-time placeholder: this file is not
// valid JavaScript until `indexed install opencode` has baked the path in.

import fs from "node:fs"
import path from "node:path"

// The collections root this install points at, baked in as a JS string literal
// (JSON string escaping is JS string escaping), so a --home path containing $,
// backticks or quotes stays a literal path instead of something JS evaluates.
const COLLECTIONS_ROOT = {{COLLECTIONS_ROOT}}

function safeCwd() {
  try {
    return process.cwd()
  } catch (_) {
    return ""
  }
}

// One JSON line per hook firing, only when INDEXED_HOOK_LOG is set. Tracing must
// never be the reason a session fails, so every failure here is swallowed.
function trace(event, fields) {
  try {
    const file = process.env.INDEXED_HOOK_LOG
    if (!file) return
    fs.appendFileSync(
      file,
      JSON.stringify({ ts: new Date().toISOString(), event, ...fields }) + "\n",
    )
  } catch (_) {
    // Debug output only: ignore.
  }
}

// Whether indexed has anything to search. Memoised per process and re-checked
// when the working directory changes or the memo ages out: half the check is
// cwd-relative (a project can carry its own `.indexed/collections.json`) and
// `context` fires on every model round-trip, so an uncached filesystem walk
// would be paid per turn — but a long session must still notice a collection
// created (or deleted) after it started.
//
// The directory is the plugin's own process cwd: the `context` payload on
// v2.3.2 carries no session directory (its keys are sessionID/model/system/
// messages/options/agent/tools), and `setup` runs once per plugin instance. A
// wrong directory only costs one omitted nudge line, never a wrong edit.
const CACHE_TTL_MS = 30000
let cached = { cwd: null, hasCollections: false, at: 0 }

function hasCollections() {
  const cwd = safeCwd()
  if (cached.cwd === cwd && Date.now() - cached.at < CACHE_TTL_MS) {
    return cached.hasCollections
  }
  let found = false
  try {
    // An explicit INDEXED_COLLECTIONS_HOME wins over the baked-in root, so a
    // shell that points indexed somewhere else is followed by the nudge too.
    const root = process.env.INDEXED_COLLECTIONS_HOME || COLLECTIONS_ROOT
    if (root) {
      try {
        found = fs.readdirSync(root).length > 0
      } catch (_) {
        found = false
      }
    }
    if (!found && cwd) {
      try {
        found = fs.existsSync(path.join(cwd, ".indexed", "collections.json"))
      } catch (_) {
        found = false
      }
    }
  } catch (_) {
    found = false
  }
  cached = { cwd, hasCollections: found, at: Date.now() }
  return found
}

// Two sentences: what to call, and how to use what comes back.
function nudge() {
  if (!hasCollections()) return ""
  return [
    "This machine has indexed collections: for questions about behaviour, ownership or intent, call indexed semantic search before shell search — inside the `execute` tool write `await tools.indexed.search({ query: \"...\" })` or `tools.indexed.search_collection({ collection: \"...\", query: \"...\" })` (on a `codemode: false` install the flat tool is `indexed_search`).",
    "Follow a hit's `line_span` to the real file:line before answering or editing; shell grep/rg stays right for exact strings and non-indexed paths.",
  ].join(" ")
}

export default {
  id: "indexed-nudge",
  async setup(ctx) {
    try {
      if (!ctx || !ctx.session || typeof ctx.session.hook !== "function") return
      await ctx.session.hook("context", (e) => {
        try {
          if (!Array.isArray(e?.system)) return e
          // Length BEFORE the push: the trace documents what the hook added.
          const systemLen = e.system.length
          const text = nudge()
          if (text) e.system.push({ type: "text", text })
          trace("session.context", {
            cwd: safeCwd(),
            systemLen,
            injected: Boolean(text),
          })
          return e
        } catch (_) {
          return e
        }
      })
    } catch (_) {
      // A plugin that cannot register is a plugin that does nothing, which is
      // the only safe failure mode for a nudge.
    }
  },
}
