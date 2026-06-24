---
type: feature-tech
feature: github-connector
sibling: product.md
parent: ../../tech.md
updated: 2026-06-24
---

# Feature: GitHub Projects & Issues Connector — Architecture

A single `GitHubConnector` covering all three deployment models — public
`github.com`, Enterprise Cloud with data residency (`SUBDOMAIN.ghe.com`), and
self-hosted Enterprise Server — which differ only in how the GraphQL endpoint is
derived from the configured `host`. Follows the **Outline** template: an async `httpx`
reader against the **GraphQL v4** API, a converter that delegates chunking to the
shared `ParsingModule`, a Pydantic `GitHubConfig` with secret getters, and
`config_spec()` / `from_config()`. It registers in the three connector registries
under type `github` and namespace `sources.github`, and gets a branch in the
update factory for `since`-based incremental fetch plus chunk-hash reuse.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)
**Connectors spec:** [../../tech-connectors.md](../../tech-connectors.md) · **Parsing:** [../../tech-parsing.md](../../tech-parsing.md)

---

## Files

```
packages/indexed-connectors/src/connectors/github/
  __init__.py                       # exports GitHubConnector                       ~10 LOC
  connector.py                      # GitHubConnector: reader+converter, config_spec/from_config  ~140 LOC
  schema.py                         # GitHubConfig (+ get_token, repo/project parsing)  ~150 LOC
  auth.py                           # resolve_token(): config/env → `gh auth token` → error  ~70 LOC
  github_graphql_reader.py          # async httpx GraphQL reader (issues/PRs/project), pagination + rate limit  ~320 LOC
  github_document_converter.py      # raw item dict → indexed dict via ParsingModule  ~180 LOC
  queries.py                        # GraphQL query strings (issues, pull requests, project items)  ~120 LOC

packages/indexed-connectors/src/connectors/registry.py   # add github → GitHubConnector / GitHubConfig / sources.github
packages/indexed-core/src/core/v1/engine/services/collection_service.py  # add "github" dispatch in _build_connector_from_config
packages/indexed-core/src/core/v1/engine/factories/update_collection_factory.py  # add github branch: since cutoff
packages/indexed-core/src/core/v1/engine/core/documents_collection_creator.py    # chunk-hash reuse on UPDATE (cross-connector)

tests/unit/indexed_connectors/github/                    # reader (mocked GraphQL), converter, auth, schema
```

---

## Contract / API

Implements `BaseConnector` (`core/v1/connectors/base.py`): `reader`, `converter`,
`connector_type` (`"github"`), `config_spec()`, `from_config()`. Reader exposes
`get_number_of_documents()` and `read_all_documents() -> Iterator[dict]`;
converter exposes `convert(document: dict) -> list[dict]`.

```python
# schema.py
class GitHubConfig(BaseModel):
    repos: list[str] = Field(default_factory=list)        # ["owner/repo", ...]
    project: str | None = None                            # "owner/number" (org or user project v2)
    host: str = "github.com"                              # "github.com" | "SUB.ghe.com" | GHES hostname
    graphql_url: str | None = None                        # explicit override; else derived from host
    verify_ssl: bool = True                               # set False for GHES self-signed CAs
    token: str | None = None                              # env: INDEXED__sources__github__token / GITHUB_TOKEN
    state: Literal["open", "closed", "all"] = "all"
    labels: list[str] | None = None
    include_pull_requests: bool = False
    include_comments: bool = True
    max_chunk_tokens: int = 512
    page_size: int = 100                                  # GraphQL max
    max_concurrent_requests: int = 5
    modified_since: str | None = None                     # internal: set by update factory (ISO)

    def get_token(self) -> str: ...                       # delegates to auth.resolve_token(self.token)
    def resolve_graphql_url(self) -> str: ...             # see § Endpoint resolution; graphql_url override wins

# auth.py
def resolve_token(explicit: str | None) -> str:
    """explicit/env → `gh auth token` (subprocess) → raise ConfigurationError."""
```

**Reader raw-document shape** (one per issue / PR / draft item), consumed by the
converter:

```python
{
  "id": "octo/api#123",            # stable document id (repo#number, or "project:<id>" for drafts)
  "url": "https://github.com/octo/api/issues/123",
  "modifiedTime": "2026-06-20T10:00:00Z",   # issue.updatedAt — drives `since`
  "title": "...", "body": "...", "state": "OPEN",
  "labels": ["bug"], "author": "octo", "kind": "issue",   # issue | pull_request | draft
  "comments": [{"author": "...", "body": "..."}, ...],
  "project_fields": {"Status": "In Progress", "Priority": "P1"},  # when from a project
}
```

---

## Implementation Detail

### Auth resolution (R3)

`resolve_token()` mirrors `ChangeTracker`'s `auto` strategy: prefer the explicit
value (config field, then `GITHUB_TOKEN`/`INDEXED__sources__github__token` via the
config chain); else shell out to `gh auth token` (`subprocess.run`, short timeout,
`text=True`), using its stdout if exit 0; else raise `ConfigurationError` naming
both remedies. `gh` is **optional** — never required, never invoked when an
explicit token exists. No network or `gh` call happens at import time.

### Endpoint resolution (R-deploy)

`resolve_graphql_url()` derives the GraphQL endpoint from `host`, so the user
configures only the host they see in the browser. An explicit `graphql_url`
always wins (escape hatch). The host normalizes by stripping any scheme/path.

| `host` | Detected as | GraphQL endpoint |
|---|---|---|
| `github.com` (default) | Public Cloud | `https://api.github.com/graphql` |
| `octocorp.ghe.com` (ends `.ghe.com`) | Enterprise Cloud, data residency | `https://api.octocorp.ghe.com/graphql` |
| `github.example.com` (anything else) | Enterprise Server (GHES) | `https://github.example.com/api/graphql` |

```python
def resolve_graphql_url(self) -> str:
    if self.graphql_url:
        return self.graphql_url
    h = self.host.removeprefix("https://").removeprefix("http://").strip("/")
    if h == "github.com":
        return "https://api.github.com/graphql"
    if h.endswith(".ghe.com"):                 # data residency: api.<sub>.ghe.com
        return f"https://api.{h}/graphql"
    return f"https://{h}/api/graphql"          # GHES: path-based
```

The distinction that makes a single field sufficient: `github.com` and `*.ghe.com`
use an **`api.` host prefix** + `/graphql`, whereas GHES uses the **`/api/graphql`
path** on the same host. Web URLs (`html_url`) come straight from the GraphQL
response, so no per-deployment URL construction is needed. `verify_ssl` is passed
to the `httpx` client for self-signed GHES CAs (same pattern as Outline).

### GraphQL reader (R1, R2, R4)

Async `httpx.AsyncClient` posting to `config.resolve_graphql_url()`,
Bearer-authenticated. Three query families in `queries.py`:

- **Issues** — `repository(owner,name){ issues(first:$n, after:$cur, filterBy:{since:$since, labels:$labels, states:$states}) { nodes { ...IssueFields comments(first:100){nodes{...}} } pageInfo{hasNextPage endCursor} } }`. One query returns issue + labels + comments; cursor-paginate on `pageInfo`.
- **Pull requests** — analogous `pullRequests(...)` selection when `include_pull_requests`.
- **Project v2** — `node(id) / organization.projectV2 / user.projectV2 { items(first,after){ nodes { content{ ... on Issue {...} ... on PullRequest {...} ... on DraftIssue {title body} } fieldValues(...) } } }`; map `fieldValues` → `project_fields`. Project items resolve their backing `repository` so they index as repo documents; the reader **dedupes** by `id` so a project item also matched via `repos` is emitted once (R2 dedupe scenario).

Rate limiting: on HTTP 403/429 or a GraphQL `RATE_LIMITED` error, back off using
`utils.retry` and the `X-RateLimit-Reset` hint; concurrency bounded by
`max_concurrent_requests` (same windowed pattern as the Outline reader). Heavy
imports (`httpx`) are function/property-local, not module-level.

### Converter via ParsingModule (R7)

Same shape as `UnifiedJiraDocumentConverter`: assemble a Markdown document
(title heading + body + each comment as a section), lazy-import `ParsingModule`,
call `parse_bytes(md.encode("utf-8"), "content.md")`, and map each
`ParsedChunk.contextualized_text` to `{"indexedData": ..., "metadata": {...}}`.
First chunk is the main item header (id/title/state/labels). `project_fields`
and item metadata are attached to chunk metadata. Output is the v1 indexed dict
(`id`, `url`, `modifiedTime`, `text`, `chunks`).

### Dynamic creation (R-config)

- `registry.py`: add `"github"` to `CONNECTOR_REGISTRY`, `CONFIG_REGISTRY`, and `NAMESPACE_REGISTRY` (`"sources.github"`).
- `collection_service._build_connector_from_config`: add a `"github"` branch calling `GitHubConnector.from_config(config_service)` (which registers `GitHubConfig` at `sources.github`, binds, and constructs).

<!-- merge -->
### Smart incremental update (R6)

Two layers, generalizing the existing update machinery:

1. **Server-side `since`** — the update factory (`update_collection_factory.py`)
   reads `manifest.lastModifiedDocumentTime`, subtracts a small safety buffer, and
   passes it to the reader as `modified_since` (transient, like Outline's env
   handoff). The reader injects it into GraphQL `filterBy:{since}` so only items
   updated at/after the cutoff are fetched. Deletions are implicit (unmatched items
   are simply not re-fetched), consistent with other network connectors.

2. **Chunk-hash reuse** — on UPDATE, `documents_collection_creator` currently
   removes *all* chunks of a re-read document and re-embeds them. This feature adds
   content-hash reuse: for a re-read document, compare each new chunk's
   `ParsedChunk.content_hash` (xxhash, already computed in parsing) against the
   previously persisted chunk hashes; reuse existing FAISS vectors for unchanged
   chunks and embed only changed/new ones. This closes the known
   "chunks always re-embedded" gap and benefits every connector, not just GitHub.
<!-- /merge -->

---

## Performance Budget

- CLI startup unaffected (<1s) — no `httpx`/parsing import at module load (lazy).
- A 1k-issue repo indexes within the existing connector envelope; GraphQL batching
  keeps it to ~`ceil(issues/100)` primary requests plus comment pagination only for
  issues exceeding 100 comments.

---

## Open Questions

1. **Chunk-hash reuse location** — implement generically in
   `documents_collection_creator` (benefits all connectors, larger blast radius) vs.
   GitHub-only first. Recommendation: generic, since the persisted index already
   keys chunks by document and the hash is free from parsing — but gate it behind
   thorough update tests before promoting to root tech.
2. **Endpoint derivation** — the three-way `host` rule (§ Endpoint resolution) is
   covered by unit tests; verify once against a live GHES and a `ghe.com` tenant
   during impl, since we have no such instances in CI.
