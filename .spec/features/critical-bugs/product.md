---
type: feature-product
feature: critical-bugs
sibling: tech.md
parent: ../../product.md
updated: 2026-06-27
---

# Feature: Critical Bugs (non-core) — Product

A focused bundle of the highest-impact open bugs that can be fixed **without
touching `packages/indexed-core`**: two security defects in the connectors and
two CLI UX defects in the app. The bundle hardens credential handling against
data-driven SSRF / MITM and removes confusing, incorrect CLI output during
`index create` and `index search`. It deliberately excludes the MCP
stale-collection bug ([#112](https://github.com/LennardZuendorf/indexed/issues/112)),
whose fix lives in core (`InspectService`) and is already scoped into the
`file-watcher` branch.

**Parent:** [../../product.md](../../product.md)
**Architecture:** [tech.md](tech.md)
**Plan:** [plan.md](plan.md)

---

## Scope

| | |
|---|---|
| **Owns** | Attachment-fetch credential guarding in `connectors/jira`, `connectors/confluence`, `connectors/outline`; a shared origin-check helper in `connectors/`; the Outline `verify_ssl` warning; storage-indicator ordering in `apps/indexed/.../knowledge/commands/create.py` + `_create_helpers.py`; search status/progress copy in `apps/indexed/.../knowledge/commands/search.py`. |
| **Does not own** | `packages/indexed-core` (engine, services, factories, search/inspect) — **no edits**. MCP stale-collection refresh (#112, `file-watcher`). The Outline connector's TLS *transport* behaviour beyond the warning. Adding `verify_ssl` to Jira/Confluence (they have no such knob). Broader CLI output rework (#109). |

---

## Requirements

### Requirement: Attachment fetches MUST NOT leak credentials off-origin

The connectors SHALL NOT send authentication (Bearer token or Basic auth) to any
attachment URL whose origin (scheme + host) differs from the configured source
base URL. When an API-supplied attachment URL is off-origin, the system MUST skip
the download and emit a warning rather than issue a credentialed request.

#### Scenario: Off-origin attachment URL is refused

- **Given** a Jira/Confluence/Outline collection configured with base URL `https://acme.example.com`
- **When** the source API returns an attachment whose `content` URL points at `https://evil.attacker.test/x`
- **Then** no HTTP request carrying the user's credentials is made to `evil.attacker.test`, the attachment is skipped, and a warning naming the refused URL is logged

#### Scenario: Same-origin attachment URL still downloads

- **Given** the same collection configured with base URL `https://acme.example.com`
- **When** the API returns an attachment URL `https://acme.example.com/secure/attachment/123/file.pdf`
- **Then** the credentialed download proceeds exactly as before and the attachment bytes are returned

### Requirement: Disabling TLS verification MUST be loud

The Outline connector SHALL default to verifying TLS certificates. When a user
sets `verify_ssl=False`, the system MUST emit a prominent security warning on
every run that names the risk (API token exposed to MITM), so the insecure mode
is never silent.

#### Scenario: Insecure TLS triggers a warning

- **Given** an Outline collection configured with `verify_ssl=False`
- **When** the Outline reader is constructed for an index or update run
- **Then** a security warning stating that TLS verification is disabled and credentials may be exposed is logged

#### Scenario: Secure default stays quiet

- **Given** an Outline collection with `verify_ssl` left at its default
- **When** the reader is constructed
- **Then** no TLS warning is emitted and certificate verification is active

### Requirement: Storage indicator MUST precede the first prompt

During `index create`, the storage-mode indicator SHALL be the first thing
printed, before any connector-specific header or input prompt, so the user knows
where data will be written before answering any configuration question.

#### Scenario: Indicator prints before the Jira URL prompt

- **Given** a user runs `indexed index create jira` in a directory with a local `.indexed/`
- **When** the command starts and prompts for the Jira URL
- **Then** the storage-mode indicator line appears above the "Jira Configuration" header and the URL prompt, not below it

### Requirement: Search status messages MUST be accurate and non-redundant

The `index search` command SHALL NOT print a "Searching for … in 1 Collection:"
headline when a single collection is targeted with `-c`, and the per-collection
progress label MUST identify the collection by **name** (not by the search
query). Multi-collection search retains a summary headline.

#### Scenario: Single-collection search omits the redundant headline

- **Given** a user runs `indexed search -c outline "app rework scope"` (normal, non-simple output)
- **When** the search runs
- **Then** no `Searching for "…" in 1 Collection:` headline is printed, and the progress reads `Searching "outline" Collection for: "app rework scope"` — the collection name, not the query

#### Scenario: Multi-collection search keeps the summary headline

- **Given** a user runs `indexed search "app rework scope"` across 3 collections
- **When** the search runs
- **Then** a `Searching for "app rework scope" in 3 Collections:` headline is printed and each collection's progress label names that collection, never the query

---

## User Experience

Single-collection search (`-c outline`), normal output — before vs after:

```
# before (buggy)
Searching for "app rework scope" in 1 Collection:     ← redundant
Searching collection: app rework scope                 ← wrong: shows query
    ✓ Searching outline  7.4s ━━━━━━━━━━━━━━━━━━━━ 100%

# after
Searching "outline" Collection for: "app rework scope"
    ✓ Searching outline  7.4s ━━━━━━━━━━━━━━━━━━━━ 100%
```

`index create jira` — before vs after:

```
# before (buggy)
Jira Configuration

Jira URL: https://acme.atlassian.net
📁 Local storage (./.indexed) - local .indexed found     ← printed too late

# after
📁 Local storage (./.indexed) - local .indexed found

Jira Configuration

Jira URL: https://acme.atlassian.net
```

---

## Non-Goals

- Fixing the MCP stale-collection refresh (#112) — core-bound, owned by `file-watcher`.
- Adding a `verify_ssl` knob to Jira/Confluence (they correctly have none).
- Removing the Outline `verify_ssl` escape hatch (kept for self-signed self-hosted CAs).
- The broader human/agent search-output redesign tracked in #109.

---

## Open Questions

1. **#124 escape-hatch strength** — recommended: keep `verify_ssl=False` working
   but warn loudly every run (default `True`). Alternatives considered: require a
   second explicit env opt-in (e.g. `INDEXED_ALLOW_INSECURE_TLS=1`) or remove the
   knob entirely. The warning-only path keeps the fix connector-local (no core
   edit); the env-gate adds friction; removal would break self-signed self-hosts.
2. **#123 off-origin behaviour** — recommended: skip + warn (never send creds
   off-origin). Alternatives: fetch off-origin *without* credentials (gets public
   attachments, may silently miss auth-gated ones) or hard-error (most paranoid,
   risks breaking legit CDN-subdomain attachment hosts).
3. **#110 multi-collection layout** — recommended: keep the single summary
   headline and let each per-collection progress phase carry the
   `Searching "<name>" Collection for: "<query>"` label. The issue's mockup shows
   a separate header line *per* collection; that needs a second print inside the
   live progress block and is deferred unless requested.
