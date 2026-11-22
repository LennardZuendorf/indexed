---
type: tech
updated: 2026-11-22
applies: ["src/indexed/core/**", src/indexed/cli/composition.py]
---

# Core Facade & App Composition Root

**Core is consumed only through the version-dispatching facade `indexed.core.engine`**
— `create` / `update` / `search` / `inspect` / `status` / `clear` / `collection_exists`
(+ the shared models): 13 names, the same surface as the former `core.v1.engine`, plus an
`engine=` selector. The facade (lazy `__getattr__`) routes every call to the v1 or v2
engine. For existing collections the on-disk manifest `version` marker is **authoritative**
— an explicit selector may only confirm it or fail with `EngineMismatchError`; selectors
(flag > env > config > default) choose the engine for **new** collections only. A collection
with no `version` key is v1. The unrecognized-version contract now SPLITS by op, per the
final review of issue #186:

- `create` / `update` / `clear` (via `_resolve_existing_engine`) still **fail loud** —
  `UnknownEngineVersionError`, never a silent v1 fallback, collection untouched.
- `search` / `status` / `inspect` (via `_group_names_by_engine`) instead **omit** the
  unrecognized-version collection from its batch (a warning is logged) rather than
  aborting the whole call. `search()`'s return type is a dict keyed by collection name, so
  it CAN and does carry the omission back as a per-collection `{"error": <message>}` entry
  (the same convention `core/v2/retrieval.py` and v1's `search_service.py` already use for
  a per-collection failure inside a batch); `status()`/`inspect()` return plain lists with
  no per-item error slot, so they purely omit it with a logged warning — unchanged.

Bulk updates filter collections by an explicit engine selector before the
update loop. MCP startup falls back to the default engine when its unused
selector is invalid. Configuration writes to `core.engine` validate before dry-run; v2 resolvers
propagate validation errors only for their own namespaces. Migration reports
`backup_purged` only after verifying removal. CLI and MCP share relevance
conversion while retaining each result's true score kind; reranking redirects
third-party stdout diagnostics to stderr. These are the shipped issue #186
contracts, not instructions to reapply its retired implementation plan.
