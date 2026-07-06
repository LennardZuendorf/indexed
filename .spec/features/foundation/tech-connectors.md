---
type: feature-tech
feature: foundation
sibling: product.md
parent: ../../tech.md
updated: 2026-07-06
---

# Feature: Foundation — Connector Architecture & Fidelity

How the connector layer is corrected in the current 7-package tree: the
reader/converter/`BaseConnector` protocols are aligned with what the engine
actually calls, each connector gains a `from_manifest(...)` that owns its own
manifest keys (deleting the app-layer per-connector wiring, the private-attribute
reaches, and the `os.environ` side-channel), and every audited connector-fidelity
defect (R6) is fixed at its cited line. No package is deleted or renamed here —
that is Feature `simplify`.

**Overview:** [tech.md](tech.md)
**Requirements:** [product.md](product.md)

Scope map:
- R6 fidelity fixes → **foundation/5** (attachments, change-tracker, ADF/storage
  converters, `_url_guard`).
- `from_manifest` seam + dropping `connector_wiring.py`'s per-connector blocks →
  **foundation/8** (facade + composition). The empty-query JQL/CQL fix moves into
  `from_manifest` there.
- Corrected `protocols.py` (`DocumentReader`/`DocumentConverter`/`BaseConnector`) →
  **foundation/7** (typed contracts).

---

## Files

```
packages/indexed-connectors/src/connectors/
  registry.py                              CONNECTOR_REGISTRY + NAMESPACE_REGISTRY (keep); dead APIs deleted in simplify
  _url_guard.py                            off-origin credential guard — parser-differential fix (R6)
  files/
    connector.py                           FileSystemConnector — gains from_manifest(); absorbs the update factory
    files_document_reader.py               unchanged (reader restricted via specific_files)
    change_tracker.py                      stored-hash comparison + git C-quote unquoting (R6)
    v1_adapter.py                          unchanged
  jira/
    connector.py                           Jira{,Cloud}Connector — gain from_manifest()
    async_jira_cloud_reader.py             follow_redirects + no raise-on-3xx for attachments (R6)
    unified_jira_document_reader.py         Server reader; requests already follows redirects (guard on Server only)
    unified_jira_document_converter.py      ADF leaf-node text extraction + list-item join (R6)
  confluence/
    connector.py                           Confluence{,Cloud}Connector — gain from_manifest()
    async_confluence_cloud_reader.py        follow_redirects + no raise-on-3xx for attachments (R6)
    unified_confluence_document_converter.py ac:link / ac:image title + filename text (R6)
    confluence_cloud_document_reader.py      DEAD sync reader — DELETED in Feature simplify, do not build on it
  outline/
    connector.py                           OutlineConnector — gains from_manifest() (kills os.environ cutoff)
    outline_document_reader.py             reference for correct follow_redirects=True

apps/indexed/src/indexed/
  connector_wiring.py                      DELETED by from_manifest: _populate_* blocks, private reaches, os.environ side-channel
```

The corrected engine-facing protocols live in `packages/indexed-protocols/src/protocols/connectors.py` (foundation/7).

---

## Contract / API

### Corrected engine-facing protocols

Today `protocols/connectors.py:12-26` declares `DocumentReader.read_documents()`
and `DocumentConverter.convert(doc)` — but **zero callers use `read_documents`**;
the engine calls `get_number_of_documents()` / `read_all_documents()` /
`get_reader_details()` on the reader (see `documents_collection_creator.py:202,225,500`)
and `convert(doc)` on the converter. The protocol is aligned to reality so a
mismatch is a mypy error rather than an `Any`-typed runtime surprise:

```python
# protocols/connectors.py  (after — foundation/7)
@runtime_checkable
class DocumentReader(Protocol):
    def get_number_of_documents(self) -> int: ...
    def read_all_documents(self) -> Iterator[Any]: ...
    def get_reader_details(self) -> dict: ...

@runtime_checkable
class DocumentConverter(Protocol):
    def convert(self, doc: Any) -> Iterator[ConvertedDocument] | list[dict]: ...
```

Every reader already implements this triple (files `:135,124,140`; unified jira
`:266,197,287`; async jira `:90,83,94`; async confluence `:96,73,108`; outline
`:128,110,147`) — the change is only the declaration, so no reader body moves.

### New `from_manifest` on each connector

`BaseConnector` keeps `reader` / `converter` / `connector_type` / `from_config`
and **gains a classmethod** that builds the reader+converter for an *incremental
update* from a stored manifest, owning its own camelCase keys and its own cutoff
logic:

```python
# protocols/connectors.py  (added — foundation/8)
class ConnectorRun(NamedTuple):
    reader: DocumentReader
    converter: DocumentConverter
    deletions: list[str]            # document IDs to remove (files only today)
    post_run: Callable[[], None] | None   # e.g. save change-tracker state

class BaseConnector(Protocol):
    ...
    @classmethod
    def from_manifest(
        cls, manifest: Manifest, config: SourceConfig, *, storage_path: str
    ) -> ConnectorRun: ...
```

Core's update loop then treats every source identically:

```python
# core update path (after) — replaces update_collection_factory.py:87 localFiles branch
run = CONNECTOR_REGISTRY[manifest.reader.type].from_manifest(
    manifest, config, storage_path=collection_full_path
)
# use run.reader / run.converter to re-index, run.deletions to prune,
# then run.post_run() after a successful persist.
```

This **deletes** the entire app-layer wiring apparatus in
`apps/indexed/src/indexed/connector_wiring.py`:

| Deleted today | Replaced by |
|---|---|
| `_populate_jira_config` / `_populate_confluence_config` / `_populate_outline_config` / `_populate_local_files_config` (`:43-121`) writing manifest values back through `ConfigService.set` | each connector's `from_manifest` reading `manifest.reader.*` directly (no config write — supports R3 read-mostly config) |
| `populate_config_from_manifest` per-connector `if/elif` (`:134-145`) | `CONNECTOR_REGISTRY[type].from_manifest` dispatch |
| `_connector_reader_converter_from_manifest` `os.environ[_OUTLINE_MODIFIED_SINCE_ENV] = ...` side-channel (`:154-171`, env key `:16`) | `OutlineConnector.from_manifest` passes `modified_since=` straight to `OutlineDocumentReader(...)` (constructor already accepts it, `outline_document_reader.py:78`) |
| `make_local_files_update_factory` reaching into `connector._config` / `connector._path` / `connector._include_patterns` (`:227-231`) | `FileSystemConnector.from_manifest` — same-class access, no private reach across the layer boundary |
| `make_manifest_connector_factory` / `make_local_files_update_factory` / `wiring_kwargs_for_update` | one `from_manifest` call in `cli/composition.py` |

Two injected callables remain at the facade (create-time and update-time
connector construction), both **required** — the `Callable | None` +
`missing_wiring_error` guards go away (foundation/8; see
[tech-core.md](tech-core.md)).

### `Manifest.reader` typing note

`from_manifest` receives a typed `Manifest` (foundation/7), so `manifest["reader"]["type"]`
string-indexing becomes `manifest.reader.type`. `reader` is `ReaderDetails` with
`extra="allow"` so per-source camelCase fields (`baseUrl`, `basePath`, `query`,
`includePatterns`, `collectionIds`, …) survive round-trip byte-stable.

---

## Implementation Detail

### R6.1 — Attachments must follow redirects and not raise on 3xx

Atlassian Cloud serves attachment bytes from a 302 redirect to a media/S3 CDN.
Two async readers create their download client **without** `follow_redirects` and
then call `raise_for_status()`, which raises on the 302 → **every** Cloud
attachment is silently dropped.

**Jira Cloud** — `async_jira_cloud_reader.py`. Client at `:185`, download +
`raise_for_status()` at `:227,234`:

```python
# before (:185)
async with httpx.AsyncClient(
    timeout=60.0,
    limits=httpx.Limits(max_connections=self.max_concurrent_requests,
                        max_keepalive_connections=5),
) as client:
    ...
# before (:227)
    response = await client.get(url, headers={...})
    response.raise_for_status()          # raises on the 302 to the CDN
```

```python
# after
async with httpx.AsyncClient(
    timeout=60.0,
    follow_redirects=True,               # (1) follow the CDN redirect
    limits=httpx.Limits(max_connections=self.max_concurrent_requests,
                        max_keepalive_connections=5),
) as client:
    ...
    response = await client.get(url, headers={...})
    if response.is_error:                # (2) 4xx/5xx only — 3xx already followed
        logger.warning(...); return None
    return response.content
```

Note the Jira Cloud download deliberately does **not** run `_url_guard`
(`:203,227`) — the redirect target is a legitimate off-origin CDN. This is the
"selectively excluded" case flagged in the root AGENTS.md learning; keep it
excluded. The **Server** reader (`unified_jira_document_reader.py:259`) uses
`requests.get`, which follows redirects by default, and correctly keeps the
origin guard at `:243` (Server attachments are same-origin).

**Confluence Cloud** — `async_confluence_cloud_reader.py`. The *comment/list*
client at `:182` is fine (JSON, no redirect), but the **attachment** client at
`:276-283` lacks `follow_redirects` and the download at `:344-345` raises on 3xx:

```python
# before (:276)
async with httpx.AsyncClient(
    auth=(self.email, self.api_token),
    timeout=60.0,
    limits=httpx.Limits(max_connections=self.max_concurrent_requests,
                        max_keepalive_connections=5),
) as client:
    ...
# before (:344)
    resp = await client.get(download_url)
    resp.raise_for_status()
```

```python
# after (:276)
async with httpx.AsyncClient(
    auth=(self.email, self.api_token),
    timeout=60.0,
    follow_redirects=True,
    limits=httpx.Limits(max_connections=self.max_concurrent_requests,
                        max_keepalive_connections=5),
) as client:
    ...
    resp = await client.get(download_url)
    if resp.is_error:
        logger.warning(...); continue
```

Reference implementation that already does this right: the Outline reader sets
`follow_redirects=True` on its attachment client (`outline_document_reader.py:292`),
which is why Outline attachments work today.

### R6.2 — git change-tracker misses reverted edits and non-ASCII paths

Two independent defects in `change_tracker.py` `_git_changes` (`:141-220`).

**(a) Reverted working-tree edits are never re-indexed.** The git strategy
derives changes purely from `git diff last_commit..HEAD` (`:167`) merged with
`git status --porcelain` (`:190`). If a file was edited, indexed, then reverted
back to its committed content, HEAD is unchanged, working tree is clean → git
reports nothing, but the *indexed* content is the edited version. The tracker
stores per-file hashes in `state.file_hashes` (`build_state` `:71-93`) yet
**never compares them** in the git path — they are used only to detect deletions
(`:215-219`). Fix: after computing the git-derived `merged` dict, reconcile
against stored hashes for files present in the current walk:

```python
# after — add before the final return (~:219)
if state.file_hashes:
    import xxhash
    for rel in current_rel:
        if rel in merged:
            continue                      # git already classified it
        old = state.file_hashes.get(rel)
        if old is None:
            merged[rel] = "added"
            continue
        fp = os.path.join(self._base_path, rel)   # or git_toplevel-relative
        try:
            new = xxhash.xxh64(Path(fp).read_bytes()).hexdigest()
        except OSError:
            continue
        if old != new:                    # catches reverted-to-committed edits
            merged[rel] = "modified"
```

This makes the git strategy hash-authoritative for content (the content-hash and
mtime strategies at `:320-391` already compare stored hashes correctly — only the
git strategy trusted git alone).

**(b) C-quoted non-ASCII filenames are never unquoted.** When a path contains
non-ASCII bytes or specials, git wraps the whole field in double quotes and
C-escapes it (e.g. `"src/caf\303\251.md"`). Both parsers take the raw field:
`_parse_diff_name_status` splits on `\t` and passes `parts[1]`/`parts[2]` straight
into `_git_path_to_rel` (`:248-270`); `_parse_status_porcelain` takes `line[3:].strip()`
(`:288`). The quoted/escaped path never matches a real file in `current_rel`, so
those files are dropped from the change set forever. Fix: unquote before path
resolution.

```python
# after — new helper, applied to every git path field
@staticmethod
def _git_unquote(path: str) -> str:
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        # git C-quotes with octal escapes on a bytes stream
        return path[1:-1].encode("latin-1").decode("unicode_escape") \
            .encode("latin-1").decode("utf-8", "replace")
    return path
# _parse_diff_name_status: rel = self._git_path_to_rel(self._git_unquote(parts[1]), ...)
# _parse_status_porcelain: git_path = self._git_unquote(line[3:].strip())
```

(Alternatively run git with `-c core.quotePath=false`; the in-code unquote is
preferred so behavior is independent of the caller's git config.) Renames in
porcelain (`old -> new`, `:291`) must unquote each half independently.

### R6.3 — ADF leaf nodes dropped from Jira text

`unified_jira_document_converter.py:122-190` (`_parse_adf_nodes`) walks ADF but
only emits `text` nodes and recurses on nodes with a `content` array (`:181-186`).
ADF **leaf** nodes carry their payload in `attrs`, not `content`, so they yield
nothing: `mention` (assignee/reporter names), `inlineCard` / `blockCard` (link
URLs), `media` (attachment filename), `emoji`, `date`, `status`. Assignees and
every linked URL vanish from the indexed text. Add explicit leaf handling before
the generic `elif "content" in node` fallthrough:

```python
# after — add cases inside the node-type dispatch (~:178)
elif node_type == "mention":
    texts.append(node.get("attrs", {}).get("text", ""))          # "@Jane Doe"
elif node_type in ("inlineCard", "blockCard"):
    texts.append(node.get("attrs", {}).get("url", ""))           # the link target
elif node_type == "media":
    a = node.get("attrs", {})
    texts.append(a.get("alt") or a.get("id", ""))                # filename/alt
elif node_type == "emoji":
    a = node.get("attrs", {})
    texts.append(a.get("text") or a.get("shortName", ""))
elif node_type in ("date", "status"):
    a = node.get("attrs", {})
    texts.append(a.get("text") or a.get("timestamp", ""))
```

**List-item join bug.** `listItem` (`:151-157`) renders `- {item_text}` and
`bulletList`/`orderedList` (`:144-149`) collect items, but because non-block
recursion returns `"".join(texts)` (`:188-189`) sibling list items are concatenated
with no separator — two bullets become one run-on line. Fix: join list-level
children with `\n` so each `- item` stays on its own line:

```python
# after — in the bulletList/orderedList branch
list_items = "\n".join(
    t for t in (self._parse_adf_node(n, depth + 1) for n in node.get("content", [])) if t
)
```

(Leaf handling and the list join are the two edits; the surrounding block-vs-inline
return contract at `:188-190` is otherwise preserved.)

### R6.4 — Confluence storage-format drops ac:link / ac:image text

`unified_confluence_document_converter.py:119-125` (`_get_cleaned_body`) runs the
storage-format HTML through `BeautifulSoup(...).get_text()`. Confluence storage
XML puts link titles and image filenames in **attributes** of custom `ac:`/`ri:`
tags (`<ac:link><ri:page ri:content-title="Design Doc"/></ac:link>`,
`<ac:image><ri:attachment ri:filename="diagram.png"/></ac:image>`), which
`get_text()` ignores because they hold no element text → link targets and image
filenames are lost. Pre-process the soup to inject that attribute text before
extraction:

```python
# after — inside _get_cleaned_body, before soup.get_text(...)
for ri in soup.find_all(["ri:page", "ri:attachment", "ri:blog-post"]):
    title = ri.get("ri:content-title") or ri.get("ri:filename")
    if title:
        ri.insert_after(soup.new_string(f" {title} "))
```

This keeps `get_text(separator=os.linesep, strip=True)` (`:125`) as the extraction
path — only the attribute-bearing custom tags are materialized into text first.

### R6.5 — empty stored query yields malformed leading-AND JQL/CQL

Today in `connector_wiring.py:49,62`, the incremental date filter is appended as
`f"{reader_config['query']} {query_addition}"` where `query_addition` **starts
with `AND (...)`**. When the stored base query is empty, this produces a leading
`AND (...)` → invalid JQL/CQL and a failed update. After the refactor this lives
in each connector's `from_manifest`; guard the join:

```python
# after — in Jira/Confluence from_manifest
date_filter = f'(created >= "{d}" OR updated >= "{d}")'      # Jira
base = (manifest.reader.query or "").strip()
query = f"{base} AND {date_filter}" if base else date_filter
```

(Confluence uses `lastModified` in place of the second `updated`, matching the
old `_populate_confluence_config` at `:62`.) The `update_date` derivation stays
`lastModifiedDocumentTime - 1 day` (`_calculate_update_time`, `:33-40`).

### R6.6 — `_url_guard` parser differential (also a secret-leak, foundation/4)

`_url_guard.is_same_origin` (`_url_guard.py:42-64`) parses the target with
`urllib.parse.urlsplit`, but the actual fetch uses `requests`/urllib3, which
parse the authority differently. For `https://evil.com\@good.com/…`, `urlsplit`
reads the host as `good.com` (backslash not a delimiter in RFC 3986) and
**approves** the request, while urllib3 treats `\` as a path/authority separator
and sends the credentialed request to `evil.com` — the Bearer/basic creds leak to
the attacker host. Reproduced (research item 12). Fix: parse the authority the way
the HTTP client does, or strip credentials whenever off-origin.

```python
# after — normalize the authority the client's way before comparison
def _client_host(url: str) -> str | None:
    # urllib3 splits authority on the first of  / ? # \  after scheme://
    from urllib.parse import urlsplit
    rest = url.split("://", 1)[-1]
    authority = re.split(r"[/?#\\]", rest, maxsplit=1)[0]   # note: backslash included
    host = authority.rsplit("@", 1)[-1].split(":", 1)[0]
    return host.rstrip(".").lower() or None                # (b) drop trailing FQDN dot
```

`is_same_origin` compares `_client_host(url)` to `_client_host(base_url)` plus the
existing scheme + `_effective_port` checks (`:60-63`, keep). Two behaviors this
also fixes:
- **(a)** the `\@` differential above — `_client_host` sees `evil.com`, so the
  guard fails closed and `warn_if_off_origin` (`:6-19`) refuses to send creds.
- **(b)** legitimate trailing-dot FQDNs (`good.com.`) are no longer rejected — the
  dot is stripped so `good.com.` and `good.com` compare equal (the `urlsplit`
  hostname path at `:57-63` rejected them today).

Belt-and-suspenders: even when same-origin, off-origin *redirect* targets are
guarded by the readers not embedding creds on the redirected hop (the Jira Cloud
exclusion in R6.1). `is_same_origin` remains exported for tests.

---

## Already-correct — do NOT re-chase (Cleared)

From the audit's Cleared list — connector behaviors verified correct, so no work:

- **Cloud document IDs don't collide.** Jira uses `document["key"]`
  (`unified_jira_document_converter.py:65`), Confluence uses `page["id"]`
  (`unified_confluence_document_converter.py:83`), Outline uses the document UUID —
  distinct namespaces, no cross-source ID collision within a collection.
- **Single-connector collections can't mix naive/aware datetimes.** A collection
  is built by exactly one connector, so all `modifiedTime` values share one source's
  tz convention — no naive-vs-aware comparison crash. Do not add tz-coercion.
- **ADF tables and panels are preserved.** `table`/`tableRow`/`tableCell`/`panel`
  carry a `content` array and flow through the generic `elif "content" in node`
  recursion (`unified_jira_document_converter.py:181-186`) — their text survives.
  Only the *leaf* attrs-bearing nodes (R6.3) were dropped.

## Dead code — do not build on it

`confluence/confluence_cloud_document_reader.py` (the **sync** Confluence Cloud
reader, ~293 LOC) is never instantiated — `ConfluenceCloudConnector` uses the async
reader (`connector.py:299`), which only borrows a couple of static helpers from it
(`build_page_query`, `parse_url_params`; `async_confluence_cloud_reader.py:13-16`).
It is on the **Feature `simplify`** delete-list. When wiring `from_manifest` for
Confluence Cloud (foundation/8) or fixing the async reader (R6.1), do not extend
or depend further on the sync reader; if the two shared static helpers matter, plan
to relocate them onto the async reader so `simplify` can delete the sync file
cleanly.
