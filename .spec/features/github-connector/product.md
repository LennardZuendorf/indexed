---
type: feature-product
feature: github-connector
sibling: tech.md
parent: ../../product.md
updated: 2026-09-07
---

# Feature: GitHub Projects & Issues Connector — Product

Adds a source connector that indexes GitHub **issues and pull-request threads**
from one or more repositories, and optionally a **GitHub Projects v2 board** as
an aggregating view that pulls items (issues/PRs/draft items) across many repos
and enriches them with project field values (Status, Priority, …). It works
against all three GitHub deployment models — public `github.com`, Enterprise
Cloud **with data residency** (`SUBDOMAIN.ghe.com`), and self-hosted **Enterprise
Server** (GHES) — mirrors the dynamic create/update flow of the
Jira/Confluence/Outline connectors, authenticates through a token resolved from
config, `.env`, or the local GitHub CLI, and delegates all chunking to the
shared parsing module.

Resolves [issue #90](https://github.com/LennardZuendorf/indexed/issues/90).

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | `src/indexed/connectors/github/` (connector, GraphQL reader, converter, schema, auth resolver); rows for `github` in `src/indexed/connectors/registry.py` (`CONNECTOR_REGISTRY`/`NAMESPACE_REGISTRY`/`PATH_KEY_REGISTRY`); config namespace `sources.github`; the `create github` CLI subcommand in `src/indexed/cli/knowledge/commands/`; `.spec/features/github-connector/`; tests under `tests/unit/indexed/connectors/github/`. |
| **Does not own** | Engine/FAISS/persistence (core), the `ParsingModule` itself (parsing), `ConfigService` internals (config), CLI command files beyond wiring the new source type, the Jira/Confluence/Outline connectors. |

---

## Requirements

### Requirement: Index repository issues and pull requests

The system SHALL index GitHub issues — and, when enabled, pull-request threads —
from each configured `owner/repo`, capturing title, body, author, state, labels,
timestamps, URL, and conversation comments as indexable text.

> **Amendment (2026-09-07):** the original requirement text also promised
> `assignees`, `milestone`, and — for pull requests — review/review-comment
> threads. None of those are fetched by the shipped GraphQL queries (only
> title/body/author/state/labels/timestamps/URL/conversation comments; PR
> comments are conversation comments, not review comments). This is a known,
> deliberate v1 gap for a follow-up, not a bug — see tech.md § Deferred.

#### Scenario: Index open and closed issues from a repo

- **Given** a collection configured with `repos = ["octo/hello"]` and `state = "all"`
- **When** the user runs `indexed index create github --repo octo/hello`
- **Then** every open and closed issue in `octo/hello` is indexed as one document with its comments included in the chunked text, and its `url` is searchable as the document URL.

#### Scenario: Pull requests included only when enabled

- **Given** `--no-include-pull-requests` (the default)
- **When** the collection is built
- **Then** only issues are indexed and no pull-request documents appear; passing `--include-pull-requests` adds PR descriptions and conversation comments as documents (not review/review-comment threads — see the amendment above).

### Requirement: Index GitHub Projects v2 boards

The system SHALL, when a `project` selector is configured, resolve the Project v2
board to its items across all referenced repositories, index each item's
underlying issue/PR (or draft item), and attach the project's custom field
values (e.g. Status, Priority, Iteration) to the document metadata.

#### Scenario: Project spanning multiple repos

- **Given** `project = "octo/12"` whose board contains issues from `octo/api` and `octo/web`
- **When** the collection is built
- **Then** issues from both repos are indexed as documents, each carrying its board field values (e.g. `status = "In Progress"`) in metadata, and the same issue is not duplicated if it also matches a configured `repos` entry.

#### Scenario: Draft project items

- **Given** a project containing a draft item (title + body, no backing repo issue)
- **When** the collection is built
- **Then** the draft item is indexed as a standalone document with its title and body text.

### Requirement: Token resolution via config, env, or GitHub CLI

The system SHALL resolve an access token in priority order: explicit config/`.env`
token first; otherwise the token reported by the local GitHub CLI (`gh auth token`);
otherwise it MUST raise a clear error instructing the user to set
`INDEXED__sources__github__token` or run `gh auth login`.

#### Scenario: Falls back to gh CLI

- **Given** no `token` in config or `.env`, and an authenticated `gh` CLI on PATH
- **When** the connector authenticates
- **Then** it uses the token from `gh auth token` without further prompting.

#### Scenario: No credentials anywhere

- **Given** no token in config/`.env` and no usable `gh` CLI
- **When** the connector authenticates
- **Then** it raises an error naming both the env var and the `gh auth login` remedy, and the run aborts before any API call.

### Requirement: Efficient GraphQL fetching with pagination and rate limiting

The system SHALL fetch data through the GitHub GraphQL v4 API, retrieving issues
with their labels and comments in batched cursor-paginated queries, and MUST
respect GraphQL rate-limit signals with retry/backoff rather than failing on the
first throttle.

#### Scenario: Large repo paginates without loss

- **Given** a repo with more issues than one page (100) allows
- **When** the reader fetches issues
- **Then** it follows `pageInfo.endCursor` until exhausted and indexes every matching issue.

### Requirement: Support all GitHub deployment models

The system SHALL index from public `github.com`, GitHub Enterprise Cloud **with
data residency** (`SUBDOMAIN.ghe.com`), and self-hosted **GitHub Enterprise
Server**, selected by a single configured `host`, deriving the correct GraphQL
endpoint for each without the user needing to know API URL conventions.

#### Scenario: Public github.com (default)

- **Given** no `host` is configured (defaults to `github.com`)
- **When** the connector builds requests
- **Then** it targets the public GraphQL endpoint and indexes issues from the configured repos.

#### Scenario: Enterprise Cloud with data residency

- **Given** `host = "octocorp.ghe.com"`
- **When** the connector builds requests
- **Then** it targets the tenant's dedicated GraphQL endpoint (the `api.`-prefixed `ghe.com` host), not `github.com`.

#### Scenario: Self-hosted Enterprise Server

- **Given** `host = "github.example.com"` (a GHES instance)
- **When** the connector builds requests
- **Then** it targets that host's path-based GraphQL endpoint, and TLS verification can be relaxed for self-signed CAs via `verify_ssl = false`.

### Requirement: Filtering by state, labels, and selectors

The system SHALL support filtering indexed content by issue `state`
(`open`/`closed`/`all`), by `labels`, and by source selector (`repos` and/or a
`project`), so a collection indexes only the intended subset.

#### Scenario: Label filter

- **Given** `labels = ["bug"]`
- **When** the collection is built
- **Then** only issues carrying the `bug` label are indexed.

### Requirement: Smart incremental update

The system SHALL update a GitHub collection incrementally by fetching only items
changed since the last run (server-side `since` cutoff derived from the manifest).

> **Amendment (2026-09-07):** the original requirement text also promised
> skipping re-embedding of chunks whose content hash is unchanged
> ("chunk-hash reuse"). That half is **descoped from this feature** — see
> plan.md unit 6 and tech.md § Deferred. It needs a new on-disk schema field
> shared by every connector type (not GitHub-specific) and has no Core v2
> story yet; it is a known, deliberate gap tracked for a follow-up plan, not
> an implemented guarantee. Today, a re-fetched GitHub document has ALL its
> chunks re-embedded, same as every other connector.

#### Scenario: Only changed issues re-fetched

- **Given** an existing GitHub collection updated yesterday and one issue edited since
- **When** the user runs `indexed index update <collection>`
- **Then** only issues updated at/after the cutoff are fetched, and the unchanged issues are left untouched in the index.

#### Scenario: Unchanged chunks not re-embedded (DESCOPED — not implemented)

- **Given** an issue that was re-fetched because a new comment was added
- **When** the document is re-indexed
- **Then** chunks whose content hash matches the previously indexed chunk would be reused, embedding only the new/changed chunks — this scenario describes chunk-hash reuse, which was **not built** in this feature (see amendment above). Today all of the re-fetched document's chunks are re-embedded.

### Requirement: Parse via the shared parsing module

The system SHALL produce chunks by passing assembled issue/PR/project Markdown
through the shared `ParsingModule`, not by reimplementing chunking in the
connector.

#### Scenario: Markdown body chunked by the shared parser

- **Given** an issue whose body is long Markdown
- **When** the converter builds chunks
- **Then** the body is chunked by `ParsingModule.parse_bytes(..., "content.md")` and each resulting chunk's contextualized text becomes an indexed chunk.

---

## User Experience

```toml
# ./.indexed/config.toml
[sources.github]
repos = ["octo/api", "octo/web"]   # repo-scoped issues/PRs
project = "octo/12"                 # optional: aggregate a Projects v2 board
state = "all"                       # open | closed | all
labels = ["bug", "feature"]         # optional label filter
include_pull_requests = true        # include PR threads (default false)
include_comments = true             # include issue/PR comments (default true)
# host = "github.com"               # default; or "octocorp.ghe.com" (data residency) / "github.example.com" (GHES)
# verify_ssl = true                 # set false for GHES with self-signed CAs

# Token (priority: config/.env  →  gh CLI  →  error)
# .env:  INDEXED__sources__github__token=ghp_xxx
```

```bash
indexed index create github --repo octo/api --repo octo/web --project octo/12
indexed index search "flaky retry logic" --collection github
indexed index update github    # incremental: only changed issues, all their chunks re-embedded
```

`create github` is a dedicated Typer subcommand (like `create files`/`jira`/
`confluence`/`outline`) — the CLI has no generic `--source <type>` flag. CLI
flags mirror the config keys above: `--repo` (repeatable), `--project`,
`--host`, `--token`, `--state`, `--label` (repeatable),
`--include-pull-requests`/`--no-include-pull-requests`.

---

## Non-Goals

- Writing to GitHub (creating/closing issues, posting comments) — read-only indexing.
- Classic (v1) Projects — only Projects v2 is supported.
- Indexing repository code, releases, wikis, or discussions (separate sources).
- GitHub App installation auth in v1 (token / `gh` CLI only) — see Open Questions.
- Webhook-driven live sync — update is pull-based like every other connector.

---

## Open Questions

1. **GitHub App auth** — deferred to a follow-up. Token + `gh` CLI covers the
   local-first use case; App auth (installation id + private key) matters mainly
   for org-wide automation and can be added behind the same auth resolver later.
2. **Deleted/transferred issues** — like other network connectors, deletions are
   not actively reconciled (a deleted issue simply stops matching). Acceptable for
   v1; revisit if it proves noisy.
