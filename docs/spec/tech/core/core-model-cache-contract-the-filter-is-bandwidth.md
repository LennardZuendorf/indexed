---
type: tech
updated: 2026-11-22
applies: "src/indexed/core/**"
---

# Model cache contract: The filter is bandwidth

**The filter is bandwidth, never a correctness gate.** Weights are necessary
but not sufficient, so `ensure_model` proves the filtered snapshot is complete
before reporting success, using the repo's own declarations rather than a
hardcoded model shape:

- Module directories are named per model (`1_Pooling`, `2_Dense`, …), so the
  allow-list matches their payload shapes (`*/config.json`,
  `*/model.safetensors`, `*/pytorch_model.bin`) instead of one model's layout.
  A multilingual model whose Dense head was filtered out used to pass the
  weights-only predicate, so `init` said "setup complete" and every load raised
  `corrupt`, with a `--force` remedy that rebuilt the same snapshot.
- A referenced module dir the filter still missed is fetched from the repo by
  its own `modules.json` (`<path>/*`, one retry). A directory that stays absent
  after that has no files in the repo — a parameterless module such as
  `2_Normalize` — which is the loader's normal case, so it is never a failure
  and never triggers a full-snapshot download.
- Every transformers tokenizer artifact class is allow-listed
  (`tokenizer.json`, `vocab.txt`/`vocab.json`+`merges.txt`,
  `sentencepiece.bpe.model`, `spiece.model`, `spm.model`, `tokenizer.model`);
  a repo that declares `tokenizer_config.json` yet lands none of them gets one
  full-snapshot retry.
- A filtered snapshot with no weights at all (custom repo publishing only
  `pytorch_model.bin`) retries once without patterns; a still-weightless result
  raises as corrupt.
