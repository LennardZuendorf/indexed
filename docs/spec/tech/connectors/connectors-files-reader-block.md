---
type: tech
updated: 2026-11-22
applies: "src/indexed/connectors/**"
---

# Files Reader Block — Persisted Keys

`FilesDocumentReader.get_reader_details()` is the **single writer** of the manifest `reader`
block for `localFiles` (core calls it; `SourceConfig.reader_opts` never reaches the manifest).
`FileSystemConnector.from_manifest` must therefore read back exactly the keys it writes, or
an `update` silently reverts that option to a `FileSystemConfig` default. The contract is
whole-block: `test_files_manifest_reader_block_round_trips_every_persisted_setting` compares
create-time and update-time blocks, so adding an option without persisting it fails CI.

| Key | Source | Read back by `from_manifest` |
|-----|--------|------------------------------|
| `type` | constant `localFiles` | dispatch |
| `basePath` | `path` (absolute, normalized) | yes (required) |
| `includePatterns` | `include_patterns` (`!` negations kept) | yes |
| `failFast` | `fail_fast` | yes |
| `respectGitignore` | `respect_gitignore` | yes |
| `excludedDirs` | `excluded_dirs` (defaults to `DEFAULT_EXCLUDED_DIRS`) | yes |
| `ocr` | `ocr_enabled` | yes |
| `tableStructure` | `table_structure` | yes |
| `codeChunking` | `code_chunking` | yes |
| `maxChunkTokens` | `max_chunk_tokens` | yes |
| `changeTracking` | `change_tracking` | yes |

Decision (2026-11-03): **persist and honour**, not "stop reading". `changeTracking` was read
with an `auto` fallback while nothing wrote it, so every update lost an explicit
`content_hash`/`mtime`/`none`. `codeChunking` was written nowhere and the flag never reached
`ParsingModule`; `false` now routes code extensions through the plaintext parser instead of
`CodeChunker` (see [tech/parsing](../parsing/README.md)).
