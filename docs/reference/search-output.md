# Search result reference (`indexed.search/1`)

Successful machine searches share one shape: `indexed index search --json`
and the MCP tools `search` / `search_collection` use the same payload builder.
The MCP tools take five optional search kwargs — see [MCP parameters](#mcp-parameters).
For CLI calls, check the exit code before parsing stdout: a non-zero exit may
contain a non-JSON Rich error panel. On exit 0, parse JSON and read `schema`;
MCP results have no process exit code, so read `schema` directly.

- `schema: "indexed.search/1"` → the success shape below.
- no `schema`, an `error` string instead → the request failed. A failed request
  never reads as "nothing matched".

## Example payload

Captured from a real run, not authored by hand: two files (`cache.py` and
`caching.md`) indexed into a `files` collection, then

```bash
indexed index search "how is the cache keyed and invalidated" -c docs-demo --json
```

```json
{
  "schema": "indexed.search/1",
  "query": "how is the cache keyed and invalidated",
  "counts": {
    "documents": 2,
    "hits": 8
  },
  "collections": [
    "docs-demo"
  ],
  "collection_errors": [],
  "documents": [
    {
      "collection": "docs-demo",
      "source_type": "localFiles",
      "id": "caching.md",
      "url": "file:///var/lib/srv/hermes/profiles/prism/cache/scratch/docs-demo/caching.md",
      "score_kind": "l2_squared",
      "hits": [
        {
          "relevance": 0.5228,
          "score": 0.9544,
          "locator": {
            "kind": "headings",
            "headings": [
              "Caching notes",
              "Invalidation"
            ]
          },
          "text": "Caching notes > Invalidation\nEntries are dropped when the document's content hash changes. There is no time-based expiry."
        },
        {
          "relevance": 0.4585,
          "score": 1.083,
          "locator": {
            "kind": "headings",
            "headings": [
              "Caching notes"
            ]
          },
          "text": "Caching notes\nThe cache is keyed by collection and document id, so a document never reads another collection's entry."
        },
        {
          "relevance": 0.4143,
          "score": 1.1713,
          "locator": {
            "kind": "document"
          },
          "text": "caching.md"
        }
      ]
    },
    {
      "collection": "docs-demo",
      "source_type": "localFiles",
      "id": "cache.py",
      "path": "/var/lib/srv/hermes/profiles/prism/cache/scratch/docs-demo/cache.py",
      "score_kind": "l2_squared",
      "hits": [
        {
          "relevance": 0.462,
          "score": 1.0761,
          "locator": {
            "kind": "document"
          },
          "text": "cache.py"
        },
        {
          "relevance": 0.4125,
          "score": 1.1751,
          "locator": {
            "kind": "line_span",
            "start_line": 4,
            "end_line": 6
          },
          "text": "def cache_key(collection, document_id):\n    \"\"\"Stable cache key for one document of a collection.\"\"\"\n    return f\"{collection}:{document_id}\""
        },
        {
          "relevance": 0.4001,
          "score": 1.1998,
          "locator": {
            "kind": "line_span",
            "start_line": 14,
            "end_line": 16
          },
          "text": "def cache_put(store, collection, document_id, value):\n    store[cache_key(collection, document_id)] = value\n    return value"
        },
        {
          "relevance": 0.3968,
          "score": 1.2065,
          "locator": {
            "kind": "line_span",
            "start_line": 9,
            "end_line": 11
          },
          "text": "def cache_get(store, collection, document_id):\n    key = cache_key(collection, document_id)\n    return store.get(key)"
        },
        {
          "relevance": 0.3502,
          "score": 1.2997,
          "locator": {
            "kind": "line_span",
            "start_line": 1,
            "end_line": 3
          },
          "text": "\"\"\"Cache helpers for the demo collection.\"\"\""
        }
      ]
    }
  ]
}
```

Read that payload once and the rest of this page is a field list: document facts
(`collection`, `source_type`, `id`, `path`/`url`, `score_kind`) stated once per
document, hits carrying `relevance`, `score`, `locator`, `text`, and the three
opt-in extras — document `git`, hit `git` and `freshness[]` — documented below.
The example above is a plain files search: git provenance, line blame, the git
re-rank and freshness are all off by default, so none of them appears in it.

## Top level

| Key | Type | Meaning |
|---|---|---|
| `schema` | string | Always `indexed.search/1` today. Branch on it; any incompatible change bumps it. |
| `query` | string | The query as submitted. |
| `counts.documents` | int | Number of entries in `documents`. |
| `counts.hits` | int | Total hits across all documents. |
| `collections` | string[] | Collections that were **searched**. Empty means nothing was searched (no collections, or none searchable) — that is not the same as "searched and nothing matched". A collection whose *requested option* was skipped is still listed here, because it was searched and its documents are in the payload; it then also appears in `collection_errors`. |
| `collection_errors` | object[] | Always present, `[]` when every request was carried out as asked. Each entry is `{"collection": "<name>", "error": "<message>"}` and means **something was not done as asked** — which is not the same as "this collection failed". Read `collections` to tell the two states apart: a collection that **failed** is absent from `collections` and contributes no documents; a collection whose requested Git option was **skipped** is in `collections` with its documents present, just unfiltered/unranked (see [Requests that were not carried out](#requests-that-were-not-carried-out)). Entries are per request-not-applied, so one collection can have more than one. CLI collections with readable status but no indexers also appear here when other collections are searched. The CLI resolves `collections` through status, so a collection with an unreadable manifest is omitted from both arrays. MCP `search` enumerates every collection directory, so a collection it cannot search is reported here; `search_collection` checks status first and returns a top-level error for a present but unusable named collection (see Failures). |
| `documents` | object[] | Matched documents, best first. A document's position reflects its **best** hit; full-precision ties keep discovery order. Ranking happens before output scores are rounded. |
| `freshness` | object[], optional | One verdict per successfully searched collection, present **only** when freshness was requested (`include_freshness` / `--freshness`). Omitted — not `[]` — otherwise. See [`freshness[]`](#freshness). |

## Document object

| Key | Type | Meaning |
|---|---|---|
| `collection` | string | Which collection the document came from. |
| `source_type` | string, optional | The collection's reader type: `localFiles`, `jira`/`jiraCloud`, `confluence`/`confluenceCloud`, `outline` or `github`. A collection is fed by one reader, so this is stated once. Omitted when the collection's manifest does not record it. |
| `id` | string | The document's identity inside its collection (a file name, a page id). |
| `path` | string, optional | Absolute source path. Present when the hit locators supply exactly one distinct path; that path is hoisted here and removed from the locators. With multiple distinct paths, document `path` is omitted and each located hit retains its own `locator.path`. |
| `url` | string, optional | Where a human or agent opens the whole document. Omitted when unknown, and dropped when it only restates `path` as `file://<path>`. |
| `score_kind` | string | What `score` means for this document: `l2_squared` (v1 collections), `cosine` (v2 collections), `rerank` (v2 with `[core.v2.rerank]` enabled) or `git-rerank` (v2 files collection whose git-signal re-rank actually scored candidates). `git-rerank` is reported **on top of** the base kind: it says the raw score is a blended one, not a different engine. `rerank` wins when both apply — the git pass then only decides which candidates reach the cross-encoder. See [What `score_kind` changes about `relevance`](#what-score_kind-changes-about-relevance). |
| `git` | object, optional | Last commit touching this file, present only when `git_provenance` was requested and git answered for the indexed snapshot. See [Document `git` block](#document-git-block). |
| `hits` | object[] | The matched chunks of this document, best relevance first. |

### Document `git` block

Six keys, always all six together — a partial block is never emitted.

| Key | Type | Meaning |
|---|---|---|
| `commit` | string | Full commit SHA (`%H`): 40 hex characters in a SHA-1 repository. |
| `short` | string | Abbreviated SHA (`%h`), as `git log --oneline` prints it. |
| `author` | string | Author name of that commit. |
| `email` | string | Author email of that commit. |
| `committedAt` | string | Commit time as strict ISO-8601 with the commit's own UTC offset (`2026-11-15T09:22:52+01:00`), not a local rendering. |
| `subject` | string | Commit subject, truncated to its first 200 characters. |

When git cannot answer, the **whole block is omitted** rather than carrying six
`null`s: no key inside `git` is ever null. That covers a non-repository source
directory, an untracked file, a path with no history, a non-files collection,
and — the case that matters most — a file whose indexed snapshot is no longer
current: a file **modified since it was indexed** gets no `git` block, because
`git log` answers for the file as it is *now* and crediting that commit would
attribute text the commit never contained. A file with uncommitted changes is
treated the same way.

Opt-in: `git` appears only when provenance was asked for (`git_provenance` on the
MCP tool, `--git-provenance` on the CLI) or enabled by
`[core.v1.search] git_provenance`.

## Hit object

| Key | Type | Meaning |
|---|---|---|
| `relevance` | float | Higher is better, **comparable across collections and engines**. Derived from the raw score per `score_kind`: `1 - score/2` for `l2_squared`, the score itself for `cosine` **and `git-rerank`**, a sigmoid of the logit for `rerank`. Normally 0–1, but it is not clamped: an `l2_squared` hit at a distance above 2 goes negative, and a `git-rerank` hit stays on the cosine scale it was blended from. Emitted values are rounded to 4 decimals after ranking; preserve payload order for near ties. Use relevance to compare hits across collections. |
| `score` | float | The raw engine score, rounded to 4 decimals. Only comparable **within one `score_kind`**. |
| `locator` | object | Where the hit sits. See below. |
| `text` | string | The matched chunk's text. Only an exact leading `# <metadata.file_path>\n` prefix is removed when that metadata path is present; other text stays unchanged. `kind: "document"` means position unknown: the text may still be a body fragment, not a title or whole-document chunk. |
| `git` | object, optional | Line-level blame for this hit's own span, present only when line blame was requested and the chunk records a span. See [Hit `git` block](#hit-git-block). |

### What `score_kind` changes about `relevance`

`relevance` is the one number you can sort across collections, so each kind maps
onto it deliberately:

| `score_kind` | `relevance` | Note |
|---|---|---|
| `l2_squared` | `1 - score/2` | v1 collections: squared-L2 distance over unit vectors, so the formula recovers cosine. Can go negative above distance 2. |
| `cosine` | `score` unchanged | v2 default: already a bounded similarity. |
| `rerank` | `1 / (1 + e^-score)` | v2 cross-encoder: the raw score is an unbounded logit, squashed into (0, 1). |
| `git-rerank` | `score` unchanged | The blended cosine is returned **as-is** (see below). |

For `git-rerank` the raw score is `cosine + recency_weight*recency +
churn_weight*churn + author_weight*author`, with every signal in `[0, 1]`, so the
result stays on the cosine scale and — having added only non-negative terms —
**may exceed 1.0**. It is never clamped and never re-based onto (0, 1): doing so
would make a re-ranked collection incomparable with the unranked one beside it.
A signal git cannot answer contributes nothing rather than a guessed value.

The kind is reported only when the re-rank actually scored something. A
requested `git_rerank` that a collection cannot serve leaves that collection's
`score_kind` at its base kind and names it in `collection_errors`, so unranked
rows never read as re-ranked.

### Hit `git` block

Blame for the hit's **own** line span, not the file's whole-file commit — so a
chunk can name a different commit than its document's `git` block.

| Key | Type | Meaning |
|---|---|---|
| `commit` | string | Full SHA of the commit that last touched the span. The newest commit among the span's lines wins; a tie resolves to the later line, so the answer is deterministic. |
| `short` | string | Abbreviated SHA. |
| `author` | string | Author name. |
| `email` | string | Author email. |
| `committedAt` | string | Commit time, strict ISO-8601 with the commit's own offset. |
| `subject` | string | Commit subject. |
| `startLine` | int | First line of the covered span, **1-based**. |
| `endLine` | int | Last line of the covered span, **1-based and inclusive**. |
| `uncommitted` | bool | Present instead of the six commit keys when any line of the span is a working-tree edit. |

`startLine`/`endLine` are the same 1-based inclusive convention as a
`line_span` locator, so a hit's `locator.start_line` and its `git.startLine`
describe the same lines. They are reported back on every attributed span so a
consumer can show exactly what the attribution covers.

Two shapes, never mixed:

- Committed span → the six commit keys **plus** `startLine` and `endLine`.
- Span containing any uncommitted line → `{"uncommitted": true, "startLine": n,
  "endLine": m}` and **no commit keys at all**. A working-tree edit is the last
  touch; naming a committed ancestor would be a whole-file guess wearing a
  line-level label.

Omitted entirely when line blame was not requested, when the chunk records no
line span (prose, PDFs, page-only locators), or when blame cannot answer for the
span — untracked file, binary file, non-repository. It is never borrowed from the
document's block.

Opt-in: `git_line_blame` on the MCP tool, `--git-line-blame` on the CLI, or
`[core.v1.search] git_line_blame`.

## Locator kinds

`locator.kind` is load-bearing: read only the keys that kind declares. Precision
order is `line_span` > `page` > `headings` > `document`; a chunk that has line
data *and* headings gets `line_span` — provided a path is resolvable too (from the
chunk's `file_path` or its `file://` url), otherwise it falls through to `page`,
`headings` or `document`. A range is never invented to fill the field
— a source with no position known gets `document`.

| `kind` | Keys | What it means |
|---|---|---|
| `line_span` | `start_line`, `end_line`, optional `path` | Code, from tree-sitter chunks. Lines are **1-based and inclusive** — what `grep -n` prints and what your editor shows. `path` stays on each located hit when multiple distinct paths prevent a document `path`. |
| `page` | `page`, optional `path` | Positive page metadata, when supplied by the producer. `page` is 1-based; a PDF/DOCX source alone does not guarantee this metadata. |
| `headings` | `headings` | Prose: Markdown, Jira, Confluence, Outline. The heading path down to the chunk, e.g. `["Caching notes", "Invalidation"]`. Never empty — a chunk with no real headings degrades to `document` rather than claiming a precision it does not have. |
| `document` | *(none)* | The chunk carries no usable position. Open the source for context; the chunk can be any body fragment, including one of many chunks. |

## `freshness[]`

An advisory: how far behind its source working tree is each collection's index.
Present **only** when asked for — `include_freshness` on an MCP search tool or
`--freshness` on the CLI — and omitted (not `[]`) otherwise. One element per
successfully searched collection; a collection that failed has no verdict
because it has no results here.

| Field | Type | Meaning |
|---|---|---|
| `collection` | string | The collection this verdict is about. |
| `status` | string | One of the three verdict words below. |
| `reason` | string, null | Reason code; `null` exactly when `status` is `fresh`, set whenever it is `stale` or `unknown`. |
| `baseline` | string, null | The 7-character commit the index was built from. `null` when no baseline could be read at all: a non-files collection, a source directory that is not recorded (or not readable), no git repository, no `HEAD`, or no baseline recorded. A baseline that *is* recorded is echoed even when the verdict is `unknown` because that commit is missing from history — that is how a caller sees which commit git could not place. |
| `head` | string, null | The 7-character current `HEAD`; `null` when git could not resolve one. |
| `filesChanged` | int, null | How many files lie between the index and the working tree. Populated only when the verdict is `stale`; `null` when git did not count them, never a plausible-looking `0`. |
| `commitsBehind` | int, null | Commits between `baseline` and `head`. `0` when the baseline *is* `HEAD`; `null` when git could not count. |
| `detachedHead` | bool | True when the source repository's `HEAD` is detached; a `fresh` summary then names the commit it points at. |
| `summary` | string | The one line every surface prints — same verdict, same words, never re-worded by a caller. |

### Verdicts

| `status` | Meaning |
|---|---|
| `fresh` | The index matches the working tree. Content the index already contains does not make a collection stale, even if it is uncommitted. |
| `stale` | The source changed since indexing. `reason` is `source-changed` and `filesChanged` carries the count. |
| `unknown` | Git cannot answer. `reason` says why — one of the codes below. |

### Reason codes

The nine codes, verbatim. Each belongs to exactly one verdict.

| `reason` | Verdict | When |
|---|---|---|
| `source-changed` | `stale` | the source changed since it was indexed |
| `not-a-files-collection` | `unknown` | the collection has no files source to compare |
| `no-base-path` | `unknown` | the collection's source directory is not recorded in its manifest |
| `no-baseline` | `unknown` | no baseline recorded (indexed before change tracking) |
| `no-git-repository` | `unknown` | the source directory is not a git work tree |
| `no-head` | `unknown` | the repository has no commits yet |
| `history-missing` | `unknown` | the indexed commit is missing from this repository's history (shallow clone or pruned history) |
| `history-rewritten` | `unknown` | the indexed commit is no longer an ancestor of HEAD (history was rewritten) |
| `git-unavailable` | `unknown` | git could not answer |

`unknown` plus `history-missing` means **git cannot tell** — a shallow clone, a
pruned or fetched-away baseline commit — not that indexing failed. Read the pair
as "unknown", never as an error report and never as `fresh`: the contract is that
a degraded answer stays visible instead of being rounded up to a fabricated
`fresh`.

The same verdict appears elsewhere with the same wording: as the `Freshness` row
of `index inspect`, in that command's JSON output, and by default in the MCP
status resources (`resource://collections/status` and
`resource://collection/{name}`), which request it unconditionally.

## MCP parameters

Both search tools — `search` and `search_collection` — accept the same five
optional kwargs. Each one only *adds* to the payload or narrows the result set;
none changes its shape.

| kwarg | Type | Effect | Omitted means |
|---|---|---|---|
| `changed_since` | `string` | Keep only files changed since this git ref, tag or commit, including uncommitted and untracked changes. | **No filter** — the whole collection is searched. |
| `git_provenance` | `bool` | Adds the document [`git` block](#document-git-block). | The configured default, `[core.v1.search] git_provenance`. |
| `git_line_blame` | `bool` | Adds the hit [`git` block](#hit-git-block). | The configured default, `[core.v1.search] git_line_blame`. |
| `git_rerank` | `bool` | Re-ranks by git recency, churn and author signals; documents then report `score_kind: "git-rerank"`. | The configured default, `[core.v1.search] git_rerank`. |
| `include_freshness` | `bool` | Adds the [`freshness[]`](#freshness) array. | No `freshness` array — this kwarg has no configured default. |

**Omitting a kwarg means "use the configured default", not `false`.** The three
git flags are `Optional[bool]` and start as `None`, so the tool can tell "the
caller said nothing" from "the caller said no". A config-enabled
`git_provenance`, `git_line_blame` or `git_rerank` therefore still applies when
the kwarg is left out, and an explicit `false` turns it off for that one call —
the same precedence the CLI flags have over the same config keys.

`changed_since` has no "off" value: omit it to filter nothing. `include_freshness`
has no config key either, so it is purely per-call — `false` and omission are
indistinguishable, and neither yields a `freshness` array.

One more rule, because a requested option can degrade: **an option that cannot be
honoured is named, never silently ignored.** A `changed_since` a collection cannot
serve (`no-git-repository`, `not-a-files-collection`, `unknown-ref`,
`v1-engine`) or a `git_rerank` that could not run (`no-git-repository`,
`not-a-files-collection`, `v1-engine`) adds that collection to
`collection_errors` with a one-line reason while its rows stay unfiltered or
unranked. `v1-engine` is the common case: v1 is the default engine, so a default
store answering a git option reports it. Unfiltered rows never read as filtered,
unranked rows never read as re-ranked.

Scope note: the two tools search and report. Neither call watches files — a search answers
from whatever the server had already indexed, and cannot itself refresh a collection. The
server those tools run in **can** keep its collections fresh between calls, but only if it
was configured to: that is opt-in, off by default, and limited to `localFiles` collections —
see [Keeping an MCP server fresh](../../README.md#keeping-an-mcp-server-fresh). What the
payload carries is unchanged either way: no answer-faithfulness or answer-quality score —
`relevance`, `score`, provenance and freshness are the whole of it.

## Failures

Check CLI exit status **before** parsing stdout. A non-zero exit is a failed
request; stdout can contain a JSON error body or a non-JSON Rich error panel.
For example, a missing named collection returns JSON and exits 1:

```console
$ indexed index search "x" -c nope --json
{
  "error": "Collection 'nope' not found"
}
$ echo $?
1
```

An `IndexedError` escaping the command reaches the top-level CLI handler, which
prints its Rich panel to **stdout** and exits 1, 2 for configuration errors, or
3 for storage errors. Ordinary logs and search notices go to stderr. The JSON
stdout guarantee applies to normal command returns, not this escape path.

Exit 0 alone does not mean success. An empty CLI store returns
`{"error": "No collections found"}` with exit 0. After the exit check, parse the
JSON and branch on `schema`; an error body has no success schema. In a success
payload, inspect `collection_errors` for requests that were not carried out and
`collections` to see what was searched. Empty `documents` with non-empty
`collections` means nothing matched in those collections. Empty `collections`
means no collection was searched; inspect `collection_errors` to distinguish an
empty store from all searches failing. A collection that appears in **both**
arrays was searched — the entry says a requested option was not applied to it, so
its rows are a superset of what you asked for, not a failure.

MCP has no exit code. Read `schema` first. Both MCP search tools report skipped
Git options in `collection_errors`. Global `search` also puts a collection it
could not search — including one whose manifest cannot be read — in
`collection_errors`; such a collection is absent from `collections`. Named
`search_collection` resolves status first instead: a collection present on disk
with an unreadable manifest or no indexers returns a top-level `{"error": "…",
"type": "MCPError"}`; an unknown name returns `{"error": "Collection 'x' not
found or has no indexers"}` without `type`. Neither body has a success schema. If
a boundary catches an `IndexedError`, `type` preserves its concrete class name,
such as `StorageError`; unexpected search/status exceptions are wrapped as
`MCPError`.

`--json` ignores `--compact` / `--no-content`; those shape the human view only.
CLI JSON and both MCP search tools always request matched chunk content, even
when MCP search config sets `include_matched_chunks = false`. The canonical
payload retains matched text and provenance.

The full failure table is in
[`docs/spec/tech/app/app-search-result-contract.md`](../spec/tech/app/app-search-result-contract.md).

## The optional extras, in one paragraph

Everything git-aware here is opt-in and additive. A document may carry `git` with
its last-touching commit — six keys, [Document `git` block](#document-git-block).
A hit may independently carry `git` for its own recorded line span, adding
1-based inclusive `startLine`/`endLine`, or `uncommitted: true` with no commit
keys at all — [Hit `git` block](#hit-git-block). A requested freshness advisory
adds `freshness[]`, one verdict per collection, with the three verdict words and
nine reason codes above ([`freshness[]`](#freshness)). A git re-rank reports
`score_kind: "git-rerank"` only when it actually scored candidates, and its
`relevance` is the blended cosine returned as-is (so it may exceed 1.0). When
none of this is requested, the payload is exactly the core shape documented
above. When a requested `changed_since` or `git_rerank` cannot be honoured, the
degradation is named in `collection_errors`; a requested document or hit `git`
block that git cannot answer is simply absent, exactly as the two `git` block
sections describe; and a requested freshness advisory never disappears — it
degrades to `unknown` with a reason code.

## Requests that were not carried out

`collection_errors` answers "was everything I asked for actually done?", not just
"did a collection fail?" Two states share the field, and `collections` tells them
apart:

- **Failed** — the collection could not be searched. It is absent from
  `collections` and contributes no documents (see Failures).
- **Option skipped** — the collection *was* searched and its documents are in
  `documents`, but a per-collection Git option could not be applied to it: a
  `--changed-since` filter leaves its rows unfiltered, a `--git-rerank` leaves
  them ordered by similarity only. The collection stays in `collections`, and the
  entry names the ref and the reason.

Entries are per request that was not applied, not per collection: asking for both
options on a collection that can honour neither yields two entries for that name.
CLI and MCP `search` render the skip line identically; the CLI human view prints
the same line as a warning panel.

One asymmetry follows from where the check lives: the CLI resolves the ref before
searching and refuses the whole request when it does not resolve
(`{"error": "--changed-since '<ref>' is not a valid git ref in <repo>"}`, exit
`1`) — naming a collection does not change that. The MCP tools hand the ref to the
engine unvalidated, so the same request there returns a success payload with the
collection in both arrays and its rows unfiltered. A skipped filter therefore never
means "the ref was fine".

Captured from a real run: a v1 collection `v1demo` and a v2 collection `demo` over
the same clean git checkout, so nothing had changed since `HEAD`. The counts depend
on how the fixture chunks; the `collections` and `collection_errors` arrays are the
contract.

```console
$ indexed index search "retry" --json --changed-since HEAD
{
  "schema": "indexed.search/1",
  "query": "retry",
  "counts": {
    "documents": 4,
    "hits": 15
  },
  "collections": [
    "v1demo",
    "demo"
  ],
  "collection_errors": [
    {
      "collection": "v1demo",
      "error": "changed_since 'HEAD' was not applied: git filtering applies to v2 collections only; results are unfiltered"
    }
  ],
  "documents": [ … ]
}
$ echo $?
0
```

`documents` is elided here: it held all four `v1demo` documents
(`README.md`, `docs/retry.md`, `src/cache.py`, `src/retry.py`), because `v1demo`
could not be filtered, while `demo` was filtered and matched nothing.

So: a collection named in `collection_errors` **and** listed in `collections` was
searched, and its rows are a superset of what you asked for — keep them, and
narrow client-side if the request was strict. Only a collection named in
`collection_errors` and **absent** from `collections` failed outright.

Naming such a collection explicitly is the other case: the request is refused
before searching, not partially answered.

```console
$ indexed index search "retry" -c v1demo --json --changed-since HEAD
{
  "error": "--changed-since 'HEAD' cannot be applied: collection 'v1demo' uses the v1 engine (git filtering is v2-only)"
}
$ echo $?
1
```
