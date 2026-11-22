---
type: tech
updated: 2026-11-22
applies: [".github/workflows/**", "tests/system/**"]
---

# System Tests in CI

The Python 3.11–3.14 system jobs acquire `all-MiniLM-L6-v2` before
pytest so model-dependent tests can run. Before acquisition, the job resolves the
model manager cache path to an absolute `HF_HUB_CACHE` and exports it to later
steps, preserving the selected cache when tests isolate HOME. The workflows do not restore the
old immutable model cache key, which held a snapshot without weights. Model
acquisition failure fails setup rather than silently skipping those tests.
