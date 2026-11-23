---
type: hub
updated: 2026-11-23
---

# Readiness

Target requirements for a developer or agent using Indexed across projects. A milestone names a capability; each issue owns one independently testable part; a milestone is complete when its acceptance run passes against a packaged build. A cut takes the milestones whole: a release ships whatever is finished, and a milestone that is only partly met stays open here.

[Alpha v0.0.11](https://github.com/LennardZuendorf/indexed/releases/tag/v0.0.11) is the published baseline. Issue-level scope and evidence live in the [GitHub roadmap](https://github.com/LennardZuendorf/indexed/issues/221).

## End-to-end workflow

A developer opens one of two clones of a project. Both select the same shared collections: project GitHub issues, a local Markdown wiki, source code and Git history. They ask why a client retries an operation. Search returns the implementation, the wiki's retry policy and the issue that explains the decision. The developer opens the code at the cited revision, walks to the containing function, follows its callers and finds the commit that changed the policy. An agent in the same project can perform that workflow and cite the same evidence. An unrelated workspace sharing the server sees its own selection.

Use this workflow across the milestones. Add separate cases for exact symbol names, documentation-only questions, partial source failure, and a question the available evidence cannot answer.

## Milestones

| # | Milestone | Deliverable | Acceptance | Status | Starts when |
| ---: | --- | --- | --- | --- | --- |
| 1 | [Shared Project Workspace](m1-shared-project-workspace.md) | Global collections and versioned project selection | Two clones, per-request scope, migration and rollback | IN PROGRESS | — |
| 2 | [Merged Project Search](m2-merged-project-search.md) | Ranked issues, wiki and code evidence | Held-out mixed-source evaluation and CLI/MCP workflow | NOT STARTED | Shared Project Workspace DONE |
| 3 | [Git and Development Sources](m3-git-and-development-sources.md) | Searchable history and ref-scoped evidence | History, rename, ref and source-failure workflows | NOT STARTED | Shared Project Workspace DONE |
| 4 | [Code Graph and Language Server](m4-code-graph-and-language-server.md) | Bounded traversal and verified editor capabilities | Search-to-graph workflow and editor/language capability tests | NOT STARTED | Merged Project Search and Git and Development Sources DONE |
| 5 | [Agent Plugin Installation](m5-agent-plugin-installation.md) | Tested integrations for six clients | Per-client install lifecycle and scoped search | IN PROGRESS | Merged Project Search DONE; began early on the shipped `indexed.search/1` payload |
| 6 | [Documentation and Readiness](m6-documentation-and-readiness.md) | Versioned guides, product copy and packaged workflow proof | Published clean install and attributable agent-task replay | NOT STARTED | All five capability milestones DONE |

The Status column is the GitHub milestone and issue state: how much of that milestone's own acceptance is met on `main`. It is a different axis from [Feature Sequence](../feature-sequence.md), which records whether a shipped feature's live surface is complete, so the two tables are not duplicates — a feature can be `IN REVIEW` there while its milestone is `IN PROGRESS` here.

## Contracts

- [Technical contracts](../../tech/readiness-contracts.md): the cross-milestone contracts for resolved scope, evidence identity, source revisions and release evidence.
