---
type: tech
updated: 2026-11-22
applies: pyproject.toml
---

# Wheel

A single `hatchling` build packages `src/indexed/` into one wheel — no bundling
step, no per-package builds.

```bash
uv build --out-dir dist
# → dist/indexed_sh-<version>-py3-none-any.whl   (wheel)
# → dist/indexed_sh-<version>.tar.gz             (sdist)
uv run python scripts/validate_wheel.py dist/*.whl   # PyPI archive validator (wheel only), also in CI
uv run --with twine twine check --strict dist/*      # metadata render check (wheel + sdist), also in CI
```
