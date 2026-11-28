---
type: concept
updated: 2026-11-28
---

# Output Formats

| Format | Use Case | Example |
|--------|----------|---------|
| **Card** | Rich terminal display | Default for `search` |
| **Table** | Structured comparison | `inspect` collections |
| **Compact** | Quick scanning | Titles only |
| **JSON** | Scripting/piping | `--json` flag |

## Inspect output (`indexed inspect`)

The inspect card distinguishes **where the collection is stored** from **where
its content came from**. `Storage` is the collection directory under
`.indexed/data/collections/<name>` (or `~/.indexed/...` in global mode); it was
previously labelled `Path`, which read as if it *were* the source. The old
label is gone from every view (brief list, `--verbose`, detail); `Storage`
carries the same value.

The detail and `--verbose` views also render the source block, read from the
manifest's `reader`:

| Row | Manifest field | Notes |
|-----|----------------|-------|
| `Source` | `reader.basePath` | Files collections; shown when the reader records a path. When the manifest records no source at all the card says `Source` / `not recorded`. |
| `URL` | first of `reader.baseUrl`, `reader.graphqlUrl`, `reader.host` | Omitted when absent (Jira/Confluence/Outline; GitHub). |
| `Query` | `reader.query` | Omitted when absent (Jira JQL, Confluence CQL). |

Each row is rendered only from a field the manifest actually recorded: a Jira
collection shows `URL` + `Query` and no `Source` row (it has no local path),
never `not recorded` beside a URL that is right there.

Long values (paths, JQL) fold onto extra lines; they are never
ellipsis-truncated. The brief list keeps its compact shape.

`--simple-output` / `--json` emits one object per collection (an array for a
listing) with these keys, in addition to the pre-existing `source_type` and
`path`:

| Key | Meaning |
|-----|---------|
| `path` | Unchanged, byte-identical to before: the collection's **storage** directory. |
| `storage_path` | The same value as `path`, under an unambiguous name. |
| `source_path` | `reader.basePath`, or `null`. |
| `source_url` | first of `reader.baseUrl`/`graphqlUrl`/`host`, or `null`. |
| `source_query` | `reader.query`, or `null`. |

Source keys are **`null` when not recorded** — never `""`, never the storage
path. Both engines derive them from the same `reader` block through one shared
allowlist projection (`src/indexed/core/source_metadata.py`): only `basePath`,
the URL keys and `query` are ever surfaced; the rest of a connector's reader
config (`includePatterns`, `collectionIds`, …) stays out of the output and out
of the machine contract.
