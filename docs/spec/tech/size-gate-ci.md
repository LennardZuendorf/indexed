---
type: tech
updated: 2026-11-22
applies: [scripts/check_sizes.py, ".github/workflows/**"]
---

# Size-Gate CI

`scripts/check_sizes.py` enforces the structural collapse (one package dir, one
real `AGENTS.md`, one `pyproject.toml`, no `[tool.una]`) plus src/test LOC. In CI
the LOC half is **growth against the merge base**, not a stored number:
```bash
uv run python scripts/check_sizes.py --baseline-ref <base>   # CI: measured(HEAD) <= measured(base) + allowance
uv run python scripts/check_sizes.py                        # offline: legacy absolute ceilings
The workflow passes the merge commit's first parent on a PR (the base the tree
was actually built on — `base.sha` can already be stale) and
`github.event.before` on a `main`/`building` push, so the ratchet also runs
after merge. `GROWTH_ALLOWANCE`
(src 2_500 / tests 3_300 lines per branch) is the largest per-commit growth over
the 40 commits on `main` before 2026-11-15 (+2_573 tests / +1_956 src, both #265)
plus ~25 % margin: exceeding it means the branch is
bigger than any reviewed unit this repo has landed, so split it rather than
raising the number. Branches therefore never edit a shared ceiling — the reason
this replaced the hand-bumped `TEST_LOC_MAX`, which made every test-adding branch
conflict with every other one.
```
