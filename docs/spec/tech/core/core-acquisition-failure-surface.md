---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Acquisition failure surface (issue #210)

**File:** `src/indexed/core/model_acquisition.py`

Acquisition (download/load) is bounded and categorized so an impossible
acquisition fails predictably instead of leaking dependency retry chatter:

- `acquire_with_retry` retries only transient failures (network / HTTP 429) up
  to `MAX_ATTEMPTS = 3` with exponential backoff; permanent failures (missing
  repo, 401/403/gated) raise immediately. Every retry logs at DEBUG, so
  `--debug` keeps the timeline while the default surface shows one line.
- The final failure is wrapped in `ModelAcquisitionError` (an `IndexedError`) —
  model name, cache dir + state, failure category, and a category-specific
  remedy (`indexed init --model …` / `--force` / network / auth). Token-shaped
  secrets are redacted from any cause text.
- `huggingface_hub`'s per-retry WARNINGs are floored at ERROR in
  `utils/logger.py`; `--debug` lowers them back to DEBUG. transformers' "does
  not appear to have a file named pytorch_model.bin or model.safetensors" fires
  for ANY swallowed lookup (offline, unreachable hub, gated, or genuinely
  absent) and must never surface raw.
- `ensure_model` verifies the download left weights; a "successful" weightless
  call raises rather than reporting a cached success. `--force` create no longer
  clears the existing collection up front — the build-aside/rename-swap keeps a
  failed acquisition from clobbering a healthy index.
