---
type: tech
updated: 2026-11-22
applies: [.github/workflows/python-eval.yml, scripts/eval_ab_run.py, "eval/**", "src/indexed/eval/**"]
---

# Retrieval Evaluation Gate

`python-eval.yml` measures the merge's first parent and its corresponding PR
merge result in one job. It fetches immutable SHAs with depth 3 and applies the
same proof described in CI Benchmarking — the merge commit's first parent is
the measured base — then verifies each measured HEAD. Each side uses its own
detached worktree and
`uv sync --locked` environment. Dispatch measures its captured revision twice;
it never resolves a moving branch tip. The common launcher is captured once
from the merge result and runs by absolute path through each side's own Python.

Before either side parses, the job pins one absolute Hugging Face cache and
acquires the embedding and parser tokenizer models. It loads the tokenizer
locally, verifies its vocabulary against model config, and constructs the
token-aware HybridChunker; a failure blocks both measurements. The cache and model snapshot identities are logged. Both sides
inherit the same cache while retaining their own locked dependencies.

`scripts/eval_ab_run.py` calls the side's existing `run_eval(connector_factory=...)`
API. It loads only the shared `eval/canonical.py` helper by explicit file path.
The side retains its own evaluator runner, core, parser, connectors and lock.
Actual import origins must be inside that side. Reports record full engine and
harness SHAs, lock digest, common-file digests and whether instrumentation
matches its captured commit. Local uncommitted instrumentation says so. Report outputs reject nonregular
paths with `lstat` and use exclusive temporary descriptors plus atomic replacement.

The evaluator-only converter replaces recognized generated leading absolute
code/plaintext path context with `eval/corpus/<relative path>`. It preserves
authored body occurrences, headings, chunk boundaries, IDs and physical
URLs/metadata. The default local evaluator uses the same canonical factory;
explicit custom factories remain supported. Effective configuration records
`input_context_policy=eval-corpus-relative-v1` (or `custom`).

`environment.converter_inputs` hashes normalized converter chunks with the
boundary label `normalized-converter-chunks`. It does not claim to capture
post-engine embedding inputs. Equal digests are checked during same-source
stability validation; intentional parser/engine changes may change inputs.
