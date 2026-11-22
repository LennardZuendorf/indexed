---
type: tech
updated: 2026-11-22
applies: "src/indexed/cli/**"
---

# Version flag (`--version`)

`indexed --version` prints the **installed distribution's** version and exits 0.
The value comes from `indexed.utils.version.installed_version()`
(`importlib.metadata.version("indexed-sh")`), never from a constant in the tree —
`pyproject.toml` declares `dynamic = ["version"]` and hatch-vcs writes it at build
time (see [Release](../release/release.md)), so the metadata *is* the only truth.
A checkout with no installed metadata answers `unknown` instead of raising.

Output is the bare version on one line (`0.0.11`), no `indexed, version …`
prefix: the release checklist compares that string verbatim and so can any
script. The option is `is_eager=True` with a callback that raises `typer.Exit`,
so it answers before other options are validated and before any command or
`ConfigService` work happens — `--version` must never need config, storage or a
model. The callback imports its helper lazily so a normal invocation pays
nothing for it (`importlib.metadata` pulls `email`/`csv`/`zipfile`).

Tests: `tests/unit/indexed/test_app.py::TestVersionFlag` (flag prints the
metadata version, one bare line, appears in `--help`, honours the `unknown`
fallback, no-ops when absent) and `tests/unit/utils/test_version.py`.
