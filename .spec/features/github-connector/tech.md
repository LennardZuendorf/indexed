---
type: feature-tech
feature: github-connector
sibling: product.md
parent: ../../tech.md
updated: 2026-09-07
---

# Feature: GitHub Projects & Issues Connector — Architecture

A single `GitHubConnector` covering all three deployment models — public
`github.com`, Enterprise Cloud with data residency (`SUBDOMAIN.ghe.com`), and
self-hosted Enterprise Server — which differ only in how the GraphQL endpoint is
derived from the configured `host`. Follows the **Outline** template: an async `httpx`
reader against the **GraphQL v4** API, a converter that delegates chunking to the
shared `ParsingModule`, a Pydantic `GitHubConfig` with secret getters, and
`config_spec()` / `from_config()`. It registers under type `"github"` and
namespace `"sources.github"` in the two generic connector registries; there is no
per-connector branch anywhere in core — `since`-based incremental fetch and
endpoint/host carry-forward both live entirely inside `GitHubConnector.from_manifest`.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)
**Connectors spec:** [../../tech-connectors.md](../../tech-connectors.md) · **Parsing:** [../../tech-parsing.md](../../tech-parsing.md)

---

## Files

```
src/indexed/connectors/github/
  __init__.py                       # exports GitHubConnector
  connector.py                      # GitHubConnector: reader+converter, config_spec/from_config/from_manifest
  schema.py                         # GitHubConfig (+ get_token, resolve_graphql_url, repo/project parsing)
  auth.py                           # resolve_token(): explicit/env -> `gh auth token` -> error; GITHUB_CLOUD_HOST
  github_graphql_reader.py          # async httpx GraphQL reader (issues/PRs/project), pagination + rate limit + dedup
  github_document_converter.py      # raw item dict -> indexed dict via ParsingModule
  queries.py                        # GraphQL query strings (issues, pull requests, project items, org+user variants)

src/indexed/connectors/registry.py            # github row in CONNECTOR_REGISTRY + NAMESPACE_REGISTRY (+ PATH_KEY_REGISTRY: "host")
src/indexed/protocols/models.py               # SourceConfig.type Literal includes "github"
src/indexed/cli/composition.py                # register_app_config registers GitHubConfig at "sources.github"
src/indexed/cli/knowledge/commands/{_create_schema,_create_commands,_create_options,create}.py  # `create github` subcommand

tests/unit/indexed/connectors/github/         # reader (mocked GraphQL), reader_projects, converter, connector, auth, schema
tests/unit/indexed/knowledge/commands/test_create.py  # TestCreateGithub class (shared file with the other 4 connectors)
```

`collection_service.py` and `update_collection_factory.py` needed **zero**
changes — see § Dynamic creation below for why the original spec's per-connector
branches were never real.

---

## Contract / API

Implements `BaseConnector` (`core/v1/connectors/base.py`): `reader`, `converter`,
`connector_type` (`"github"`), `config_spec()`, `from_config()`, `from_manifest()`.
Reader exposes `get_number_of_documents()` and `read_all_documents() ->
Iterator[dict]`; converter exposes `convert(document: dict) -> list[dict]`.

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
    modified_since: str | None = None                     # internal: set by from_manifest overlay (ISO)

    def get_token(self) -> str: ...                       # delegates to auth.resolve_token(self.token, host=self.host)
    def resolve_graphql_url(self) -> str: ...              # see § Endpoint resolution; graphql_url override wins
    def is_cloud(self) -> bool: ...
    def parsed_repos(self) -> list[tuple[str, str]]: ...
    def parsed_project(self) -> tuple[str, int] | None: ...

# auth.py
GITHUB_CLOUD_HOST = "github.com"   # defined here, not schema.py — schema imports auth, so a
                                    # back-import would be circular; schema re-exports the name.

def resolve_token(explicit: str | None, host: str | None = None) -> str:
    """explicit/GITHUB_TOKEN env -> `gh auth token --hostname <host>` (Enterprise) -> raise ConfigurationError."""
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

Not fetched: `assignees`, `milestone`, PR reviews/review-comment threads — see
product.md R1's amendment and § Deferred below.

---

## Implementation Detail

### Auth resolution (R3)

`resolve_token()` mirrors `ChangeTracker`'s `auto` strategy: prefer the explicit
value (config field, then plain `GITHUB_TOKEN` env var); else shell out to
`gh auth token` (`subprocess.run`, 5s timeout, `text=True`), passing
`--hostname <host>` whenever `host != "github.com"` so an Enterprise
collection's `gh`-CLI fallback resolves that host's token instead of
github.com's; else raise `ConfigurationError` naming both remedies. `gh` is
**optional** — never required, never invoked when an explicit token exists. No
network or `gh` call happens at import time.

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
    if self.host == GITHUB_CLOUD_HOST:
        return "https://api.github.com/graphql"
    if self.host.endswith(".ghe.com"):
        return f"https://api.{self.host}/graphql"
    return f"https://{self.host}/api/graphql"
```

The distinction that makes a single field sufficient: `github.com` and `*.ghe.com`
use an **`api.` host prefix** + `/graphql`, whereas GHES uses the **`/api/graphql`
path** on the same host. Web URLs (`html_url`) come straight from the GraphQL
response, so no per-deployment URL construction is needed. `verify_ssl` is passed
to the `httpx` client for self-signed GHES CAs (same pattern as Outline).
`GitHubConnector.from_manifest` overlays `host`/`graphqlUrl` from the manifest
(alongside the query-shaping fields) so `indexed index update` on a GHES/
`*.ghe.com` collection rebuilds against the same endpoint it was created with,
rather than falling back to the config default.

### GraphQL reader (R1, R2, R4)

Async `httpx.AsyncClient` posting to `config.resolve_graphql_url()`,
Bearer-authenticated. Three query families in `queries.py`:

- **Issues** — `repository(owner,name){ issues(first:$n, after:$cur, filterBy:{since:$since}, states:$states, labels:$labels) { nodes { ...IssueFields comments(first:100){nodes{...}} } pageInfo{hasNextPage endCursor} } }`. One query returns issue + labels + comments; cursor-paginate on `pageInfo`.
- **Pull requests** — analogous `pullRequests(...)` selection when `include_pull_requests`; conversation comments only (not review comments/review threads — see § Deferred).
- **Project v2** — `organization(login:).projectV2(number:) { items(first,after){ nodes { content{ ... on Issue {...} ... on PullRequest {...} ... on DraftIssue {title body} } fieldValues(...) } } }`, with an identical `user(login:)` variant (`PROJECT_ITEMS_QUERY_USER`) tried when the organization probe fails. GitHub answers a user-owned project's `organization(login:)` probe with both `data.organization: null` AND a `NOT_FOUND` GraphQL error on `path=["organization"]`; `_is_organization_not_found()` recognizes that exact shape as "not an org, try the user query" rather than a hard failure — a naive `organization is None` check never reaches this branch because the reader's own error-array check raises first. `fieldValues` maps to `project_fields`. Project items resolve their backing `repository` so they index as repo documents; the reader **dedupes** by `id`, merging `project_fields` from whichever copy has them into the surviving document rather than pure first-wins, so a project item also matched via `repos` is emitted once with its board fields intact (R2 dedupe scenario). `get_number_of_documents()` and `read_all_documents()` both read from one cached, shared crawl (`_deduplicated_documents()`), so counting never re-runs the GraphQL fetch.

Rate limiting: on HTTP 403/429 or a GraphQL `RATE_LIMITED` error, back off using
`utils.retry` and the `X-RateLimit-Reset` hint; concurrency bounded by
`max_concurrent_requests` (same windowed pattern as the Outline reader). A 403
with no rate-limit signal (a real permission/scope error) is not misclassified as
rate-limiting. Heavy imports (`httpx`) are function/property-local, not
module-level.

### Converter via ParsingModule (R7)

Same shape as `UnifiedJiraDocumentConverter`: assemble a Markdown document
(title heading + body + each comment as a section), lazy-import `ParsingModule`,
call `parse_bytes(md.encode("utf-8"), "content.md")`, and map each
`ParsedChunk.contextualized_text` to `{"indexedData": ..., "metadata": {...}}`.
First chunk is the main item header (id/title/state/labels). `project_fields`
and item metadata are attached to chunk metadata. Output is the v1 indexed dict
(`id`, `url`, `modifiedTime`, `text`, `chunks`).

### Dynamic creation (R-cfg)

No `CONFIG_REGISTRY` and no per-connector core branches exist for **any**
connector type (Feature 14 deleted `CONFIG_REGISTRY`; core dispatch was never
per-type to begin with). The real wiring is two dicts plus one registration call:

- `connectors/registry.py`: `CONNECTOR_REGISTRY["github"] = GitHubConnector`,
  `NAMESPACE_REGISTRY["github"] = "sources.github"`, and
  `PATH_KEY_REGISTRY["github"] = "host"` (most connectors write their
  `base_url_or_path` override to a `.url` config key; GitHub writes to `.host`,
  files to `.path` — `PATH_KEY_REGISTRY` generalizes this across all five
  connector types, replacing what used to be three separate hardcoded `"url"`
  sites: `cli/knowledge/commands/create.py:86`, `create.py:210`, and
  `cli/composition.py::build_connector`).
- `cli/composition.py::register_app_config` calls
  `config_service.register(GitHubConfig, path="sources.github")` — the actual
  `ConfigService.register()` call site for every source's schema, run once at
  app startup.
- `GitHubConnector.from_config(config_service)` binds and constructs; `cli/
  composition.py::build_connector` resolves the connector class generically via
  `CONNECTOR_REGISTRY[cfg.type]` — there is no `if cfg.type == "github"` branch
  anywhere in `composition.py`, `collection_service.py`, or
  `update_collection_factory.py`.

CLI reachability: `indexed index create github --repo octo/hello --project
octo/12 --host github.example.com` is a dedicated Typer subcommand
(`cli/knowledge/commands/_create_commands.py`), driven by a `SourceSpec` entry
in `_create_schema.py` — the CLI has no generic `--source <type>` flag; each
connector gets its own subcommand, matching `create files`/`jira`/`confluence`/
`outline` exactly.

<!-- merge -->
### Incremental update (R6 — `since` cutoff shipped; chunk-hash reuse descoped)

**Shipped: server-side `since` cutoff.** `GitHubConnector.from_manifest` reads
`manifest.last_modified_document_time`, subtracts a 60-second safety buffer, and
sets it as an in-memory `modified_since` config overlay (mirroring Outline's
overlay pattern — no `os.environ` side-channel). It also overlays every other
reader-shaping field stored on the manifest (`repos`, `project`, `host`,
`graphqlUrl`, `state`, `labels`, `includePullRequests`, `includeComments`,
`pageSize`, `maxConcurrentRequests`, `verifySsl`) so an update rebuilds an
identical reader to the one that created the collection. The reader injects
`since` into the issues query's `filterBy:{since}`; only items updated at/after
the cutoff are fetched. Deletions are implicit (unmatched items are simply not
re-fetched), consistent with other network connectors.

**Descoped: chunk-hash reuse.** `documents_collection_creator` currently removes
*all* chunks of a re-read document and re-embeds them on UPDATE — true for
every connector, not GitHub-specific. Reusing FAISS vectors for chunks whose
content hash is unchanged would need a new on-disk field
(`index_document_mapping.json` doesn't persist a chunk hash today), a migration
story for every existing collection across all connector types, and has no
Core v2 equivalent (v2 only has document-level hash-skip). Research during
implementation confirmed this is a cross-cutting engine change, not part of
"making the GitHub connector work" — moved out of this plan entirely (see
plan.md unit 6 and
[docs/superpowers/plans/2026-09-05-github-connector.md § Out of scope](../../../docs/superpowers/plans/2026-09-05-github-connector.md)).
Needs its own follow-up plan.
<!-- /merge -->

---

## Performance Budget

- CLI startup unaffected (<1s) — no `httpx`/parsing/connector import at module
  load (lazy; `_create_schema.py`'s `GITHUB_CLOUD_HOST` lookup goes through the
  same lazy `_load()` helper every other connector's cloud-URL default uses,
  not a top-level import).
- A 1k-issue repo indexes within the existing connector envelope; GraphQL batching
  keeps it to ~`ceil(issues/100)` primary requests plus comment pagination only for
  issues exceeding 100 comments.

---

## Deferred

- **Chunk-hash reuse** (R6's second half) — see § Incremental update above and
  plan.md unit 6. Cross-cutting, needs its own plan.
- **`assignees`/`milestone` on issues; PR review/review-thread comments** — R1's
  original requirement text promised these; the shipped GraphQL queries never
  request them (only title/body/author/state/labels/timestamps/URL/conversation
  comments). Deliberate v1 gap, not a bug — product.md R1 has been amended to
  match what's shipped, with this noted as a known follow-up. Adding them is a
  `queries.py` field-selection change plus converter/test updates, not a
  redesign.
- **`comments(first:100)` fetched unconditionally**, even when
  `include_comments=False`, with no truncation detection past 100 comments (an
  issue/PR with a 101st comment silently loses it). Flagged during the final
  whole-branch review (finding I3) and explicitly parked as a follow-up — needs
  a real query variant (skip the `comments` selection entirely) plus a
  `hasNextPage`-aware truncation warning, scoped better as focused iteration
  than a bundled fix.
- **Endpoint derivation** — the three-way `host` rule (§ Endpoint resolution) is
  covered by unit tests; verify once against a live GHES and a `ghe.com` tenant,
  since none exist in CI.
- **GitHub App auth** — see product.md § Open Questions; token + `gh` CLI covers
  the local-first use case for now.
