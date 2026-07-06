---
type: feature-product
feature: simplify
sibling: tech.md
parent: ../../product.md
updated: 2026-07-06
---

# Feature: Simplify — Product

Codebase Reduction. `indexed` today is ~66k lines: a ~3k-line engine wrapped in
~18k of CLI/config chrome, ~25k of tests (much of it exercising mechanism, not
behavior), and ~15k of vendored process apparatus, spread across a seven-package
`uv` workspace. This feature makes the code SMALLER without changing what the
tool does for its user: collapse the workspace to a single package, delete
machinery that has no second implementation, right-size the CLI and config
surface, keep only behavior tests, and trim the engineering apparatus. Every
change is size-only; a user running `index create`, `index search`,
`index update`, and the MCP server sees identical behavior before and after.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | Repository layout (workspace → one package, one build); deletion of dead/phantom-generality code; the size of the CLI and config command surface; test composition (behavior vs mechanism) and the coverage gate's scope; the process apparatus (`AGENTS.md` count, vendored skills, CI shape). |
| **Does not own** | Any behavior, bug fix, contract, or failure semantics — all correctness and the typed-contract/facade groundwork are Feature `foundation`, which this feature depends on being DONE. The eventual v2 engine rewrite (this only leaves the seam clean for it). On-disk collection format (unchanged; the compatibility boundary is fixed by `foundation`). |

---

## Requirements

### Requirement: Single package

The system SHALL build and ship as a single `indexed` package producing one
wheel (`indexed-sh`) from one `pyproject.toml`, with the `una` bundler, every
per-package `pyproject.toml`, and the version-sync script removed, and the
workspace import-graph checker replaced by a slim single-package import check.

#### Scenario: One build, one wheel

- **Given** the collapsed repository with a single `pyproject.toml`
- **When** the wheel is built in a clean environment and installed
- **Then** exactly one wheel is produced, both console entry points run
  (`indexed --help` and the MCP server `--help` succeed), and no `una` step,
  per-package build, or version-sync step participates in the build

### Requirement: No phantom generality

The system MUST NOT retain machinery that abstracts over a single
implementation: the indexer registry/factory/naming scheme and multi-indexer
plumbing (one indexer exists), the batch size that never batches, unused data
transfer objects, dead registry lookup APIs, re-export compatibility shims, the
updating-creator wrapper, the never-instantiated synchronous confluence-cloud
reader, and the redundant second progress-callback system.

#### Scenario: Dead API is gone

- **Given** the audited list of zero-consumer symbols
- **When** the repository is grepped for each deleted symbol name
- **Then** no production or test reference remains, and the full suite passes

### Requirement: Right-sized CLI

The system SHALL expose one schema-driven `create` command covering every
source (replacing four near-identical command clones), a config command surface
reduced to get/set/list/validate, no one-time legacy migration command, and a
Rich rendering surface pruned to the components actually rendered — with no
single command file exceeding 300 lines.

#### Scenario: Per-source create parity

- **Given** the single schema-driven create command
- **When** a collection is created from each source (files, and the three
  network sources against stubbed HTTP)
- **Then** each produces a searchable collection whose known query returns its
  known hit, matching the behavior of the four prior per-source commands

### Requirement: Behavior-only tests

The system SHALL keep behavior, system, and benchmark tests plus the
`foundation` characterization harness, and delete mechanism tests (registry
membership, re-export shims, protocol-conformance stubs, Rich-markup rendering,
legacy migration), with the coverage gate scoped to engine, connector, and
config code (UI chrome exempt) and the total test corpus reduced toward its
size target.

#### Scenario: Suite survives a rename

- **Given** the reduced, behavior-only suite
- **When** an internal symbol is renamed without changing behavior
- **Then** the suite still passes (no test asserted the old name or internal
  structure), and the coverage gate on engine/connector/config code stays green

### Requirement: Right-sized process apparatus

The system SHALL consolidate the seven real `AGENTS.md` files (root + six
per-package) into one root `AGENTS.md` of at most 100 lines, unvendor the
checked-in agent skills so they install from a lockfile, and trim CI to lint,
type-check, test, import-check, and wheel-smoke with benchmarks moved to an
on-demand workflow. The by-design `CLAUDE.md`/`WARP.md` symlinks (multi-tool
compatibility) SHALL be preserved on the surviving root file, not treated as
duplication to remove.

#### Scenario: One AGENTS.md

- **Given** the collapsed repository
- **When** the repository tree is inspected for engineering-contract docs
- **Then** exactly one real `AGENTS.md` exists at the root (≤100 lines) with its
  `CLAUDE.md`/`WARP.md` symlinks intact, no vendored skill tree is checked in,
  and CI runs only the trimmed gate set

---

## Non-Goals

- No behavior change of any kind. This feature fixes no bugs and adds no
  features; correctness is entirely `foundation`'s.
- No change to the on-disk collection format or to existing collections.
- No v2 engine rewrite — this feature only ensures the single-package layout,
  clean edges, and behavior-only suite make that rewrite a drop-in later.
- No new capability, source, or configuration key.

## Open Questions

1. **Coverage floor after UI exemption** — Once UI chrome is exempt from the
   coverage gate, the >85% floor applies to a smaller, denser base. Confirm the
   floor still holds against engine/connector/config only; recommend keeping
   85% and letting the reduced surface raise the effective number.
