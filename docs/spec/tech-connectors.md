---
type: branch
scope: connectors
parent: tech.md
covers: connector protocol, implemented connectors, change tracking
updated: 2026-11-14
---

# Tech Branch: Connectors (`src/indexed/connectors/`)

Protocol-based data-source adapters. May import protocols/config/utils/parsing;
MUST NOT import core engine, CLI, or MCP (see [tech.md](tech.md) § Architectural Rules).

**Parent: [tech.md](tech.md).** Document parsing: [tech-parsing.md](tech-parsing.md).

---

## Connector Protocol

**File:** `src/indexed/protocols/connectors.py`

```python
from typing import Any, Iterator, Protocol, runtime_checkable

@runtime_checkable
class DocumentReader(Protocol):
    def get_number_of_documents(self) -> int: ...
    def read_all_documents(self) -> Iterator[Any]: ...
    def get_reader_details(self) -> dict: ...          # per-source "reader" block for the manifest

class DocumentConverter(Protocol):
    def convert(self, doc: Any) -> Iterator[ConvertedDocument]: ...

class BaseConnector(Protocol):
    @property
    def reader(self) -> DocumentReader: ...
    @property
    def converter(self) -> DocumentConverter: ...
    @property
    def connector_type(self) -> str: ...
    @classmethod
    def from_config(cls, config_service) -> "BaseConnector": ...
    @classmethod
    def from_manifest(cls, manifest, config_service, *, storage_path) -> ConnectorRun: ...
```

The protocols declare exactly what the engine calls — a connector missing a method is a
**ty error**, not a runtime `AttributeError`. Reader fetches raw documents; Converter
transforms them into searchable chunks (text + metadata) via the parsing module.
`from_manifest` rebuilds `(reader, converter, deletions, post_run)` (a `ConnectorRun`) for
an incremental update from the collection's own manifest, so **core's update path is
source-agnostic** — one call for every connector, no per-type / `localFiles` branch.

---

## Implemented Connectors

| Connector | Location | Protocol | Auth |
|-----------|----------|----------|------|
| **FileSystemConnector** | `.../connectors/files/` | Local FS | None |
| **JiraCloudConnector** | `.../connectors/jira/` | REST API | Email + Token |
| **JiraServerConnector** | `.../connectors/jira/` | REST API | Email + Token |
| **ConfluenceCloudConnector** | `.../connectors/confluence/` | REST API | Email + Token |
| **ConfluenceServerConnector** | `.../connectors/confluence/` | REST API | Email + Token |
| **OutlineConnector** | `.../connectors/outline/` | REST API | Bearer token |

(All paths under `src/indexed/connectors/`.)

### Files Traversal — Storage Root Is Never Source Content

A files collection must never index indexed's own storage. Both modes live in a
directory named `.indexed` — `./.indexed` (local) and `~/.indexed` (global) —
holding `config.toml`, `.env`, `data/collections/*` and caches. Two layers
enforce that in `connectors/files/`:

- **Name rule:** `.indexed` is in `DEFAULT_EXCLUDED_DIRS`
  (`schema.py`), pruned during traversal before descending, independent of
  `.gitignore` and `include_patterns`, and for nested workspaces too.
- **Path rule:** `FilesDocumentReader` guards the *resolved* storage roots
  (`default_storage_roots()` → `<base>/.indexed` and `~/.indexed`) and prunes
  any directory equal to or inside one, plus explicit `specific_files` passed by
  an incremental update. This holds even when `excluded_dirs` is overridden
  without `.indexed`.

Consequences, deliberate:

- A workspace's `.indexed/` is **reserved**; it cannot be re-enabled as source.
- A *nested* directory literally named `.indexed` is skipped by the name rule
  and can only be re-enabled by an explicit `excluded_dirs` list that omits it.
- Pointing `--path` *inside* a storage root is an explicit request: a root that
  contains the scan base is dropped from the guard, so such a scan still works.

Why it matters beyond tidiness: `.indexed/.gitignore` is untracked, so without
the guard `search --changed-since <ref>` reported the collection's own storage
file as changed (issue #279 follow-up). Collections created before the fix keep
the stale document until a re-create (`--force`) or the next `update`, which
drops it as a deletion via change tracking.

---

## Credential Security — Origin Guard

**File:** `src/indexed/connectors/_url_guard.py`

All credentialed attachment fetchers (Jira Server/DC, Confluence Server, Outline) call
`warn_if_off_origin(url, base_url)` before issuing any HTTP request. This function
compares scheme + hostname + **effective port** (missing ports normalized to the
scheme default — 443 for HTTPS, 80 for HTTP — so a base URL without an explicit port
still matches a default-port attachment, while a non-default port like `:8443` is a
different origin), logs a warning, and returns `False` on mismatch so the caller can
`return None` without crashing the indexing run.

```python
from connectors._url_guard import warn_if_off_origin

if not warn_if_off_origin(url, self.base_url):
    return None   # skip silently after logging warning
```

`is_same_origin(url, base_url)` is the primitive (bool only, no side effects).
`warn_if_off_origin` wraps it with logging and is the one to use in readers.

`is_cloud_host(url)` (same module) is the Cloud-vs-Server discriminator: it parses
the host **before** the `*.atlassian.net` suffix check, so a raw-URL substring like
`https://evil.com/x.atlassian.net` is not misread as Cloud (incomplete URL-substring
sanitization). The Jira/Confluence Cloud readers use it instead of a bare
`base_url.endswith(".atlassian.net")`.

**Exclusions:** `AsyncJiraCloudDocumentReader` — Jira Cloud serves attachment content
from `api.media.atlassian.com` (off-origin by design, URLs from Jira's own API, not
attacker-controlled). `AsyncConfluenceCloudDocumentReader` — constructs URLs as
`f"{self.base_url}/wiki{path}"` (always same-origin by construction; guard unnecessary).

---

## Files Reader Block — Persisted Keys

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
`CodeChunker` (see [tech-parsing.md](tech-parsing.md)).

---

## Change Tracking

`FileSystemConnector` supports incremental indexing via `ChangeTracker`:

| Strategy | Detection |
|----------|-----------|
| **git** | `git diff --name-status` between commits |
| **content-hash** | xxhash of contents vs stored state |
| **mtime** | modification time (faster, less reliable) |
| **auto** | git if `.git` exists, else content-hash |

State persisted as `state.json`, updated after each successful run.

**Correctness:** the git strategy is **content-hash-authoritative** — it reconciles
the diff against stored content hashes, so a file edited and then **reverted back to
its committed state** is still re-indexed (a name-status diff alone would miss it).
Git **C-quoted non-ASCII paths** (`"\303\244…"`) are unquoted to real filenames
before tracking.

---

## Query-Time Git Helper (`utils/git_meta.py`)

Indexing is not the only consumer of git: `search --changed-since` and
`--git-provenance` ask the *query* side the same questions. The shared helper lives in
`src/indexed/utils/git_meta.py` — `utils` is the only layer both `core` and
`connectors` may import (a connector-local helper would break the import edges).

- Stdlib `subprocess` only, every call a list argv with `timeout=5`, a checked return
  code, and **all** exceptions swallowed to `None`/empty: a git problem must never
  break a search. The child env strips leaked `GIT_DIR`/`GIT_WORK_TREE`/`GIT_INDEX_FILE`/
  `GIT_OBJECT_DIRECTORY`/`GIT_CEILING_DIRECTORIES` and pins `GIT_TERMINAL_PROMPT=0`,
  `LC_ALL=C` — the same hygiene as `change_tracker.py`.
- `repo_toplevel` / `is_git_repo` — `git rev-parse --show-toplevel`.
- `changed_paths(repo, ref)` — union of `git diff --name-only <ref> --` (REF's tree vs
  the **working tree**, so committed, staged and unstaged changes all count) and
  `git ls-files --others --exclude-standard` for untracked work. Two legs: a plain
  `git diff` and a `--cached` diff add nothing this one call does not already see. NUL-delimited paths preserve whitespace and newlines.
  An invalid ref returns `None` (verified up front via
  `rev-parse --verify <ref>^{commit}`) — a typo must never look like "nothing changed".
- `head_commit` / `commit_exists` / `is_ancestor` / `is_shallow_repository` /
  `commit_count` / `is_detached_head` — the freshness facts behind
  `utils/freshness.py` (#146 slice 1): the HEAD SHA, whether the indexed commit still
  exists and is an ancestor of HEAD, a real `rev-list --count`, and detached-HEAD
  detection. These need `_run_code`, because `merge-base --is-ancestor` answers "no"
  with exit 1 — folding that into `None` like `_run` does would turn "git says no" into
  "git is broken", and `unknown`/`history-rewritten` must stay distinguishable.
- `ignored_paths` — `git ls-files --others --ignored --exclude-standard`. `git status`
  never reports an ignored file, so one that was indexed and only later ignored would
  otherwise read `fresh` forever.
- `last_commit(repo, path)` — ONE `git log -1 --format=…` per file, giving
  `{commit, short, author, email, committedAt, subject}`. `committedAt` is the committer time; author time remains the blame recency signal. Line blame is an independent opt-in.
- `snapshot_is_current(base_path, source_id, modified_time, indexed_at=None)` — compares
  a node's indexed `modified_time` with the file's mtime now (`os.path` + `stat`, no
  subprocess). The stored value is offset-aware UTC, so the comparison is
  zone-independent; an offset-less (legacy) value is judged instead against the
  manifest's `updatedTime`, which is zone-free. `last_commit` answers for the file as it
  is on disk, so retrieval attaches provenance only while this says the indexed
  snapshot still describes it.
- `blame_lines(repo, path)` — ONE `git blame --line-porcelain` per file, parsed into
  one record per line (`commit`/`short`/`author`/`email`/`committedAt`/`subject` plus
  the sort-only author epoch). `None` when blame cannot answer: untracked path,
  non-repo, binary file (a NUL in git's own 8 kB sniff window — plain blame would
  return a binary blob as one meaningless "line"), or any git failure. Callers memoize
  by `(repo, path)` within a search, so a document's chunks share one call.
- `resolve_range(lines, start_line, end_line)` — pure mapping from a 0-based inclusive
  span to its newest touching commit (`startLine`/`endLine` are reported 1-based, as
  git counts). A span with any working-tree line returns
  `{"uncommitted": true, "startLine", "endLine"}` — never the committed ancestor
  dressed up as line-level provenance — and a gap or out-of-range span returns `None`.
- `repo_relative(repo, base_path, source_id)` — document ids are base-path-relative
  (`v1_adapter.py:35-36`), git pathspecs are repo-relative; this rebases with `os.path`
  arithmetic only (no symlink resolution, no filesystem probe).
- **No global cache.** Callers memoize per search call, so a long-lived MCP server
  cannot serve stale git facts.

Active configured storage roots are excluded from file traversal and explicit incremental files. When the storage root equals the source root, only its `data` directory is excluded.

File inventory traversal fails on filesystem errors or a replaced source root; it never classifies an incomplete inventory as deletions.
