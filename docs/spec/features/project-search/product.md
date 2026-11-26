---
type: feature-product
feature: project-search
sibling: tech.md
parent: ../../product.md
updated: 2026-11-26
---

# Feature: Project Search — Product

One query answers from every source a project declared — GitHub issues, the
local Markdown wiki and current source code — and says, per source, whether it
actually answered.

**Parent:** issue [#340](https://github.com/LennardZuendorf/indexed/issues/340)
(milestone [Merged Project Search](https://github.com/LennardZuendorf/indexed/milestone/12)) ·
**Architecture:** [tech.md](tech.md) · **Plan:** [plan.md](plan.md) ·
Builds on [workspace-selection](../workspace-selection/product.md).

## Problem

A workspace already declares its collections in a committed `indexed.toml`
(#344) and one search walks them. But the payload cannot say what was *meant*
to be searched: `collections` lists only what the engine answered for, and
`collection_errors` only what the engine complained about. A source that was
never built, whose index was deleted, or that indexes nothing therefore leaves
no trace at all — the query returns two sources' evidence and reads exactly like
a corpus that only ever had two sources.

That silence is fatal for what comes next. Every retrieval number this milestone
will publish (quality per source, latency, distractor rate) would be computed
against a payload that quietly drops a dead source, so a regression in one
source would look like a corpus property rather than a failure.

## Outcome

A search over a project's declared sources returns ranked evidence from each
source that answered, and a per-source record — `ok`, `empty`, `missing`,
`unusable` or `failed` — for every source that did not. Nothing is silent, and
one broken source does not blank the query.

## Requirements

- **R1 — Every hit is citable.** Each document keeps its collection, source type
  and id; each hit keeps a locator its source really supports (line span for
  code, headings for Markdown, document for an issue) and resolves to the file
  path, issue number or comment URL it came from.
- **R2 — Intent is visible.** The payload carries one `sources` entry per
  collection the request intended to search, in scope order, each with a
  `status` and — when it is not `ok` — an `error` naming the source and the
  remedy. A source that was intended but not searched is `missing` or
  `unusable`, never absent.
- **R3 — Empty is not "no match".** A collection that indexes zero documents
  reports `empty` with an error; a collection that was searched and simply had
  nothing to match the query reports `ok`. The two must never look alike.
- **R4 — One dead source does not blank the rest.** A search whose selection
  contains a vanished collection still returns the other sources and exits 0
  (the query *was* answered), naming the dead one per source. Asking for one
  collection by name that cannot be searched still fails: that request was not
  answered.
- **R5 — Detail is bounded.** A hit never carries a whole diff or a whole
  comment thread; comment text is chunked like any other body, so a hit is
  bounded by the chunker, not by the size of the source. The payload's size is
  asserted in the suite.
- **R6 — The contract is additive.** `sources` is a new key on the existing
  `indexed.search/1` shape; `collections`, `collection_errors`, `counts` and
  `documents` keep their meaning, so an existing consumer is unaffected.

## Non-goals

- Choosing between dense, reranked and hybrid retrieval, publishing quality or
  latency tables, distractor rates, and picking a default — those are measured
  on top of this payload, not with it (next card).
- Inferring a source *kind* ("issues", "wiki", "code") the store does not know:
  the payload reports the collection name and the reader type it actually has,
  and never guesses a taxonomy from a path.
- Per-request MCP workspace scope (#345); a server still resolves one workspace.

## Acceptance

Fixture: one repository whose `indexed.toml` selects three collections holding a
known answer each — a GitHub issue, a Markdown wiki page and a source file.

1. One search returns at least one hit per source; every hit's reference
   resolves to a real path/URL; `sources` lists all three as `ok`.
2. Delete one collection's data and re-run: the other two still return, the
   payload names the dead one as `missing` with an error, and the process exits 0.
3. Empty one collection's index and re-run: that source is `empty` with an
   error, and zero hits from it are not reported as "no match".
4. The payload stays under its byte budget and no hit text exceeds the chunker's
   bound.
