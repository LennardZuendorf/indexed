---
type: decision
updated: 2026-11-22
---

# 2026-09-02: Feature 17 (Core v2 Discoverability) shipped; folder wrapped up

**Decision:** Merge PR #191's branch into `main`-tracking state (conflict was
narrow — `docs/spec/lessons.md` only, both sides had appended new dated entries
at the same spot; every generated/dependency file `main` had moved touched
in the interim — `uv.lock`, workflow YAMLs, `pyproject.toml`, a
`sentence-transformers` rename — merged clean via git's own three-way merge,
verified with `uv lock --check` plus a full re-run of the gate post-merge:
suite and coverage verified at delivery). Promoted the durable cross-cutting content and
**deleted** `features/core-v2-discoverability/`: the `--engine`
leaf/group/root precedence pattern (Click hands a child `Context` its
parent's `ctx.obj` by identity — a group/leaf callback writing into it needs
no new resolution tier) and the four-surface engine-error normalizer went to
[Engine Selection](../tech/app/app-engine-selection.md); the Rich-swallows-bracketed-
help-text gotcha went to [tech/app](../tech/app/README.md) § Markup Safety and
`AGENTS.md` Learnings (broadly reusable — any future `typer.Option(help=...)`
naming a config key is at risk); `--engine`, `index migrate`, and reranking
became shipped rows in [Features](../areas/README.md), also backfilling
pre-existing drift where Feature 16 (2026-07-19) had shipped without a
features-table update. Two items were deliberately left as **unresolved
follow-up candidates, not spec backlog:** a 5th engine-error surface
(`config validate`/`list`/`get`, found during the feature's final review,
confirmed outside R3/R6's 4-surface scope) and the same `help=`-discards-
docstring pattern already fixed on 5 commands but never audited for full
repo coverage. Neither blocks anything; either is a candidate GitHub issue if
a maintainer wants full closure, not something worth re-opening this spec
for. **Rationale:** a completed feature folder must not linger; durable
cross-cutting content belongs in root specs, resolved fix-by-fix detail
belongs in PR #191 + git history. CODE IS TRUTH — live surface is
`src/indexed/cli/`, `core/engine.py`, `core/v2/`, and `tests/`.
