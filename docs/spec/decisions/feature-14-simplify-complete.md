---
type: decision
updated: 2026-11-22
---

# 2026-07-10: Feature 14 (Simplify) complete

**Decision:** Shipped Feature 14 across six units, each a green commit: simplify/1
(unvendor `.agents/` skills, one root `AGENTS.md` ≤100 lines, benchmark CI
on-demand); simplify/2 (delete zero-consumer symbols — `SearchArgs`,
`CONFIG_REGISTRY`/`get_config_class`/`list_connector_types`, dead indexer orphans,
the never-instantiated sync Confluence reader, the dead `ProgressUpdate`/
`ProgressCallback` system, the never-batching `indexing_batch_size` loop, the
`_UpdatingCollectionCreator` wrapper); simplify/3 (collapse the 7-package workspace
to one `indexed` package under `src/indexed/` in one history-preserving `git mv` +
mechanical import rewrite, drop `una` + 8 per-package `pyproject.toml` +
`sync_version` role, replace the graph checker with `scripts/check_imports.py`);
simplify/4 (config CLI 2061→47 over get/set/list/validate, `create` de-cloned to one
schema-driven handler, delete `migration.py`, thin commands so every command file
≤300, prune unrendered Rich components, lazy connector-registry, + the two deferred
Foundation config cleanups: `ConfigService.instance()`→cached `get_config()/reload()`
and the single path/mode resolver); simplify/5 (prune pure Rich-chrome tests, rescope
coverage to core/connectors/config/parsing/utils/protocols with cli/mcp exempt,
≥85%); simplify/6 (`scripts/check_sizes.py` size gate + promote the architectural
merge-block to root `tech.md` + reconcile all root specs to the single-package
layout). A 5-finder adversarial bug-hunt over the refactors caught **one real
regression** — `config get --simple-output` on a section/ancestor path leaked nested
secrets in cleartext (masking checked only the queried key, not the returned value) —
fixed with recursive `_mask_sensitive_raw` + a regression test. R1/R3/R4/R5 verified;
full suite + system + characterization green; mypy 0-new; validate.sh clean.
**Deferred (R2 partial):** the indexer factory/registry + multi-indexer plumbing were
NOT deleted. The audit's "phantom generality" premise was factually wrong
post-Foundation — `get_indexer_config`/`indexer_factory` are the live path that
resolves the embedding **model** (3 supported models) from the persisted indexer
name, and the `manifest.indexers[]` array is a Foundation byte-stable on-disk
compatibility contract. Deleting the factory would inline duplicated FaissIndexer+
embedder construction at four call sites (an anti-simplification) and risk breaking
existing collections; the multi-indexer flatten only touches an in-memory 1-element
list for near-zero value. Left as a v2-rewrite follow-up.
**Rationale / honesty on size:** the spec's aspirational "~66k→15k / ~6k src / ~8k
tests" targets were **not** met (measured: ~21k src, ~28k tests) and are not
reachable under this feature's own non-goals ("no v2 rewrite, no behavior/feature
removal") — the app/connector/config layers are real functionality, and much of the
CLI shrink was extraction/reorganization (better structure, not raw deletion). The
genuine, durable wins are structural: one package instead of seven, ~12.6k LOC of
vendored skills unvendored, dead code gone, a 97%-smaller config CLI, a de-cloned
`create`, a cleaner config API, and a behavior-only suite with a scoped coverage
gate. `check_sizes.py` guards the real measured baseline (src ≤23k, tests ≤29k) to
prevent regrowth rather than assert a number a rewrite would be needed to hit.
