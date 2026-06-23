---
type: feature-tech
feature: blame-ownership
sibling: product.md
parent: ../../tech.md
updated: 2026-06-23
---

# Feature: Blame & Ownership — Architecture

Read-only formatting layer over the git metadata persisted by the
git-metadata-enrichment feature. The searcher already returns git fields on
matched chunks (in chunk metadata + `index_document_mapping.json`); this feature
adds a small ownership helper, wires it into the existing formatters, adds the
`who_owns` MCP tool, and adds a CLI ownership view. No engine or persistence
changes.

**Parent:** [../../tech.md](../../tech.md)
**Requirements:** [product.md](product.md)
**Plan:** [plan.md](plan.md)

---

## Files

| File | Change |
|------|--------|
| `apps/indexed/src/indexed/knowledge/ownership.py` | New — pure `Ownership` model + `build_ownership(git_fields)` aggregator; shared by CLI + MCP |
| `apps/indexed/src/indexed/mcp/formatting.py` | Add `ownership` block to each chunk in `format_search_results_for_llm` |
| `apps/indexed/src/indexed/mcp/tools.py` | Register `who_owns` tool (reuses `svc_search` / `ConfigService`) |
| `apps/indexed/src/indexed/knowledge/commands/search.py` | Add ownership rows to the meta card + compact line |
| `apps/indexed/src/indexed/knowledge/commands/inspect.py` | Add ownership view (aggregate contributors) |
| `tests/unit/indexed/` | Unit tests mirroring the touched modules |

Git fields are read from the existing chunk dict under `matchedChunks` (and the
document JSON) — no new on-disk format. Keep each command file ≤150 lines;
ownership aggregation lives in `ownership.py`, not in the commands.

## Contract / API

```python
# apps/indexed/src/indexed/knowledge/ownership.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Contributor:
    author: str
    commit_count: int

@dataclass(frozen=True)
class Ownership:
    last_author: str | None
    last_committed_date: str | None
    commit_count: int
    contributors: tuple[Contributor, ...]   # ranked, descending by commit_count
    has_git_metadata: bool

def build_ownership(git_fields: dict | None) -> Ownership:
    """Aggregate persisted git fields into a display model.
    Returns Ownership(has_git_metadata=False, ...) when git_fields is empty."""

def ownership_to_dict(o: Ownership) -> dict:
    """Serialize for JSON / MCP output."""
```

```python
# apps/indexed/src/indexed/mcp/tools.py  (registered inside register_tools)
@mcp.tool
def who_owns(target: str, ctx: Optional[Context] = None) -> Dict[str, Any]:
    """Return owners + contributing commits for a file path or code symbol.
    Resolves `target` via the existing search service, aggregates git fields
    across matched chunks, returns {target, owners, contributing_commits,
    has_git_metadata} or a structured empty result."""
```

## Implementation Detail

- **Aggregation:** `build_ownership` reads `last_author`, `last_committed_date`,
  `commit_count`, and `touching_commits` from a chunk's git fields, tallies a
  per-author commit count from `touching_commits`, and sorts contributors
  descending. Missing/empty fields → `has_git_metadata=False`.
- **`who_owns` resolution:** a path-shaped target is matched against
  `documentPath`; otherwise the string is run through `svc_search` as a symbol
  query. Matched chunks' git fields are merged via `build_ownership`, and
  `contributing_commits` is the de-duplicated union of `touching_commits`. The
  tool reuses `_resolve_config` + `svc_search` exactly like `search`, and wraps
  failures as `{"error": str(e)}` per the existing MCP error pattern.
- **CLI display:** ownership rows are appended to the existing meta card via the
  Rich teal-accent components in `search.py`; the inspect ownership view builds a
  `create_detail_card` of top contributors. Degraded state renders a single dim
  "no git metadata" row.
- **Lazy imports:** no new heavy ML imports; `ownership.py` is pure-Python and
  import-safe at module top.

## Open Questions

1. Symbol resolution precision — does a plain `svc_search` query suffice, or
   should `who_owns` filter to exact symbol-name matches in chunk metadata?
2. Should the ownership view be a flag on `index inspect` or its own subcommand?
   Defaulting to an `inspect` extension to avoid a new command file.
