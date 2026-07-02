---
type: feature-product
feature: architecture-audit
sibling: tech.md
parent: ../../product.md
updated: 2026-06-29
---

# Feature: Architecture Audit Remediation — Product

Captures the remediation requirements from the full monorepo architecture audit
(2026-06-29). This feature is the spec vehicle for fixing structural debt in
surviving v0.1 infrastructure before and during the v2 core/connectors rewrite.
It delivers a downward-only dependency graph, single-source configuration and
runtime bootstrap, CLI/MCP parity, connector consolidation, dead-code removal,
and the scaffold prerequisites that unblock v2 — without implementing v2 itself.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)
**Research:** [research/app.md](research/app.md) · [research/core.md](research/core.md) · [research/connectors.md](research/connectors.md) · [research/config.md](research/config.md) · [research/parsing-utils.md](research/parsing-utils.md) · [research/systemic.md](research/systemic.md)

---

## Scope

| | |
|---|---|
| **Owns** | Dependency graph fixes (core must not depend on connectors); protocols extracted to a lowest shared package; CLI and MCP storage-path and config parity; single-source config resolution; explicit app bootstrap (no import-time registration); connector registry consolidation; HTTP retry policy alignment; quick-win deletions of speculative and unused code; file-size compliance on all touched modules; v2 scaffold prerequisites (protocols package, import-graph CI gate). |
| **Does not own** | New product features (GitHub connector, Google Drive, etc.); full v2 engine implementation (separate future feature); thin-command extraction and oversized command-file refactors tracked in [issue #119](https://github.com/LennardZuendorf/indexed/issues/119) — overlap is acceptable but not required here. |

---

## Requirements

### Requirement R1: Downward-only dependency graph

The system SHALL enforce a downward-only dependency graph: the core engine MUST
NOT import concrete connector implementations or the connectors package; connectors
MUST NOT import the core engine, CLI, or MCP layers; and infrastructure packages
MUST NOT import anything above them.

#### Scenario: Core builds without connectors on the import graph

- **Given** the core package is analyzed for import dependencies
- **When** a static import-graph check runs in CI
- **Then** no module in the core package imports the connectors package or any
  concrete connector implementation, and the check passes.

#### Scenario: Connectors receive core behaviour via injection

- **Given** a collection create or update operation that needs a source adapter
- **When** the app orchestrates the pipeline
- **Then** the core engine receives a connector instance from the app composition
  root and never resolves connector types itself.

### Requirement R2: Protocols in the lowest shared package

The system SHALL define shared connector and source protocols (including metadata,
source configuration shapes, and progress reporting types) in a dedicated lowest-layer
package that both core and connectors depend on, and MUST NOT leave those contracts
defined in a higher layer.

#### Scenario: Both core and connectors depend on protocols only

- **Given** the protocols package is published in the workspace
- **When** core and connectors declare their dependencies
- **Then** both packages depend on the protocols package and neither package
  defines duplicate protocol types for the same contract.

#### Scenario: App wires concrete connectors against protocols

- **Given** a registered connector type in the app registry
- **When** the app builds a connector for a configured source
- **Then** the returned instance satisfies the shared protocol type from the
  protocols package without the core importing the concrete class.

### Requirement R3: CLI and MCP storage path parity

The system SHALL resolve collections storage location through one shared runtime
context used by both CLI and MCP entry points, honouring the same local/global
mode flags, workspace overrides, and configuration precedence.

#### Scenario: Same storage root for equivalent CLI and MCP sessions

- **Given** identical configuration, environment, and local-mode flags
- **When** the CLI lists collections and the MCP server lists collections in the
  same environment
- **Then** both surfaces read from and write to the same collections root.

#### Scenario: MCP respects local mode

- **Given** local mode is enabled via configuration or flag equivalent to the CLI
- **When** the MCP server starts
- **Then** it resolves collections under the workspace-local data directory, not
  the global user data directory.

#### Scenario: Global local flag affects behaviour, not display only

- **Given** the user passes a global local-mode flag on the CLI
- **When** any knowledge command runs
- **Then** storage resolution, not just help text or context display, uses the
  local collections path.

### Requirement R4: Single-source config resolution everywhere

The system SHALL resolve configuration through one authoritative read path per
mode (local vs global) and MUST NOT merge or reinterpret stored TOML through
parallel resolution paths that can diverge from the spec precedence chain.

#### Scenario: Read path matches write path

- **Given** configuration was written for a collection or workspace
- **When** any CLI command, MCP tool, or service reads that configuration back
- **Then** the value returned matches what was written without silent merge or
  fallback to a different resolution strategy.

#### Scenario: Mode override remains effective

- **Given** the configuration service has not yet been initialized for the process
- **When** the app entry point requests a specific local/global mode override
- **Then** all subsequent reads honour that override for the lifetime of the process.

#### Scenario: One precedence chain end to end

- **Given** defaults, global TOML, workspace TOML, environment variables, and
  CLI/MCP arguments that conflict on the same key
- **When** configuration is resolved
- **Then** the outcome follows the documented precedence (highest-priority source
  wins) through a single code path, with no secondary merge layer.

### Requirement R5: Explicit app bootstrap

The system SHALL perform all configuration registration, logging setup, and
connector registry initialization in explicit bootstrap functions invoked by app
entry points, and MUST NOT register config specs, configure logging, or mutate
global singleton state at module import time.

#### Scenario: Importing a library module has no side effects

- **Given** a fresh Python process that imports core, config, connector, or app
  modules without calling an entry point
- **When** import completes
- **Then** no configuration specs are registered, logging is not configured, and
  no connector registry is populated.

#### Scenario: CLI and MCP call bootstrap before work

- **Given** the user invokes the CLI or starts the MCP server
- **When** the entry point runs
- **Then** bootstrap registers config, configures logging, and builds the connector
  registry before any command handler or tool executes.

### Requirement R6: IndexedError at boundary layers

The system SHALL translate domain and package failures into `IndexedError`
subtypes at CLI, MCP, and connector boundaries, and MUST NOT swallow exceptions
silently or map all failures to generic error dictionaries without classification.

#### Scenario: MCP maps IndexedError to structured errors

- **Given** an operation that raises a typed `IndexedError` subtype
- **When** the MCP tool handler catches the failure
- **Then** the client receives a structured error response that preserves the
  error category and a user-safe message, not a bare exception string from an
  unclassified catch-all.

#### Scenario: CLI maps IndexedError to exit codes and messages

- **Given** an operation that raises a typed `IndexedError` subtype during a CLI
  command
- **When** the command exits
- **Then** the user sees a clear message appropriate to the error type and the
  process exits with a non-zero code without a full traceback for expected failures.

#### Scenario: Unexpected errors still propagate

- **Given** an operation that raises a non-IndexedError exception
- **When** the boundary layer handles the failure
- **Then** the error is logged with traceback and propagates or exits with
  diagnostic detail suitable for debugging.

### Requirement R7: Connector registry single path

The system SHALL construct connector instances through one app-owned registry
and MUST NOT maintain parallel builder functions in core factories that
 independently instantiate the same connector types.

#### Scenario: Create and update use the same registry

- **Given** configured sources for Jira, Confluence, files, or Outline
- **When** collection create and collection update both need a connector
- **Then** both flows obtain the connector from the same registry entry, not
  from separate copy-pasted builder logic.

#### Scenario: No triple instantiation paths

- **Given** an audit of connector construction call sites
- **When** remediation is complete
- **Then** at most one registry-backed code path exists per connector type for
  runtime instantiation (excluding tests).

### Requirement R8: HTTP retry policy consistent (transient-only)

The system SHALL apply HTTP retries only for transient failures (timeouts,
connection errors, rate limits, and explicitly classified retryable status codes)
and MUST NOT retry non-transient client or server errors.

#### Scenario: 404 is not retried

- **Given** an HTTP client call that receives a 404 response
- **When** the retry wrapper executes
- **Then** the call fails immediately without further attempts.

#### Scenario: Timeout is retried with backoff

- **Given** an HTTP client call that times out
- **When** the retry wrapper executes within configured limits
- **Then** the call is retried with backoff until success or retry exhaustion.

#### Scenario: Connectors share one retry policy

- **Given** Jira, Confluence, and Outline connectors performing outbound HTTP
- **When** each encounters the same transient failure class
- **Then** all use the same shared retry classification and backoff behaviour.

### Requirement R9: Delete speculative and unused code

The system SHALL remove code identified in the audit as unused, deprecated, or
speculative, including the Faiss auto-indexer experiment, deprecated connector
wrappers superseded by current implementations, and dead data-transfer objects
with no live callers.

#### Scenario: Removed modules have no remaining imports

- **Given** deleted modules from the audit inventory
- **When** the test suite and static import analysis run
- **Then** no production code imports the deleted symbols and all tests pass.

#### Scenario: Deprecated wrappers are gone

- **Given** legacy Jira or Confluence wrapper modules marked deprecated in the audit
- **When** remediation ships
- **Then** those wrappers are removed and callers use the current connector
  implementations only.

### Requirement R10: File size compliance on touched modules

The system SHALL keep every new or materially changed module within the
architectural file-size limits (CLI commands, services, and general modules as
defined in root tech architectural rules), splitting or extracting logic when a
 touched file would otherwise exceed its limit.

#### Scenario: Changed command files respect CLI limit

- **Given** a CLI command file modified by this feature
- **When** remediation for that file is complete
- **Then** the file is at or below the CLI command line limit, with business
  logic extracted to a service module if needed.

#### Scenario: New bootstrap and runtime modules stay bounded

- **Given** new app bootstrap or runtime context modules introduced by this feature
- **When** they are merged
- **Then** each module is at or below the general module limit and has a single
  clear responsibility.

### Requirement R11: v2 scaffold prerequisites

The system SHALL land the minimum structural prerequisites for the v2
core/connectors rewrite: the protocols package (R2), a passing import-graph CI
gate (R1), and documented promotion of architectural rules into root specs —
without implementing v2 engine or connector logic.

#### Scenario: Import-graph CI gate blocks regressions

- **Given** CI runs on every pull request touching package dependencies
- **When** a change reintroduces a forbidden import (e.g., core importing connectors)
- **Then** the import-graph check fails and the change cannot merge.

#### Scenario: Protocols package is workspace-ready

- **Given** the v2 feature branch is started
- **When** its authors add dependencies
- **Then** they can depend on the protocols package and app bootstrap patterns
  delivered by this feature without further graph surgery.

#### Scenario: Architectural rules promoted on completion

- **Given** this feature reaches COMPOUND
- **When** cross-cutting decisions are merged to root specs
- **Then** root tech architectural rules reflect the enforced dependency graph,
  bootstrap pattern, and boundary error handling delivered here.

---

## Outputs

- Corrected package dependency graph with CI enforcement
- Shared protocols package consumed by core and connectors
- Unified runtime context for CLI and MCP (storage path, config mode)
- Explicit app bootstrap replacing import-time side effects
- Single connector registry and consolidated HTTP retry behaviour
- Removed dead and speculative modules from the audit inventory
- Updated root and feature specs reflecting promoted architectural rules
- Green quality gate (lint, types, tests, coverage) after all remediation units

---

## Non-Goals

- Shipping new data-source connectors or net-new user-facing capabilities
- Implementing v2 indexing engine, persistence, or search semantics
- Complete thin-command refactors or service extractions beyond what file-size
  compliance requires on files this feature touches (see issue #119)
- Performance optimization, embedding model changes, or index algorithm upgrades
- Multi-user server mode, sharding, or embedding-version migration (root open
  questions remain deferred)

---

## Open Questions

1. **Scope of file-size fixes in untouched commands** — this feature enforces
   limits on touched files only; whether to batch-refactor remaining oversized
   commands is tracked separately in issue #119. Default: do not expand scope.

2. **MCP tool vs resource surface alignment** — audit noted drift between shipped
   MCP tools and documented resources; parity work here covers storage and error
   paths, but full MCP API realignment may need a follow-up if product scope
   changes. Default: fix parity blockers (collections path, errors); defer cosmetic
   API renames unless they block v2.

3. **Parsing/utils consolidation depth** — research cluster identifies duplication
   opportunities; this feature deletes clear dead code but may defer larger
   parsing refactors unless they block graph or bootstrap work. Default: delete
   and defer structural parsing changes to v2 or a dedicated hygiene pass.
