---
type: tech
updated: 2026-11-23
applies: [src/indexed/**]
---

# Readiness Contracts

[Readiness requirements](../concepts/readiness/README.md) · [Architecture](../tech.md) · [Delivery sequence](../plan.md)

These target contracts constrain designs across the readiness milestones. Existing behavior stays documented in the owning component specs. Feature designs define concrete file schemas, wire formats, defaults, migrations and tests before implementation.

## One resolved scope per operation

- Resolve repository selection and caller overrides at the application boundary using the shared config and composition layers. Carry the resolved scope into the engine operation. A long-lived MCP server must resolve new requests independently, including concurrent requests. A concurrent update can change visible data only within the request's resolved collection scope. A change that invalidates an evidence reference produces a stale outcome.
- Keep collection identity independent of checkout location. Resolve stable collection IDs through the selected store and preserve engine routing by manifest. Treat missing selection, invalid selection, unavailable collection and scoped success as separate cases.
- Indexed owns writes to `indexed.toml` at the Git worktree root. Resolve in one order: the nearest `indexed.toml`, then the deprecated `.indexed/collections.json` pointer, then storage mode. The pointer is a compatibility path to migrate off, never a mechanism a new design builds on. Read the definition into one validated, typed selection DTO before resolving collection IDs. An unsupported version, invalid selection or missing registered collection produces an explicit error, never a wider or narrower scope. Keep engine settings and credentials in their existing configuration.
- Treat promotion of existing local data to the shared store as a journalled move: journal each collection before its data moves, verify the moved bytes against the pre-move fingerprint when content verification is requested, and register only after verification succeeds. Design for collisions, interruption, resumption and rollback. The journal, not a retained copy, is what makes the previous location restorable until the transition completes.

Owning surfaces include [Configuration](config/README.md), [App composition](app/README.md) and the [core facade](../../../src/indexed/core/engine.py).

## Stable evidence and bounded consumers

- The source and collection establish an evidence identity. Carry a source document or commit, the indexed revision or generation when available, and the supported location granularity. Resolve local locations against that identity and detect revision mismatches. A checkout path is a location, independent of stable evidence identity. Shared workspace snapshot and checkout matching apply to local Files and Git collections. Use Git provenance where available and preserve the remote connectors' existing identity and freshness contracts.
- Use the shared machine payload as the compatibility baseline for CLI and MCP. Extend it compatibly or publish an explicit version change with migration guidance. Preserve raw score semantics and partial collection errors through fusion and reranking. Keep ranking evidence separate from outcome reporting.
- Expand and traverse only against the resolved scope and a valid result reference. Bound requested or returned chunks, depth, node and edge counts and response size. Expose truncation and stale, unresolved or out-of-scope references as distinct outcomes. Protect ranges and local paths at the resolution boundary.
- Convert locations at protocol boundaries. An editor range uses its negotiated position encoding and describes the documents and revisions from which it was derived. Feed CLI, MCP and LSP from the same evidence identity.

Baseline [search result contract](../../reference/search-output.md) · [App surfaces](app/README.md) · [Provenance utilities](../../../src/indexed/utils/provenance.py)

## Source revisions and relationships

- Connector output preserves source identity and the selected revision window. Keep current checkout records and historical commit/diff records distinguishable. Persist update state sufficient to identify rename, deletion, source unavailability and rewritten-ref cases.
- Record code relationships and cross-source links with typed provenance. Distinguish syntax nesting from semantically resolved symbol relationships. Explicit references can link issues, PRs, commits and files. Track the indexed generation for edges so a consumer can detect stale results across updates.
- Define bounds and explicit partial coverage for histories, comments and traversal. Test incremental publication with a stale reference and a changed, renamed or deleted source. A successful update must agree with the results of indexing the same final snapshot afresh within the same scope.

Owning surfaces include [Connectors](connectors/README.md), [Parsing](parsing/README.md), [Core](core/README.md) and the [LSP server](../../../src/indexed/lsp/).

## Installed adapters and release evidence

- Put host-specific installation and lifecycle logic at the app boundary. Each adapter records or derives which settings and files it owns, preserves unrelated config and handles interrupted install, repeat, upgrade and uninstall. Assert the result in a fresh host profile and a profile with existing settings.
- Exercise the public interfaces from the packaged artifact. Evidence names the exact tag or build, runtime, host and language versions, fixtures and model configuration. Distinguish cold provisioning from warmed offline use. Retain a readback for each client and language capability claim.
- Freeze evaluation cases, relevance judgments, candidate budgets and quality/latency criteria before comparing retrieval modes. Compare the same corpus and inputs over the same configured scope. Keep per-query rankings, measurements, errors and model and environment identity. Record agent-task outcomes separately from document ranking.
- Check docs examples against the selected package. The readiness evidence records what passed, what failed, and what capability is still open. The issue tracker holds the executable slices and evidence links.

The shipped [Claude Code](../../../src/indexed/cli/install.py), [Codex](../../../src/indexed/cli/install_codex.py) and [OpenCode](../../../src/indexed/cli/install_opencode.py) installers, the [evaluation harness](../../../eval/README.md) and the [release workflow](../../../.github/workflows/python-release-ci.yml) provide baselines for the designs.
