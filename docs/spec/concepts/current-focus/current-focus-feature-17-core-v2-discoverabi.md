---
type: concept
updated: 2026-11-22
---

# Current Focus: Feature 17 Core v2 Discoverability is

**Feature 17 Core v2 Discoverability is DONE** (implemented 2026-09-01, spec
drafted 2026-08-30): seven product/UX requirements, five units, clustered
from the PR #162 review in
[issue #188](https://github.com/LennardZuendorf/indexed/issues/188) plus two
same-shape sibling defects folded in — `--engine` surfaced on `index create`
and its four leaf subcommands (plus a group-level `--engine` callback on
`index create` itself, added during final review to fully satisfy R1's
requirement text); a `--rerank`/`--no-rerank` flag on `index search` that
prints a hint rather than silently no-op on a v1-only search (routed to
stderr under `--simple-output` to keep stdout JSON-pure); a clean,
byte-identical single-line engine-error message on all four surfaces that
can catch a bad value (`--engine` flag, env, `config set core.engine`, and
hand-edited `config.toml`); Core v2 mentioned in README's `## Usage`; and
every knowledge command's `--help` (not just `migrate`'s) rendering its own
docstring. No correctness risk; Core v2 itself (Feature 16) already worked —
this was entirely a discoverability/UX surface fix. Implemented via
`superpowers:subagent-driven-development` (one implementer + one task review
per unit, all 5 Approved) plus a final whole-branch review that caught 2 real
cross-unit bugs a per-unit review couldn't (a Rich-markup bug swallowing
`--rerank`'s help text, and the group-level `--engine` gap above), fixed in
one wave and re-verified clean. One newly-discovered 5th engine-error surface
(`config validate`/`list`/`get`) was deliberately left out of scope rather
than expanding past the CONFIRMed plan — recorded as a known follow-up
candidate (see below). Full gate green: ruff/ty/import-graph clean, full
suite 93.30% coverage (>85% required). **Wrapped up 2026-09-02:** the
durable cross-cutting content promoted to root specs — the leaf/group/root
`--engine` precedence + shared-`ctx.obj` mechanism and the four-surface
error normalizer to [Engine Selection](../../tech/app/app-engine-selection.md); the Rich
markup-swallows-bracketed-help-text gotcha to [tech/app](../../tech/app/README.md) §
Markup Safety and `AGENTS.md` Learnings; `--engine`/`index migrate`/
reranking as shipped rows in [Features](../../areas/README.md) (CLI +
Search — also closed pre-existing drift where Feature 16 had shipped without
a features-table update); resolved backlog (the R1-R7 fix-by-fix detail,
the 5th engine-error surface note, the deferred generic misplaced-option
hint) lives in PR #191 and git history, not the spec. Feature-spec folder
deleted — live surface is code + root specs only.
