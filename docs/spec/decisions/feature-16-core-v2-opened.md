---
type: decision
updated: 2026-11-22
---

# 2026-07-18: Feature 16 (Core v2) opened; Feature 15 closed

**Decision:** Mark Feature 15 DONE (merged to `main` in PR #155; folder
wrap-up owed). Open Feature 16 Core v2: a LlamaIndex-based second engine
coexisting with the frozen v1 engine. Headline decisions (ADRs in the v2
planning doc, since moved to git history / PR #158): v2 uses a **new version-marked on-disk format**
(supersedes the "same on-disk format" swap premise); routing is
**manifest-authoritative** — explicit selectors (`--engine` flag >
`INDEXED__CORE__ENGINE` > `[core] engine` > default v1) apply to *new*
collections only, and a conflicting selector on an existing collection fails
loud; store is SimpleVectorStore with the store identity recorded and
dispatched per collection (FAISS excluded from v2 — LlamaIndex's FAISS
integration lacks delete/filters); embeddings via the native LlamaIndex
HuggingFace integration with v1's exact model — local-only, self-contained,
shared model cache; migration is explicit, offline-by-default, backed up and
reversible; remote providers (Ollama, …), additional stores (Qdrant, …), KG
and hybrid retrieval all deferred to future features behind the shipped
seams.
**Maintainer review 2026-07-18:** `--engine` naming and default-flip criteria
approved; remote providers + Qdrant descoped (units core-v2/5 and core-v2/7
retired); no v1 deprecation planning; PRs #132–#136 closed as superseded and
issues #5/#7 annotated. The prior attempt (PR #86 + splits #132–#136, closed/stale
against the deleted workspace layout) was reviewed: its adapter-at-boundary,
version marker, and mismatch-error patterns are kept; its flag-over-manifest
precedence, delete-before-persist, and hardcoded-FAISS load path are designed
out; recommend closing #132–#136 and annotating issues #5/#7.
**Rationale:** evidence-based reconciliation of the repo's swap-seam design,
the failed first attempt, and verified LlamaIndex capabilities (research in
git history / PR #158; feature folder deleted 2026-07-19).
