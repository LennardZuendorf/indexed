---
type: decision
updated: 2026-11-22
---

# 2026-09-01: Feature 17 (Core v2 Discoverability, issue #188) shipped

**Decision:** Implemented all 5 units (R1–R7 verified) via
`superpowers:subagent-driven-development` — a fresh implementer subagent per
unit, a task-scoped spec+quality review after each (all 5 Approved, only
Minor findings deferred to this log), then a final whole-branch review on the
most capable available model to catch what no per-unit review could: cross-unit
interactions. That review found no Critical issues but 3 real Important ones,
fixed in one wave and re-verified clean by a scoped re-review:
1. `--rerank`'s `--help` text contained the literal substring `[core.v2.rerank]`,
   which Rich's markup parser silently swallowed from the rendered output —
   the exact config key the flag's help exists to name was invisible. Fixed
   by dropping the brackets (matching the neighboring `--limit` option's
   existing unbracketed-config-key convention); the regression test was
   strengthened to assert the key text itself, not just the flag name.
2. R1's own requirement text named BOTH `index create --help` (the group) and
   `index create files --help` (the leaf) — only the leaf shipped in the
   original 5-unit plan (that was the CONFIRMed scope; the group surface was
   a gap the final review caught, not a plan violation). Fixed by adding a
   group-level `--engine` callback on `create.app`, mirroring the root app's
   own callback pattern exactly (writes into the same `ctx.obj["engine"]`
   slot via Click's parent→child `obj` inheritance) — verified empirically,
   not just by reasoning about Click internals, and confirmed to leave every
   existing R1 test (leaf position, leaf help, root-only regression,
   existing-collection raw-flag-only replay) untouched. Effective precedence:
   leaf flag > group flag > root flag > env > config > default.
3. R2's "never a silent no-op" requirement was technically violated for
   `--rerank` under `--simple-output` — a prior, independently-verified-correct
   fix had fully suppressed the hint there to protect stdout's JSON purity.
   Resolved by routing the hint to **stderr** under `--simple-output` instead
   of dropping it (`typer.echo(notice, err=True)`) — stdout stays pure,
   parseable JSON; the notice still exists on a channel a human running the
   command would see.
A 4th finding — a 5th surface (`config validate`/`list`/`get`) that still
leaks a raw pydantic dump or shows no warning for a bad `core.engine` value —
was deliberately left unfixed rather than silently expanding scope past the
CONFIRMed 7-requirement plan; recorded in product.md as a known remaining
surface for a future follow-up unit, not fixed ad-hoc mid-review.
**Rationale:** the two-human-gate model (plan→impl, verify→ship) means new
scope discovered during the ship-side review doesn't get silently absorbed
into the CONFIRMed plan's units — genuine requirement gaps the confirmed text
already covered (finding 2) get fixed; genuinely new scope (the 5th surface)
gets documented and deferred instead. Full gate green throughout: ruff/ty/
import-graph clean, full suite 93.30% coverage (>85% required).
