---
type: decision
updated: 2026-11-22
---

# 2026-07-19: Feature 16 (Core v2) shipped; Features 15 + 16 folders wrapped up

**Decision:** Core v2 is implemented (PR #158) and hardened by an end-to-end
testing pass that found two real bugs the unit tests + review missed — v2 was
embedding engine-owned metadata (paths/timestamps/chunk numbers) into every
vector (broke v1 relevance parity R8 and mixed ranking R11; fixed by excluding
metadata from the embed text), and the `v2` engine selector crashed via env/
config (only `--engine` normalized it; fixed in `CoreEngineConfig`'s validator).
Also shipped: distinct reranked `scoreKind`, unified relevance shown in mixed CLI
search, filename-only chunks no longer highlighted as the top result, `--collection`
alias on update/remove/migrate, and quieter missing-collection logs. Marked
Feature 16 DONE. **Wrapped up both owed feature folders:** promoted the core-v2
"Engine routing contract" cross-cutting block into [Core
Facade & App Composition Root](../tech/core-facade-composition-root.md) (correcting the stale "same on-disk format" swap
premise — v2 uses a new version-marked format), compounded the testing lessons
into [lessons.md](../lessons.md), then **deleted** `features/core-v2/` and
`features/review-remediation/` (review-remediation had no pending merge blocks;
its content shipped with PR #155). CODE IS TRUTH — live surface is `core/v2/`,
the facade, and `tests/`.
**Rationale:** a completed feature folder must not linger; durable cross-cutting
content lives in root specs, resolved detail in git history. E2E UX testing (not
just green unit tests) is what caught the metadata-in-embedding regression.
