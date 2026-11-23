---
type: tech
updated: 2026-11-22
applies: [".github/workflows/**", pyproject.toml]
---

# Release

The GitHub Release **tag** is the version, decided at release time — no manual
pre-bump in a PR. `pyproject.toml` declares `dynamic = ["version"]` and
**hatch-vcs** resolves the version from `git describe` at build time, so no
version string is stored in the repo at all. On `release: published`, the build
job checks out the tag at `fetch-depth: 0` (hatch-vcs needs the tags), builds,
asserts the built dists carry the tag version, validates (validate_wheel +
`twine check --strict`), and publishes wheel + sdist to PyPI via OIDC trusted
publishing (no token). There is **no backmerge job**: `main` has no version to
drift, so nothing has to be written back. Still no `sync_version.py`.

`uv.lock`'s root-package entry simply omits the `version` field (uv reports the
change as `indexed-sh v0.0.5 -> (dynamic)`; no such token is written to the
file), so the lock does not churn per commit.

Because no version string lives in the repo, the only way to ask a build what it
is at runtime is the installed metadata — surfaced to users as
`indexed --version` (see [Version flag](../app/app-version-flag.md)), which is
what the release checklist's post-publish step runs.

Off-tag builds use the `post-release` scheme (`raw-options` in
`[tool.hatch.version]`), yielding `<last-tag>.post<N>+g<sha>` — e.g.
`0.0.7.post4+g5d98c95` for four commits past `v0.0.7`, plus a `.dYYYYMMDD`
suffix when the tree is dirty. It anchors on the **last** tag rather than
guessing the next one; the default `guess-next-dev` would claim `0.0.8.devN`,
which is wrong whenever the next release isn't a patch bump. The `+g<sha>`
local segment is also a tripwire: PyPI rejects local versions, and the release
job's assert catches the mismatch before upload.
