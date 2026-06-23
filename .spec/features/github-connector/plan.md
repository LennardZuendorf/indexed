---
type: feature-plan
feature: github-connector
sibling: tech.md
parent: ../../plan.md
updated: 2026-06-23
---

# Feature: GitHub Projects & Issues Connector — Implementation Plan

Delivers a read-only GitHub connector in vertical slices: config+auth first, then
the GraphQL reader (issues → PRs → projects), then the parsing-backed converter
and registry wiring (create works E2E), then smart incremental update. Each unit
is test-first against a mocked GraphQL boundary; FAISS/embeddings run on small
fixtures per the repo's "mock the network, not the engine" rule.

**Parent:** [../../plan.md](../../plan.md)
**Requirements:** [product.md](product.md)
**Architecture:** [tech.md](tech.md)

**Feature gate:** Starts now — depends only on shipped infra (connectors, parsing,
config, update factory), all `DONE` in root [plan.md](../../plan.md).

---

## Problem Frame

The connector reuses every existing seam (BaseConnector protocol, registry
dispatch, update factory, ParsingModule), so the risk is concentrated in two new
places: GraphQL fetching/auth and the chunk-hash update optimization. Units are
ordered so a usable create-only connector lands before the update work, and so the
cross-cutting chunk-hash change is isolated in its own unit behind tests.

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Index repository issues and pull requests](product.md#requirement-index-repository-issues-and-pull-requests) | github-connector/2, github-connector/4 |
| R2 | [Index GitHub Projects v2 boards](product.md#requirement-index-github-projects-v2-boards) | github-connector/3, github-connector/4 |
| R3 | [Token resolution via config, env, or GitHub CLI](product.md#requirement-token-resolution-via-config-env-or-github-cli) | github-connector/1 |
| R4 | [Efficient GraphQL fetching with pagination and rate limiting](product.md#requirement-efficient-graphql-fetching-with-pagination-and-rate-limiting) | github-connector/2 |
| R5 | [Filtering by state, labels, and selectors](product.md#requirement-filtering-by-state-labels-and-selectors) | github-connector/2 |
| R6 | [Smart incremental update](product.md#requirement-smart-incremental-update) | github-connector/5, github-connector/6 |
| R7 | [Parse via the shared parsing module](product.md#requirement-parse-via-the-shared-parsing-module) | github-connector/4 |
| R-cfg | Dynamic creation / registry wiring | github-connector/1, github-connector/4 |

---

## Key Technical Decisions

1. **GraphQL v4 over httpx, not REST/PyGithub.** One query yields issues+labels+comments; Projects v2 is GraphQL-only; matches existing async readers; no heavy new dependency. See [tech.md](tech.md) § GraphQL reader.
2. **Auth `auto`: config/env → `gh auth token` → error.** `gh` optional, never required, never called when a token is set. Mirrors `ChangeTracker` auto.
3. **Single unified connector** (Cloud + GHES by base URL), per the Outline template.
4. **Smart update = `since` filter + chunk-hash reuse.** Server-side cutoff like other connectors, plus reuse of unchanged chunks' vectors — promoted as a cross-cutting engine improvement.

---

## Unit IDs

Units are `github-connector/n`, assigned once and never renumbered. Cite in
commits (`feat(connectors): github-connector/2 ...`).

---

### github-connector/1 — Config, schema & auth resolver

**Goal:** `GitHubConfig`, `auth.resolve_token()`, and registry wiring exist so the connector type is discoverable and credentials resolve.

**Requirements:** R3, R-cfg

**Dependencies:** —

**Files:**

```
packages/indexed-connectors/src/connectors/github/__init__.py
packages/indexed-connectors/src/connectors/github/schema.py
packages/indexed-connectors/src/connectors/github/auth.py
packages/indexed-connectors/src/connectors/registry.py        # add github rows
```

**Test scenarios:**

- Explicit `token` wins over `gh`; `GITHUB_TOKEN` env used when config empty.
- `gh auth token` used when no explicit token (subprocess mocked).
- No token + no `gh` → `ConfigurationError` naming env var and `gh auth login`.
- `repos`/`project` strings parse to `(owner, repo)` / `(owner, number)`.

**Verification:** `uv run pytest tests/unit/indexed_connectors/github/test_auth.py tests/unit/indexed_connectors/github/test_schema.py -q` green; `get_connector_class("github")` resolves.

---

### github-connector/2 — GraphQL reader: issues (pagination, filters, rate limit)

**Goal:** Async reader fetches issues for `repos` with labels+comments, paginated, filtered by state/labels/since, with backoff.

**Requirements:** R1, R4, R5

**Dependencies:** github-connector/1

**Files:**

```
packages/indexed-connectors/src/connectors/github/queries.py
packages/indexed-connectors/src/connectors/github/github_graphql_reader.py
```

**Test scenarios:**

- Two-page issue set fully read via `endCursor` (mocked GraphQL responses).
- `state`/`labels` translate into `filterBy`/`states` arguments.
- 403/429 + GraphQL `RATE_LIMITED` triggers retry/backoff, then succeeds.
- Raw-document dict shape matches the contract in tech.md.

**Verification:** `uv run pytest tests/unit/indexed_connectors/github/test_reader.py -q` green.

---

### github-connector/3 — Reader: pull requests & Projects v2

**Goal:** Reader also fetches PR threads (when enabled) and resolves a Project v2 board to items across repos (incl. drafts), deduping by id and attaching field values.

**Requirements:** R1, R2

**Dependencies:** github-connector/2

**Files:**

```
packages/indexed-connectors/src/connectors/github/queries.py        # PR + project queries
packages/indexed-connectors/src/connectors/github/github_graphql_reader.py
```

**Test scenarios:**

- `include_pull_requests=true` adds PR documents; `false` omits them.
- Project board with items in two repos yields both, with `project_fields` populated.
- Draft project item indexed as standalone document.
- Issue present in both `repos` and `project` emitted once (dedupe).

**Verification:** `uv run pytest tests/unit/indexed_connectors/github/test_reader_projects.py -q` green.

---

### github-connector/4 — Converter + connector + create E2E

**Goal:** Converter turns raw items into indexed chunks via `ParsingModule`; `GitHubConnector` wires reader+converter and `from_config`; `collection_service` dispatches `github`. Create works end-to-end.

**Requirements:** R1, R2, R7, R-cfg

**Dependencies:** github-connector/3

**Files:**

```
packages/indexed-connectors/src/connectors/github/github_document_converter.py
packages/indexed-connectors/src/connectors/github/connector.py
packages/indexed-core/src/core/v1/engine/services/collection_service.py   # github dispatch
```

**Test scenarios:**

- Markdown body chunked via `parse_bytes(..., "content.md")`; first chunk is item header.
- Comments and `project_fields` appear in chunk text/metadata.
- `BaseConnector` runtime-checkable conformance holds.
- System test: build a small collection from mocked reader output into `tmp_path` and search it.

**Verification:** `uv run pytest tests/unit/indexed_connectors/github/test_converter.py -q` and a `tests/system` create+search test green.

---

### github-connector/5 — Incremental update: `since` cutoff

**Goal:** `indexed index update` on a GitHub collection fetches only items changed since the manifest cutoff.

**Requirements:** R6

**Dependencies:** github-connector/4

**Files:**

```
packages/indexed-core/src/core/v1/engine/factories/update_collection_factory.py   # github branch
```

**Test scenarios:**

- Update passes `modified_since` from `manifest.lastModifiedDocumentTime` (minus buffer) into the reader.
- Reader injects `since` into `filterBy`; only changed issues fetched (mocked).
- Manifest `lastModifiedDocumentTime` advances after a successful update.

**Verification:** `uv run pytest tests/unit/indexed_core/ -q -k github_update` green.

---

### github-connector/6 — Chunk-hash reuse on update (cross-cutting)

**Goal:** On UPDATE, reuse FAISS vectors for chunks whose `content_hash` is unchanged; embed only changed/new chunks. Promoted as an engine-wide improvement.

**Requirements:** R6

**Dependencies:** github-connector/5

**Files:**

```
packages/indexed-core/src/core/v1/engine/core/documents_collection_creator.py
```

**Test scenarios:**

- Re-indexing a document with one changed chunk embeds only that chunk; unchanged chunk vectors retained.
- Document with no chunk changes results in zero new embeddings.
- Search results remain correct after a hash-reuse update.

**Verification:** `uv run pytest tests/unit/indexed_core/ -q -k chunk_hash` green; full suite + coverage >85% before push.

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| github-connector/1 | /2, /4 | — |
| github-connector/2 | /3 | /1 |
| github-connector/3 | /4 | /2 |
| github-connector/4 | /5 | /3 |
| github-connector/5 | /6 | /4 |
| github-connector/6 | — | /5 |

---

## Progress

| Unit | Status |
|---|---|
| github-connector/1 | NOT STARTED |
| github-connector/2 | NOT STARTED |
| github-connector/3 | NOT STARTED |
| github-connector/4 | NOT STARTED |
| github-connector/5 | NOT STARTED |
| github-connector/6 | NOT STARTED |
