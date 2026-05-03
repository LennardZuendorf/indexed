# Outline Wiki Connector — Product Spec

**Status:** Proposed
**Author:** Engineering
**Date:** 2026-05-01

---

## Problem & Users

Teams that run [Outline](https://www.getoutline.com/) as their primary knowledge base (either on Outline Cloud or self-hosted) cannot currently surface that content through `indexed`. Their wiki pages remain invisible to `indexed search` and to AI agents using the MCP server, even though the same teams may already have their Jira issues and Confluence pages indexed.

**Target users:**
- Engineers and PMs who want semantic search across all company knowledge in one place.
- AI agents (Claude Desktop, Cursor, Cline) that need to retrieve context from Outline docs via the MCP `search` tool.
- Platform/DevOps teams running self-hosted Outline who want the same indexing capability without sending data to a third-party SaaS.

---

## Goals

1. **Full text indexing** — Index every published Outline document (title, body Markdown) into a searchable FAISS collection.
2. **Attachment / image indexing** — Download inline images and file attachments; run them through the same `ParsingModule` (Docling + OCR) used by the Files and Confluence connectors so their content is findable by text search.
3. **Cloud and self-hosted parity** — The connector works against `https://app.getoutline.com` (Cloud) and any self-hosted Outline instance without requiring different commands, separate connector types, or code forks.
4. **Efficient batching** — Page through the Outline API in configurable batches; fetch document bodies and attachments concurrently to keep end-to-end indexing time reasonable on large workspaces.
5. **Incremental refresh** — `indexed index update outline-wiki` re-reads only documents changed since the last run (via `updatedAt` filtering in `documents.list`).
6. **Consistent UX** — The CLI flow matches the existing Confluence/Jira experience: interactive prompts for missing fields, sensitive credentials stored in `.env`, non-sensitive config in `config.toml`.

## Non-Goals

- Writing back to Outline (create/update documents).
- Indexing Outline document _comments_ (Outline's comment feature is minimal; deferred to a follow-up).
- Real-time / webhook-driven sync (deferred; `indexed index update` covers the incremental case).
- Outline API write operations or admin functions.

---

## User Stories

### 1. Index an Outline Cloud workspace

```
$ indexed index create outline --collection company-wiki
Outline URL [https://app.getoutline.com]: ↵
Outline API Token: ••••••••••••••
✓ Collection 'company-wiki' created with 342 documents from Outline
```

### 2. Index a self-hosted Outline instance

```
$ indexed index create outline --collection internal-wiki
Outline URL [https://app.getoutline.com]: https://wiki.acme.internal
Outline API Token: ••••••••••••••
✓ Collection 'internal-wiki' created with 1,204 documents from Outline
```

The user experience is identical to Cloud; only the URL prompt answer differs.

### 3. Search Outline content via CLI

```
$ indexed index search "incident runbook pagerduty" --collection company-wiki
```

Results include Outline URLs, document titles, and the matching text passage.

### 4. AI agent searches Outline via MCP

An AI agent calling `search(query="deploy backend service", collection="company-wiki")` via the MCP server receives the most relevant Outline passages, including text extracted from embedded screenshots via OCR.

### 5. Restrict indexing to specific collections

```
$ indexed index create outline --collection eng-wiki --collection-id abc123,def456
```

Scopes indexing to the specified Outline collection IDs instead of the whole workspace.

### 6. Incremental update

```
$ indexed index update company-wiki
```

Re-fetches only documents with `updatedAt > last_indexed_at`, re-embeds changed chunks, and updates the FAISS index in place.

### 7. TOML-driven configuration (CI / automation)

```toml
# ~/.indexed/config.toml
[sources.outline]
url = "https://wiki.acme.internal"
collection_ids = ["abc123"]
include_attachments = true
```

```
$ export OUTLINE_API_TOKEN=ol_api_...
$ indexed index create outline --collection ops-wiki
```

---

## UX Details

### CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--url` / `-u` | prompted (default `https://app.getoutline.com`) | Outline base URL. Accepts any domain for self-hosted. |
| `--token` | prompted (env `OUTLINE_API_TOKEN`) | Outline API token (`ol_api_…`). Stored in `.env`. |
| `--collection-id` | (index all) | Comma-separated collection IDs to restrict indexing. |
| `--include-attachments / --no-include-attachments` | `True` | Download and OCR attachments and inline images. |
| `--ocr / --no-ocr` | `True` | Enable OCR on image attachments. |
| `--collection` / `-c` | `outline` | Name for the indexed collection. |
| `--force` | `False` | Overwrite an existing collection. |
| `--use-cache / --no-cache` | `True` | On-disk cache for unchanged documents. |
| `--local` | `False` | Store collection in `.indexed/` of the current directory. |

### Interactive prompt order

When fields are missing from config / env:

1. `Outline URL [https://app.getoutline.com]:` — Enter accepts Cloud; any URL is accepted for self-hosted.
2. `Outline API Token:` — masked input, stored in `.env` as `OUTLINE_API_TOKEN`.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `OUTLINE_API_TOKEN` | API token (takes precedence over `config.toml` value) |
| `INDEXED__sources__outline__url` | Override URL via environment |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Documents indexed correctly | ≥ 95% of published, non-archived docs |
| Indexing time (1,000-doc workspace) | < 2 minutes on warm cache |
| OCR hit rate for image attachments | ≥ 80% of image-only attachments yield searchable text |
| Search relevance (P@5) | Parity with Confluence connector on equivalent content |
| CLI startup time | < 1 second (lazy loading maintained) |
| Self-hosted parity | 100% — same binary, same flags, no separate connector type |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Self-hosted instances behind VPN / custom CAs | `verify_ssl: bool = True` field; ops can set `False` if needed. TLS verification is on by default. |
| Rate limiting (undocumented limits) | `execute_with_retry` with exponential backoff; configurable `batch_size` and `max_concurrent_requests`. |
| Signed attachment URLs expire during download | Download happens immediately after listing, within the same async window (< 60s TTL well within bounds). |
| Large workspaces (10k+ docs) | Streaming iterator pattern — no full in-memory load. `batch_size` defaults to 50, configurable up to 250. |
| Archived / draft documents indexed accidentally | `documents.list` defaults to `published` status filter; archived and draft docs are excluded. |
