---
type: feature-plan
feature: github-connector
sibling: tech.md
parent: ../../plan.md
updated: 2026-09-07
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

**Feature gate:** Shipped — `src/indexed/connectors/github/`, registry rows,
`index create github` CLI subcommand, `since`-cutoff incremental update. See
[../../plan.md](../../plan.md) Feature 19.

---

## Problem Frame

The connector reuses every existing seam (`BaseConnector` protocol, the generic
`CONNECTOR_REGISTRY`/`NAMESPACE_REGISTRY` dispatch, `from_manifest` on the
connector itself, `ParsingModule`), so the risk concentrated in two new places:
GraphQL fetching/auth and the CLI entry point the original spec omitted.
Chunk-hash reuse (unit 6 below) was descoped mid-plan once research showed it
needs an on-disk schema change shared by every connector type, not a
GitHub-specific concern — see
[docs/superpowers/plans/2026-09-05-github-connector.md § Out of scope](../../../docs/superpowers/plans/2026-09-05-github-connector.md).

---

## Requirements Trace

| ID | Requirement | Units |
|---|---|---|
| R1 | [Index repository issues and pull requests](product.md#requirement-index-repository-issues-and-pull-requests) | github-connector/2, github-connector/4 |
| R2 | [Index GitHub Projects v2 boards](product.md#requirement-index-github-projects-v2-boards) | github-connector/3, github-connector/4 |
| R3 | [Token resolution via config, env, or GitHub CLI](product.md#requirement-token-resolution-via-config-env-or-github-cli) | github-connector/1 |
| R4 | [Efficient GraphQL fetching with pagination and rate limiting](product.md#requirement-efficient-graphql-fetching-with-pagination-and-rate-limiting) | github-connector/2 |
| R5 | [Filtering by state, labels, and selectors](product.md#requirement-filtering-by-state-labels-and-selectors) | github-connector/2 |
| R-deploy | [Support all GitHub deployment models](product.md#requirement-support-all-github-deployment-models) | github-connector/1, github-connector/2 |
| R6 | [Smart incremental update](product.md#requirement-smart-incremental-update) | github-connector/5, github-connector/6 (DESCOPED half) |
| R7 | [Parse via the shared parsing module](product.md#requirement-parse-via-the-shared-parsing-module) | github-connector/4 |
| R-cfg | Dynamic creation / registry wiring | github-connector/1, github-connector/4, CLI subcommand (below) |

---

## Key Technical Decisions

1. **GraphQL v4 over httpx, not REST/PyGithub.** One query yields issues+labels+comments; Projects v2 is GraphQL-only; matches existing async readers; no heavy new dependency. See [tech.md](tech.md) § GraphQL reader.
2. **Auth `auto`: config/env → `gh auth token` → error.** `gh` optional, never required, never called when a token is set. Mirrors `ChangeTracker` auto.
3. **Single unified connector** (Cloud + GHES by base URL), per the Outline template.
4. **Smart update = `since` filter, shipped; chunk-hash reuse, descoped.** Server-side cutoff like other connectors shipped as unit 5. Reuse of unchanged chunks' vectors (unit 6) turned out to be a cross-cutting engine change (new on-disk schema for `index_document_mapping.json`, shared by every connector type, no Core v2 story) — moved out of this plan; needs its own follow-up plan.

---

## Unit IDs

Units are `github-connector/n`, assigned once and never renumbered. Cite in
commits (`feat(connectors): github-connector/2 ...`).

---

### github-connector/1 — Config, schema, endpoint & auth resolver

**Goal:** `GitHubConfig` (incl. `resolve_graphql_url()`), `auth.resolve_token()`, and registry wiring exist so the connector type is discoverable, endpoints derive per deployment, and credentials resolve.

**Requirements:** R3, R-deploy, R-cfg

**Dependencies:** —

**Files:**

```
src/indexed/connectors/github/__init__.py
src/indexed/connectors/github/schema.py
src/indexed/connectors/github/auth.py
src/indexed/connectors/registry.py                    # CONNECTOR_REGISTRY + NAMESPACE_REGISTRY rows
src/indexed/protocols/models.py                        # SourceConfig.type Literal gains "github"
```

**Test scenarios:**

- Explicit `token` wins over `gh`; `GITHUB_TOKEN` env used when config empty.
- `gh auth token` used when no explicit token (subprocess mocked); `--hostname` passed for a non-default host.
- No token + no `gh` → `ConfigurationError` naming env var and `gh auth login`.
- `repos`/`project` strings parse to `(owner, repo)` / `(owner, number)`.
- `resolve_graphql_url()`: `github.com` → `api.github.com/graphql`; `octocorp.ghe.com` → `api.octocorp.ghe.com/graphql`; `github.example.com` → `github.example.com/api/graphql`; explicit `graphql_url` overrides all; scheme/trailing-slash in `host` is normalized.

**Verification:** `uv run pytest tests/unit/indexed/connectors/github/test_auth.py tests/unit/indexed/connectors/github/test_schema.py -q` green; `get_connector_class("github")` resolves.

**Status:** DONE.

---

### github-connector/2 — GraphQL reader: issues (pagination, filters, rate limit)

**Goal:** Async reader fetches issues for `repos` with labels+comments, paginated, filtered by state/labels/since, with backoff.

**Requirements:** R1, R4, R5

**Dependencies:** github-connector/1

**Files:**

```
src/indexed/connectors/github/queries.py
src/indexed/connectors/github/github_graphql_reader.py
```

**Test scenarios:**

- Two-page issue set fully read via `endCursor` (mocked GraphQL responses).
- `state`/`labels` translate into `filterBy`/`states` arguments.
- 403/429 + GraphQL `RATE_LIMITED` triggers retry/backoff, then succeeds; a real permission-scope 403 (no rate-limit headers) is NOT misclassified as rate-limiting.
- Reader posts to `config.resolve_graphql_url()` and honors `verify_ssl` (asserted via mocked client construction).
- Raw-document dict shape matches the contract in tech.md.
- `get_number_of_documents()` counts the same deduplicated set `read_all_documents()` yields (both call a cached, shared crawl — no double GraphQL pass).

**Verification:** `uv run pytest tests/unit/indexed/connectors/github/test_reader.py -q` green.

**Status:** DONE.

---

### github-connector/3 — Reader: pull requests & Projects v2

**Goal:** Reader also fetches PR threads (when enabled) and resolves a Project v2 board to items across repos (incl. drafts), deduping by id and attaching field values.

**Requirements:** R1, R2

**Dependencies:** github-connector/2

**Files:**

```
src/indexed/connectors/github/queries.py        # PR + project queries
src/indexed/connectors/github/github_graphql_reader.py
```

**Test scenarios:**

- `include_pull_requests=true` adds PR documents; `false` omits them.
- Project board with items in two repos yields both, with `project_fields` populated.
- Draft project item indexed as standalone document.
- Issue present in both `repos` and `project` emitted once (dedupe), keeping the union of both copies' `project_fields` rather than first-wins.
- An org-owned project probe that fails with `NOT_FOUND` on `path=["organization"]` falls through to the user-owned query instead of raising.

**Verification:** `uv run pytest tests/unit/indexed/connectors/github/test_reader_projects.py -q` green.

**Status:** DONE.

---

### github-connector/4 — Converter + connector + create E2E

**Goal:** Converter turns raw items into indexed chunks via `ParsingModule`; `GitHubConnector` wires reader+converter and `from_config`; the connector registers generically (`CONNECTOR_REGISTRY`/`NAMESPACE_REGISTRY` + `ConfigService.register()`) — no per-connector branch anywhere in core. Create works end-to-end.

**Requirements:** R1, R2, R7, R-cfg

**Dependencies:** github-connector/3

**Files:**

```
src/indexed/connectors/github/github_document_converter.py
src/indexed/connectors/github/connector.py
src/indexed/connectors/registry.py                       # github row (already added in unit 1)
src/indexed/cli/composition.py                            # register_app_config: GitHubConfig registration
```

**Test scenarios:**

- Markdown body chunked via `parse_bytes(..., "content.md")`; first chunk is item header.
- Comments and `project_fields` appear in chunk text/metadata.
- `BaseConnector` runtime-checkable conformance holds.
- System test: build a small collection from a mocked GraphQL transport (real reader+converter, HTTP stubbed) into `tmp_path` and search it.

**Verification:** `uv run pytest tests/unit/indexed/connectors/github/test_converter.py tests/unit/indexed/connectors/github/test_connector.py -q` and the system create+search test green.

**Status:** DONE. `collection_service.py`/`update_collection_factory.py` needed **zero** changes — both are fully registry/protocol-driven already (see tech.md § Dynamic creation for the corrected wiring description).

---

### github-connector/5 — Incremental update: `since` cutoff

**Goal:** `indexed index update` on a GitHub collection fetches only items changed since the manifest cutoff, and correctly rebuilds against the same host/endpoint the collection was created against.

**Requirements:** R6, R-deploy

**Dependencies:** github-connector/4

**Files:**

```
src/indexed/connectors/github/connector.py   # GitHubConnector.from_manifest
```

**Test scenarios:**

- Update passes `modified_since` from `manifest.lastModifiedDocumentTime` (minus a 60s safety buffer) into the reader.
- Reader injects `since` into `filterBy`; only changed issues fetched (mocked).
- `from_manifest` overlays `host`/`graphqlUrl` (plus `pageSize`/`maxConcurrentRequests`) from the manifest, not just the query-shaping fields — an update on a GHES/`*.ghe.com` collection rebuilds against the same endpoint it was created with, never silently falling back to `api.github.com`.
- Manifest `lastModifiedDocumentTime` advances after a successful update.

**Verification:** `uv run pytest tests/unit/indexed/connectors/github/test_connector.py -q -k manifest` green.

**Status:** DONE. Unlike the original spec's assumption, there is no `update_collection_factory.py` per-connector branch — the `since` cutoff and endpoint-overlay logic live entirely inside `GitHubConnector.from_manifest`, mirroring `OutlineConnector.from_manifest` exactly.

---

### github-connector/6 — Chunk-hash reuse on update (cross-cutting)

**Goal:** On UPDATE, reuse FAISS vectors for chunks whose `content_hash` is unchanged; embed only changed/new chunks. Promoted as an engine-wide improvement.

**Requirements:** R6

**Dependencies:** github-connector/5

**Files:**

```
src/indexed/core/v1/engine/core/documents_collection_creator.py
```

**Status:** DESCOPED — see "Corrections to the spec" /
"Out of scope: chunk-hash reuse" in
[docs/superpowers/plans/2026-09-05-github-connector.md](../../../docs/superpowers/plans/2026-09-05-github-connector.md).
No chunk hash is persisted anywhere on disk today; shipping this needs a schema
change to `index_document_mapping.json` shared by every connector (files/jira/
confluence/outline too), a migration story for existing collections, and has no
Core v2 story yet (v2 only has document-level hash-skip). The GitHub connector
is fully functional without it — `indexed index update` already re-fetches only
changed items (unit 5's `since` cutoff) and re-embeds their chunks, exactly like
every other connector today. Needs its own follow-up plan against
`documents_collection_creator.py`, scoped across all connector types, once a
migration approach is decided. Tracked at
[#90](https://github.com/LennardZuendorf/indexed/issues/90).

---

## CLI entry point (not in the original spec)

**Goal:** `indexed index create github --repo ... --project ... --host ...` — a
dedicated Typer subcommand mirroring `create files`/`jira`/`confluence`/`outline`,
since the CLI has no generic `--source <type>` flag and the original spec's
`indexed index create gh --source github` example never matched real CLI shape.

**Requirements:** R-cfg

**Dependencies:** github-connector/4

**Files:**

```
src/indexed/cli/knowledge/commands/_create_schema.py      # SourceSpec entry for "github"
src/indexed/cli/knowledge/commands/_create_commands.py    # @app.command("github")
src/indexed/cli/knowledge/commands/_create_options.py     # --repo/--project/--host/... options
src/indexed/cli/knowledge/commands/create.py               # generalized source_path_key (was hardcoded "url")
```

**Test scenarios:**

- `indexed index create github --repo octo/hello` builds a collection end-to-end (`TestCreateGithub`, mirrors `TestCreateOutline`'s direct-call + patch convention).
- `--token` reaches `GITHUB_TOKEN`/`INDEXED__sources__github__token` (was silently discarded before the fix wave — see lessons.md).
- A configured `[sources.github] host` in `config.toml` is read and preserved, not overwritten by the interactive prompt's default.

**Verification:** `uv run pytest tests/unit/indexed/knowledge/commands/test_create.py -q -k Github` green.

**Status:** DONE.

---

## Dependencies

| Unit | Blocks | Blocked by |
|---|---|---|
| github-connector/1 | /2, /4 | — |
| github-connector/2 | /3 | /1 |
| github-connector/3 | /4 | /2 |
| github-connector/4 | /5, CLI entry point | /3 |
| github-connector/5 | /6 | /4 |
| github-connector/6 | — | /5 — **descoped, not built** |

---

## Progress

| Unit | Status |
|---|---|
| github-connector/1 | DONE |
| github-connector/2 | DONE |
| github-connector/3 | DONE |
| github-connector/4 | DONE |
| github-connector/5 | DONE |
| github-connector/6 | DESCOPED — see "Out of scope: chunk-hash reuse" in [docs/superpowers/plans/2026-09-05-github-connector.md](../../../docs/superpowers/plans/2026-09-05-github-connector.md); needs its own follow-up plan |
| CLI entry point (`create github`) | DONE — spec omitted this row entirely; added during implementation |
