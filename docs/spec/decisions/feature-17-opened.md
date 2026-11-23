---
type: decision
updated: 2026-11-22
---

# 2026-08-30: Feature 17 (Core v2 Discoverability, issue #188) opened; scope expanded same day

**Decision:** Capture the five PR #162-review UX findings in
[issue #188](https://github.com/LennardZuendorf/indexed/issues/188) as
Feature 17 rather than fixing ad-hoc: `--engine` invisible on `index create`
subcommands (root-only today, mirrors the existing `--local` pattern for the
fix); reranking has no CLI flag (v2-only, `[core.v2.rerank]` today); `config
set core.engine` prints a raw multi-line pydantic dump instead of the clean
single-line message `--engine`/`INDEXED__CORE__ENGINE` already produce (fix:
reuse `composition.normalize_engine_selector` directly — `config/commands/`
is exempt from the config-package import-purity rule, so no layering
violation); README has zero Core v2 mention; and `index migrate --help`
discards its safety docstring because `knowledge/cli.py` registers it with an
explicit `help=` override. Investigated via 4 parallel research subagents
against `main`, all file:line anchors re-verified by direct reads.
**Same-day follow-up:** on maintainer review, two questions left open by the
initial spec were resolved and two related-but-descoped defects were pulled
into scope rather than left as follow-ups: (1) `--rerank` on a search that
resolves to no v2 collection now must print a one-line hint instead of
silently no-op (`core/versioning.py::detect_engine_version` per searched
collection decides); (2) the config.toml `[core] engine` path gets the same
clean-error fix as `config set` — `resolve_engine_selector`'s config.toml
branch drops `bind()`/pydantic entirely in favor of a raw
`config_service.get("core.engine")` read, closing the last of four surfaces
that can catch a bad engine value; (3) the `help=`-discards-docstring fix
extends from `migrate` to its three siblings (`search`/`inspect`/`update`/
`remove`), same file (`knowledge/cli.py`), same mechanism. The one item that
stays descoped by explicit maintainer choice: a generic Click "did you mean
the top-level flag?" hint for a misplaced `--engine` on the flat commands —
R1's direct fix (surfacing `--engine` on `index create`) already resolves
#188's concrete repro. Now 7 requirements across 5 units (R6 rides with R3's
unit, R7 with R5's). **Rationale:** all seven are discoverability/consistency
gaps on a feature (Core v2) whose safety story already works and is verified
— small, disjoint, no data-loss risk — but worth a spec so each fix carries
its own scenario instead of being patched ad-hoc during a support pass; the
two folded-in defects are the same shape as findings already in the spec, so
fixing them alongside is cheaper than tracking a separate follow-up issue.
