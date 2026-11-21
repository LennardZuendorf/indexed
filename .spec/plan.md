---
type: entrypoint
scope: implementation
covers: readiness milestones, feature sequence, acceptance and current focus
children: []
updated: 2026-11-21
---

# Development Plan for Indexed

[Product spec](product.md) · [Readiness requirements](product-readiness.md) · [Technical contracts](tech-readiness.md) · [GitHub delivery tracker](https://github.com/LennardZuendorf/indexed/issues/221)

## Current Status

[Indexed Alpha v0.0.11](https://github.com/LennardZuendorf/indexed/releases/tag/v0.0.11) is published on GitHub and [PyPI](https://pypi.org/project/indexed-sh/0.0.11/). It includes cross-collection semantic search, shared CLI and MCP search output, Git provenance and freshness, local watching, editor navigation and a Claude Code installer. The package supports Python 3.11.5 through 3.14. This release is the baseline for the readiness milestones.

## Readiness Milestones

A milestone names a capability a developer or agent can use. Each issue owns one independently testable part. A milestone is complete when its acceptance check passes against a packaged build. GitHub holds issue-level scope and evidence.

### 1. Shared Project Workspace

[GitHub milestone](https://github.com/LennardZuendorf/indexed/milestone/11) · [Parent issue #229](https://github.com/LennardZuendorf/indexed/issues/229) · [Requirements and acceptance](product-readiness.md#shared-project-workspace)

- **Scope.** A global store for reusable collections and a versioned, committable repo definition that selects which collections CLI, MCP and LSP search. MCP resolves project scope for each request. Credentials live outside the repo definition.
- **Available in v0.0.11.** Global and per-project storage modes, explicit collection selection, and shared CLI/MCP storage resolution.
- **Complete when.** Two clones or worktrees and a second repository can select one underlying collection. Concurrent clients receive the correct scoped results. Invalid or missing selections fail explicitly. Migration and rollback preserve existing local data.
- **Issue.** [#229 Shared collections and workspace profile](https://github.com/LennardZuendorf/indexed/issues/229).

### 2. Merged Project Search

[GitHub milestone](https://github.com/LennardZuendorf/indexed/milestone/12) · [Parent issue #340](https://github.com/LennardZuendorf/indexed/issues/340) · [Requirements and acceptance](product-readiness.md#merged-project-search)

- **Scope.** One ranked search over GitHub issues, a local Markdown wiki and current source code. Compare lexical and semantic retrieval, candidate fusion and reranking. Give results stable source references, bounded detail and explicit per-source errors.
- **Available in v0.0.11.** All three sources, cross-collection semantic search, separate v2 reranking, a small pinned evaluation corpus, and the shared `indexed.search/1` payload.
- **Complete when.** One CLI or MCP search can cite evidence from all three sources. Compare dense, dense with reranking, hybrid and hybrid with reranking on held-out queries. Publish quality by source and query type, latency and distractor rates for unanswerable queries. Set quality and latency criteria before comparing with the strongest existing baseline. Choose the default from those results. Check search-to-expansion parity, source inspection and partial failures.
- **Issues.** [#204 Evaluation](https://github.com/LennardZuendorf/indexed/issues/204) · [#205 Hybrid search](https://github.com/LennardZuendorf/indexed/issues/205) · [#219 Expansion](https://github.com/LennardZuendorf/indexed/issues/219) · [#108 Inspect](https://github.com/LennardZuendorf/indexed/issues/108) · [#109 Search output](https://github.com/LennardZuendorf/indexed/issues/109) · [#125 Error integrity](https://github.com/LennardZuendorf/indexed/issues/125) · [#356 GitHub discussion coverage](https://github.com/LennardZuendorf/indexed/issues/356).

### 3. Git and Development Sources

[GitHub milestone](https://github.com/LennardZuendorf/indexed/milestone/13) · [Parent issue #342](https://github.com/LennardZuendorf/indexed/issues/342) · [Requirements and acceptance](product-readiness.md#git-and-development-sources)

- **Scope.** Search current Git checkouts, commit history and bounded diff evidence. Support ref- and PR-scoped search. Use remote Git repositories as the next additional development source.
- **Available in v0.0.11.** Local file indexing, Git-aware updates, changed-since filtering, provenance, line blame, freshness and optional Git-signal ranking.
- **Complete when.** A developer can find why a file changed, retrieve a specific commit or diff, and open the correct revision or current file. Run the same workflow against a remote Git source. Verify shallow and detached checkouts, ref switches, history rewrites, renames, deletions and source failures. Results distinguish historical evidence from current code.
- **Issues.** [#60 Git and code awareness](https://github.com/LennardZuendorf/indexed/issues/60) · [#92 Remote Git](https://github.com/LennardZuendorf/indexed/issues/92) · [#145 Ref and PR scope](https://github.com/LennardZuendorf/indexed/issues/145) · [#146 Freshness](https://github.com/LennardZuendorf/indexed/issues/146). [#355 Git history ingestion](https://github.com/LennardZuendorf/indexed/issues/355) owns searchable commit and diff evidence.

### 4. Code Graph and Language Server

[GitHub milestone](https://github.com/LennardZuendorf/indexed/milestone/14) · [Parent issue #341](https://github.com/LennardZuendorf/indexed/issues/341) · [Requirements and acceptance](product-readiness.md#code-graph-and-language-server)

- **Scope.** A full editor workflow for supported languages and a typed graph that CLI, MCP and LSP can traverse from a search hit. Open the hit at its source range, walk parent and child syntax or symbol scopes, and follow definition, reference, import and call relationships. Link code, commits, PRs and issues through attributable edges.
- **Available in v0.0.11.** Syntax-aware chunks and source locations, workspace symbols, hover, search-based definitions and references, and informational index diagnostics.
- **Complete when.** A real editor session navigates from a search result to related code and cited evidence. The same graph references work through CLI and MCP with explicit response and traversal limits. A supported-language matrix covers document and workspace symbols, hover, definitions, references, implementations, type and call navigation, diagnostics, completion and signatures, rename, formatting and code actions. Test actual language-aware resolution and use existing language servers where applicable. Verify graph updates after edits, renames and deletion.
- **Issues.** [#241 LSP capabilities](https://github.com/LennardZuendorf/indexed/issues/241) · [#148 Linked evidence](https://github.com/LennardZuendorf/indexed/issues/148). [#353 Code graph traversal](https://github.com/LennardZuendorf/indexed/issues/353) owns semantic code relationships and search-to-tree exploration.

### 5. Agent Plugin Installation

[GitHub milestone](https://github.com/LennardZuendorf/indexed/milestone/15) · [Parent issue #222](https://github.com/LennardZuendorf/indexed/issues/222) · [Requirements and acceptance](product-readiness.md#agent-plugin-installation)

- **Scope.** Versioned adapters for Claude Code, Codex, OpenCode, Droid, Hermes Agent and OpenClaw. Install MCP, skills and agent hooks with a documented lifecycle per client.
- **Available in v0.0.11.** `indexed install claude-code` registers MCP and installs the `index-use` skill. Other clients can connect through their own MCP configuration.
- **Complete when.** Each client passes clean-environment install, registration, skill discovery, hook execution, scoped search, exploration, upgrade and uninstall. Repeated install preserves unrelated configuration. Verify client version and hook support against actual installations. If native hooks are unavailable, test an equivalent adapter. A documented gap keeps that client capability open.
- **Issues.** [#222 Agent plugins](https://github.com/LennardZuendorf/indexed/issues/222) · [#67 File watching and Git hooks](https://github.com/LennardZuendorf/indexed/issues/67). Agent hooks belong to #222. Git-triggered refresh belongs to #67.

### 6. Documentation and Readiness

[GitHub milestone](https://github.com/LennardZuendorf/indexed/milestone/16) · [Parent issue #343](https://github.com/LennardZuendorf/indexed/issues/343) · [Requirements and acceptance](product-readiness.md#documentation-and-readiness)

- **Scope.** Clear product copy and consistent README, site, CLI help and guides. Explain installation, scopes, supported clients and languages, sources, search-to-citation, offline model preparation, migration and troubleshooting.
- **Available in v0.0.11.** Quick Start, search result reference, editor and Claude Code guides, release notes and an evaluation runbook. The live Quick Start still advertises an unbounded Python minimum.
- **Complete when.** A new user follows the published docs from a clean install to a scoped multi-source query, graph traversal and cited answer. Verify the examples against that package and the language and client matrices. Compare the same representative agent tasks with and without Indexed and publish the evidence and limitations.
- **Issues.** [#218 Public docs and product copy](https://github.com/LennardZuendorf/indexed/issues/218) · [#174 CLI onboarding](https://github.com/LennardZuendorf/indexed/issues/174) · [#220 Installed workflow and task trial](https://github.com/LennardZuendorf/indexed/issues/220) · [#336 Python support](https://github.com/LennardZuendorf/indexed/issues/336).

## Feature Sequence

| Order | Feature | Deliverable | Test | Status | Starts when |
| ---: | --- | --- | --- | --- | --- |
| 1 | Shared Project Workspace | Global collections and versioned project selection | Two clones, per-request scope, migration and rollback | NOT STARTED | — |
| 2 | Merged Project Search | Ranked issues, wiki and code evidence | Held-out mixed-source evaluation and CLI/MCP workflow | NOT STARTED | Shared Project Workspace DONE |
| 3 | Git and Development Sources | Searchable history and ref-scoped evidence | History, rename, ref and source-failure workflows | NOT STARTED | Shared Project Workspace DONE |
| 4 | Code Graph and Language Server | Bounded traversal and verified editor capabilities | Search-to-graph workflow and editor/language capability tests | NOT STARTED | Merged Project Search and Git and Development Sources DONE |
| 5 | Agent Plugin Installation | Tested integrations for six clients | Per-client install lifecycle and scoped search | NOT STARTED | Merged Project Search DONE |
| 6 | Documentation and Readiness | Versioned guides, product copy and packaged workflow proof | Published clean install and attributable agent-task replay | NOT STARTED | All five capability milestones DONE |

The status column tracks each milestone's new acceptance scope. Existing pieces are listed above. Host capability discovery and public docs corrections can proceed while dependencies are open.

### Delivered baseline

| Feature | State | Evidence |
| --- | --- | --- |
| Core indexing, connectors and v1/v2 coexistence | DONE | [Facade](../src/indexed/core/engine.py), [v2 and migration](../src/indexed/core/v2/), [connectors](../src/indexed/connectors/registry.py) |
| github-connector | PUBLISHED, SPEC WRAP-UP OPEN | [GitHub connector](../src/indexed/connectors/github/), [#200](https://github.com/LennardZuendorf/indexed/pull/200) |
| retrieval-eval | PUBLISHED, SPEC WRAP-UP OPEN | [Harness and evidence](../eval/README.md), [#297](https://github.com/LennardZuendorf/indexed/pull/297) |
| lsp-tier0 | PUBLISHED, SPEC WRAP-UP OPEN | [Editor server](../src/indexed/lsp/), [#303](https://github.com/LennardZuendorf/indexed/pull/303) |
| lsp-tier1 | PUBLISHED, SPEC WRAP-UP OPEN | [Editor system tests](../tests/system/test_lsp_out_of_process.py), [#303](https://github.com/LennardZuendorf/indexed/pull/303) |
| file-watcher | MERGED, CATCH-UP OPEN | [CLI #278](https://github.com/LennardZuendorf/indexed/pull/278), [MCP #316](https://github.com/LennardZuendorf/indexed/pull/316), [catch-up test](../tests/system/test_mcp_watch_freshness.py) |
| Canonical search, Git provenance and Claude Code installer | DONE | [Search contract](../docs/reference/search-output.md), [Git #293](https://github.com/LennardZuendorf/indexed/pull/293), [installer #317](https://github.com/LennardZuendorf/indexed/pull/317) |

## Current Focus

Start with the Shared Project Workspace contract. Settle profile discovery, collection identity, per-request selection and migration. In parallel, track the [#358 macOS MCP watcher catch-up timeout](https://github.com/LennardZuendorf/indexed/issues/358) and correct the live Python support range for v0.0.11. The [narrow-terminal installer fix #359](https://github.com/LennardZuendorf/indexed/pull/359) is on main after v0.0.11 and closes [#357](https://github.com/LennardZuendorf/indexed/issues/357).

## Versioning Strategy

Tags determine the package version. Alpha can introduce breaking changes. A stable release follows semantic versioning. Milestones track readiness and can span releases. [Release workflow](../.github/workflows/python-release-ci.yml)

## Decision Log

Current routing and storage decisions live in [Architecture](tech.md) and [Configuration](tech-config.md). The previous rollout log is in [Git history](https://github.com/LennardZuendorf/indexed/blob/396e6ec92a69735710bef95831af83fd864da239/.spec/plan.md#decision-log).
