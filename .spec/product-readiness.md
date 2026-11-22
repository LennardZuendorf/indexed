---
type: product-topic
parent: product.md
scope: product
covers: milestone requirements, acceptance evidence, readiness
updated: 2026-11-22
---

# Indexed readiness requirements

[Product spec](product.md) · [Technical contracts](tech-readiness.md) · [Delivery sequence](plan.md#feature-sequence) · [GitHub roadmap](https://github.com/LennardZuendorf/indexed/issues/221)

These are target requirements for a developer or agent using Indexed across projects. [Alpha v0.0.11](https://github.com/LennardZuendorf/indexed/releases/tag/v0.0.11) is the published baseline. Each milestone needs an observed acceptance run from a packaged build. The [plan](plan.md#readiness-milestones) records what the baseline already delivers.

## End-to-end workflow

A developer opens one of two clones of a project. Both select the same shared collections: project GitHub issues, a local Markdown wiki, source code and Git history. They ask why a client retries an operation. Search returns the implementation, the wiki's retry policy and the issue that explains the decision. The developer opens the code at the cited revision, walks to the containing function, follows its callers and finds the commit that changed the policy. An agent in the same project can perform that workflow and cite the same evidence. An unrelated workspace sharing the server sees its own selection.

Use this workflow across the milestones. Add separate cases for exact symbol names, documentation-only questions, partial source failure, and a question the available evidence cannot answer.

## Shared Project Workspace

[Milestone 11](https://github.com/LennardZuendorf/indexed/milestone/11) · [Parent #229](https://github.com/LennardZuendorf/indexed/issues/229)

A developer can index a collection once, select it from several repositories and understand which collections a query will use.

| Requirement | Observable behavior |
| --- | --- |
| Shared storage | Multiple projects can reference one collection. Selecting it or moving a checkout leaves the existing index data reusable. |
| Repository selection | Indexed writes a versioned `indexed.config.toml` at the Git worktree root. The file selects collections by stable ID. The developer can inspect the resolved project and selection. Engine settings and credentials use their existing configuration. |
| Request isolation | CLI, MCP and LSP resolve the same project selection. Concurrent MCP requests from separate projects each use their own selection, even if a collection update runs at the same time. A present but malformed definition or an unresolved collection reference produces an actionable result without widening scope. |
| Existing data | A developer explicitly previews and starts migration of local collections. Indexed copies and verifies the data before registration and preserves the original for rollback. Conflicts and interruptions have explicit recovery paths. |
| Checkout differences | A shared local Files or Git collection preserves the indexed snapshot. Use Git provenance when available. A different checkout exposes a mismatch when opening evidence. Remote connectors keep their existing source identity and freshness behavior. |

**Acceptance.** Use two clones or worktrees at different revisions, a second project with an overlapping selection, and two concurrent MCP clients. Prove reuse of the same collection data, distinct scopes, and correct behavior for missing or renamed collections. Exercise an existing v1 and v2 local collection through migration and rollback. Verify that an interrupted or repeated migration preserves the original data until the verified outcome is known.

The feature design settles how CLI, MCP and LSP supply the workspace, how requests behave without a profile, and how to present migration and rollback.

## Merged Project Search

[Milestone 12](https://github.com/LennardZuendorf/indexed/milestone/12) · [Parent #340](https://github.com/LennardZuendorf/indexed/issues/340)

A developer can ask one question across GitHub issues, a local Markdown wiki and code. Results explain where the evidence came from and remain useful for both exact identifiers and broader questions.

| Requirement | Observable behavior |
| --- | --- |
| Unified ranking | One scoped result list can combine relevant records from all three source types. Query and result controls have equivalent meaning through CLI and MCP. Equivalent duplicates do not crowd out relevant hits, and the result preserves independently attributable source references. |
| Verifiable results | Each hit identifies its source and provides the best supported location for citation. A selected hit can expand to bounded nearby evidence while preserving the distinction between the match and added context. |
| Honest outcomes | A healthy zero-match search, partial source failure and total failure produce distinguishable outcomes. GitHub discussion omissions caused by connector limits are visible. A stale expansion reference reports staleness or a missing target. |
| Measured ranking | Compare dense, dense with reranking, hybrid and hybrid with reranking against the strongest existing baseline. Choose the default using the agreed results and document its tradeoffs. |

**Acceptance.** Recover the issue, policy page and implementation in the shared workflow, and prove CLI/MCP parity for search and expansion. Test a failed source alongside healthy sources and a query with no matching evidence. Freeze held-out judgments and quality/latency gates before comparison. Publish per-source and combined ranking quality, exact-identifier and semantic results, distractors on unanswerable queries, latency and the winning configuration.

Ranking budgets, fusion policy and the public expansion surface belong to the feature design.

## Git and Development Sources

[Milestone 13](https://github.com/LennardZuendorf/indexed/milestone/13) · [Parent #342](https://github.com/LennardZuendorf/indexed/issues/342)

A developer can search Git history as evidence for why code changed and distinguish a historical match from the current source tree.

| Requirement | Observable behavior |
| --- | --- |
| Current and historical evidence | Search current checkouts, commit messages and authors, changed paths and bounded diff evidence. Each historical result identifies the originating repository and commit. |
| Change scope | Limit search to a ref range or a PR's changes. An unresolved ref or unavailable comparison range has an explicit outcome. |
| Source lifecycle | Index a local checkout or remote Git repository. Report what changed, which revisions were indexed, and whether updates succeeded. Surface shallow history and collection limits as partial coverage. |
| Revision navigation | Opening a result reaches the cited revision, or reports why that revision is unavailable. Renames and deleted paths retain their historical context. |

**Acceptance.** Find why a file changed and open the cited commit and changed range from both a checkout and a remote Git source. Cover a branch switch, shallow or detached history, a rewritten ref, a rename, a deletion and an unavailable remote. Demonstrate that results and freshness describe the actual indexed snapshot after each case.

The Git source design settles commit selection, initial history and diff bounds, and remote refresh policy. Historical repository snapshots are tracked separately in [#147](https://github.com/LennardZuendorf/indexed/issues/147).

## Code Graph and Language Server

[Milestone 14](https://github.com/LennardZuendorf/indexed/milestone/14) · [Parent #341](https://github.com/LennardZuendorf/indexed/issues/341)

A developer can move from search evidence to code structure, language-aware relationships and the development records that explain the result.

| Requirement | Observable behavior |
| --- | --- |
| Search to tree | Open a hit at its source location and inspect its enclosing scope and child syntax or symbols. Carry repository, revision and location across CLI, MCP and the editor. |
| Typed graph | Follow available definitions, references, imports and calls. Each edge identifies its type, source and whether it came from syntax or semantic resolution. Traversal reports its limits and any unavailable continuation. |
| Linked evidence | Follow attributable links among code, commits, PRs and issues. Edits, renames, deletions and revision mismatches have visible outcomes. |
| Editor workflow | Publish a language and capability matrix covering symbols, hover, definitions, references, implementations, type and call navigation, diagnostics, completion, signatures, rename, formatting and code actions. Validate the required editor workflows in the initial supported languages. Record each capability as verified, partial or unsupported. Document and test delegated capabilities, and retain unverified items as readiness gaps. |

**Acceptance.** Start with the search hit in an editor, find the enclosing function, follow a semantically resolved caller and cite the associated commit or issue. Repeat traversal through CLI and MCP. Include same-named symbols in different scopes, a cycle, cancellation, a stale range, unsaved editor changes, Unicode positions and an unsupported edge. Test advertised editor capabilities, including editing operations where declared, against the same language support matrix.

The feature design chooses the initial supported languages and the semantic providers. The milestone owns a tested capability matrix and distinguishes semantic resolution from approximate search navigation.

## Agent Plugin Installation

[Milestone 15](https://github.com/LennardZuendorf/indexed/milestone/15) · [Parent #222](https://github.com/LennardZuendorf/indexed/issues/222)

A developer can add Indexed to an agent through a versioned installer and see what the installed integration can do.

| Requirement | Observable behavior |
| --- | --- |
| Six clients | Claude Code, Codex, OpenCode, Droid, Hermes Agent and OpenClaw each have a tested adapter, a supported-version record and matching setup instructions. |
| MCP, skills and hooks | Each adapter registers MCP, makes the Indexed skill discoverable and executes a host hook or an equivalent tested lifecycle adapter. Each client can search the selected repository and explore a result. |
| Safe lifecycle | A clean install, repeat install, upgrade and uninstall preserve unrelated user configuration. A partial failure has a documented retry or recovery outcome. |
| Coverage | Record native support, equivalent adapter behavior and remaining gaps per client. A missing capability keeps that matrix entry open. |

**Acceptance.** In a clean profile for each client, install, discover MCP and the skill, observe hook execution, search scoped evidence, and follow a result. Repeat installation, upgrade and remove the adapter with existing unrelated config present. Retain the host, host version, artifact and results for each action.

Agent lifecycle hooks are owned here. Git-triggered refresh remains under [#67](https://github.com/LennardZuendorf/indexed/issues/67).

## Documentation and Readiness

[Milestone 16](https://github.com/LennardZuendorf/indexed/milestone/16) · [Parent #343](https://github.com/LennardZuendorf/indexed/issues/343)

A developer can understand the product from the README or site and complete the advertised project-evidence workflow using the published package.

| Requirement | Observable behavior |
| --- | --- |
| Clear positioning | Lead with the task Indexed helps complete. Explain collections, repo selection and evidence through concrete examples. README, site and CLI help use consistent names and commands. |
| Versioned claims | Published docs identify the tested package, Python range, client/language support, source limitations, and what model files must be prepared before offline use. |
| Complete onboarding | The docs cover installation, scoping, indexing sources, searching, graph exploration and citations. Migration and troubleshooting guides cover observable failures and recovery. |
| Demonstrated value | Repeat representative developer-agent tasks with and without Indexed. Publish the artifact, fixture or revision, scoring criteria, observed citation quality, failures and effort. |

**Acceptance.** A new user follows published examples in a clean environment from the wheel to the end-to-end workflow. Independently replay the before/after agent tasks for implementation, rationale, exact-identifier lookup, changed-source evidence and an unanswerable request. Verify all commands, links and support claims against the selected release evidence. Report first-run model download separately from warmed setup and search timing.
