---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Model cache contract

**Files:** `src/indexed/core/v1/engine/indexes/embeddings/model_manager.py`,
`src/indexed/core/v2/embedding/local.py`, `src/indexed/core/model_acquisition.py`

The embedding model lives in the shared HF hub cache (`HF_HUB_CACHE` >
`HF_HOME/hub` > `~/.cache/huggingface/hub`, `models--<org>--<name>/snapshots/<rev>/`).
A model counts as **cached** only when a snapshot holds a real weights file
(`model.safetensors` / `pytorch_model.bin`, resolving to a completed blob) — hub
symlinks a snapshot file only once its blob completes, so an interrupted download
leaves config/tokenizer files WITHOUT weights, and a weights-blind "any file"
check would pin the load offline (`local_files_only=True`) and then fail on the
missing weights — one interrupted download bricks every embedding op until a
manual re-download. v1 (`is_model_cached`) and core.v2 (`_is_model_cached`)
carry identical semantics (a parity test keeps them in lockstep).

**Predicate and loader are one selection.** v1's `_select_cached_snapshot` is the
single source for both `is_model_cached` and `_resolve_snapshot_path`, and
`load_model` loads THAT snapshot path (not the repo id) with
`local_files_only=True` — so "cached" always means "loadable offline" and a
config-only residue can never be reported as a false cached success. refs/main
names the active revision; with none, the first weights-bearing snapshot wins.

**Pre-download is the load set, not the repository.** `ensure_model` passes
`_MODEL_ALLOW_PATTERNS` to `snapshot_download` — safetensors weights, the
tokenizer artifacts, the sentence-transformers module payloads and the
model/ST configs — because the unfiltered repository also publishes ONNX,
OpenVINO, TF, Rust and torch-`.bin` variants no Indexed path loads (measured
2026-11-16 on a clean `HF_HOME`: 889 MB for the full snapshot vs 88 MB for this
set, which is exactly what a first `index create` downloads). The ONNX export
is never required: v2 embeds through LlamaIndex/torch, and v1 attempts ONNX
from the cached snapshot and falls back to torch.
