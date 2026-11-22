---
type: hub
updated: 2026-11-22
---

# Plan

Root roadmap: whole-feature gates only, no unit-level backlog, no long-horizon wishlist. Features (what/why) are in [product.md](product.md); architecture is in [tech.md](tech.md).

## Where we are

- [Current status](concepts/current-status.md): v0.1.0 Alpha, breaking changes allowed.
- [Current focus](concepts/current-focus/README.md): recently delivered work, by feature.
- [Versioning strategy](concepts/versioning-strategy.md): MAJOR.MINOR.PATCH and what alpha means.

## Sequence

- [Feature sequence](concepts/feature-sequence.md): binary whole-feature gates, features 1 to 24.
- [Delivered-feature detail](concepts/feature-sequence-detail.md): notes behind the rows.
- Feature folders (fallback layer; each needs a row here):

| Feature | Spec |
|---|---|
| collection-registry | [product](features/collection-registry/product.md), [plan](features/collection-registry/plan.md) |
| file-watcher | [product](features/file-watcher/product.md), [plan](features/file-watcher/plan.md) |
| github-connector | [product](features/github-connector/product.md), [plan](features/github-connector/plan.md) |
| lsp-tier0 | [product](features/lsp-tier0/product.md), [plan](features/lsp-tier0/plan.md) |
| lsp-tier1 | [product](features/lsp-tier1/product.md) |
| retrieval-eval | [product](features/retrieval-eval/product.md), [plan](features/retrieval-eval/plan.md) |

## Decisions

- [Decision log](decisions/README.md): dated planning decisions, features 14 to 18 and earlier.
- [Open questions](questions/README.md): product and technical.
