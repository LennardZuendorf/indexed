---
type: tech
updated: 2026-11-22
applies: [".github/workflows/**", pyproject.toml]
---

# Release (2)

`python-ci.yml`, `python-cov.yml`, and `python-release-ci.yml` check out at
`fetch-depth: 0`. On a shallow tagless checkout hatch-vcs resolves to
`0.0.0.postN+g<sha>` with only a `UserWarning`, and `validate_wheel.py` and
`twine check --strict` both still pass — a wrong version that goes green.
`python-benchmark.yml` is the exception: `pytest-bench-action` checks out at a
hardcoded `fetch-depth: 2` that no input overrides, so its install carries a
non-tag version. Nothing in the benchmark suite reads the version, so this is
tolerated rather than fixed.

Building from a tree with **no** `.git` (GitHub's auto-generated source tarball,
a vendored copy) resolves to the `fallback_version` of `0.0.0`. Without that
fallback hatch-vcs raises `LookupError` and the build dies — a regression
against the old static version. The fallback also supplies the base when git is
readable but no tag is reachable, which is why a shallow checkout reads
`0.0.0.postN+g<sha>` rather than `0.0.postN+g<sha>` — but it never yields a bare
`0.0.0` there, so the release assert still catches it. Measured with the current
config:

| checkout | built version |
| --- | --- |
| `HEAD` == tag, clean | exact tag version |
| tags reachable, off-tag | `0.0.7.post3+g21083d3d9` |
| shallow, tagless, clean | `0.0.0.post2+ga0347642e` |
| no `.git` | `0.0.0` |
