---
type: feature-product
feature: core-v2-discoverability
sibling: tech.md
parent: ../../product.md
updated: 2026-08-30
---

# Feature: Core v2 Discoverability — Product

Fixes the five product/UX gaps clustered in
[issue #188](https://github.com/LennardZuendorf/indexed/issues/188), found during
the review of PR #162 (Core v2). The underlying v2 safety story (migration
dry-run/backup/rollback, v1-stays-default scoping) is already correct and
verified — these are discoverability and consistency gaps a first-time v2
adopter hits, not correctness risks. Users are indexed CLI operators trying v2
for the first time; the output is a CLI/docs surface where `--engine`,
reranking, and `index migrate` are where a user would actually look for them,
and errors read the same regardless of which surface caught them.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | `--engine` on `index create`/`index create <source>` help + parsing (`src/indexed/cli/knowledge/commands/_create_options.py`, `_create_commands.py`, `create.py`, `_create_helpers.py`); a discoverable rerank flag on `index search` (`search.py`, `core/engine.py`, `core/v2/retrieval.py`); a clean `config set core.engine` error message (`config/commands/set.py`); Core v2 footprint in `README.md`; `index migrate --help` rendering its full safety docstring (`knowledge/cli.py`, `knowledge/commands/migrate.py`) |
| **Does not own** | Reranking *correctness* (tracked in a separate companion code-quality issue referenced by #188); the external hosted docs site (`indexed.sh/docs`); v1→v2 migration mechanics themselves (already shipped, Feature 16); the same `help=`-overrides-docstring pattern on `search`/`update`/`remove` (pre-existing elsewhere, not required by #188 — see tech.md Open Questions); the `[core] engine` config.toml validation error path (a related but distinct raw-dump site not named in #188 — see tech.md Open Questions) |

---

## Requirements

### Requirement: engine flag is visible where a v2 adopter looks for it

The system MUST accept `--engine` on `index create` and its four source
subcommands (`files`/`jira`/`confluence`/`outline`) — not only on the root
`indexed` callback — and MUST show it in `index create --help` / `index create
files --help`.

#### Scenario: engine flag placed after the subcommand

- **Given** a user runs `indexed index create files --engine v2 --path ./docs`
- **When** the command is parsed
- **Then** it MUST succeed (not `No such option: --engine`), and the new
  collection MUST be created with engine v2.

#### Scenario: help text advertises the flag

- **Given** a user runs `indexed index create files --help`
- **When** the help text renders
- **Then** it MUST list `--engine` among the shown options.

#### Scenario: subcommand flag still composes with the root flag

- **Given** a user runs `indexed --engine v2 index create files --path ./docs`
  (root-level flag, no subcommand flag)
- **When** the command is parsed
- **Then** engine resolution MUST behave exactly as it does today (unchanged
  root-level precedence) — the subcommand flag is additive, not a replacement
  of the existing root-level path.

### Requirement: Reranking has a discoverable CLI flag

The system MUST expose a `--rerank`/`--no-rerank` flag on `index search`,
shown in `index search --help`, that overrides `[core.v2.rerank] enabled` for
that one search.

#### Scenario: rerank forced on for one search

- **Given** `[core.v2.rerank] enabled = false` in config.toml and a v2
  collection
- **When** the user runs `indexed index search "query" --collection my-v2-docs
  --rerank`
- **Then** the search MUST rerank results for that call, without changing the
  stored config.

#### Scenario: flag omitted falls back to config

- **Given** no `--rerank`/`--no-rerank` flag is passed
- **When** a search runs
- **Then** behavior MUST be unchanged from today (`[core.v2.rerank] enabled`
  decides).

#### Scenario: rerank flag on a v1-only search

- **Given** a v1 collection (no rerank support in v1) and `--rerank` passed
- **When** the search runs
- **Then** the command MUST NOT crash and MUST make it visible to the user
  that reranking did not apply (exact wording — silent no-op vs. an explicit
  note — is an implementation decision, see tech.md Open Questions).

### Requirement: config set reports the same clean engine error as the flag and env paths

The system MUST report the identical clean, single-line message for an invalid
engine value regardless of which surface caught it (`--engine` flag,
`INDEXED__CORE__ENGINE` env, or `config set core.engine`) — never a raw
multi-line pydantic `ValidationError` dump.

#### Scenario: bad value via config set

- **Given** a user runs `indexed config set core.engine v3`
- **When** validation fails
- **Then** the printed error MUST be the single line `Invalid engine 'v3';
  expected one of: 1, 2, v1, v2` (the same message `--engine v3` and
  `INDEXED__CORE__ENGINE=v3` already produce), not a multi-line pydantic dump.

### Requirement: README documents Core v2's existence

The system MUST mention `--engine`, `index migrate`, and Core v2 in
`README.md`'s existing `## Usage` section (matching its terse, example-driven
style), so a user reading the documented entry point learns v2 exists without
`--help` archaeology.

#### Scenario: reader scans README Usage section

- **Given** a user reads `README.md` top to bottom
- **When** they reach `## Usage`
- **Then** they MUST see at least one example each of `--engine` and `index
  migrate`, styled consistently with the existing `create`/`search`/`config`
  examples.

### Requirement: index migrate help text shows the safety explanation

The system MUST render `migrate`'s full docstring (the `.v1-backup` /
rollback-safe explanation and usage examples) via `indexed index migrate
--help`, not just a one-line summary — this is the one command explicitly
designed to reassure a user before a data-changing operation.

#### Scenario: nervous user checks migrate help before running it

- **Given** a user runs `indexed index migrate --help` before their first
  migration
- **Then** the output MUST include the explanation that the original
  collection is kept as `<name>.v1-backup` and the operation is rollback-safe,
  plus the `Examples:` block — not only `"Migrate a v1 collection to v2"`.

---

## Non-Goals

- Reranking correctness fixes (separate companion code-quality issue
  referenced by #188).
- Rewriting or duplicating the hosted docs site (`indexed.sh/docs`) content —
  README additions stay short and point there for detail, matching the
  existing `## Documentation` pattern.
- Fixing the same `help=`-overrides-docstring pattern on `search`/`update`/
  `remove` (pre-existing elsewhere; #188 names only `migrate`).
- Fixing the `[core] engine` config.toml validation error path (also not
  fully clean today, but not named in #188 — flagged as a follow-up, see
  tech.md Open Questions).
- Any change to v1→v2 migration mechanics, v2 engine internals, or the
  version-dispatching facade beyond the one new `rerank` passthrough
  parameter.
