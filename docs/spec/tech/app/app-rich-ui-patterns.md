---
type: tech
updated: 2026-11-22
applies: "src/indexed/cli/**"
---

# Rich UI Patterns

All terminal output via `rich`:

- **Info cards** — `Panel`-based cards for search results / object summaries
- **Status indicators** — colored icons (`✓`, `✗`, `!`)
- **Progress** — spinner + bar for long-running indexing

## Theme

- **Accent:** teal (`#00D4AA`) for commands/highlights
- **Secondary:** dim/grey for metadata

## Markup safety

User-supplied query text and indexed content are **Rich-escaped**
(`rich.markup.escape` / `Text`) before display — never build markup from
untrusted content. A `[/...]` or `arr[i]` in a query or document must render
literally, never raise `MarkupError` and never silently drop the text.

The same parser also runs over **static option help text** — a bracketed
`[dotted.config.key]` inside a `typer.Option(help=...)` string is parsed as a
style tag and silently dropped from rendered `--help` output (no error, no
warning). Never write a bracketed config key in a `help=` string; write it
unbracketed (`core.v1.search.max_docs`, not `[core.v1.search.max_docs]`) as
`--limit` and `--rerank` both do. A test asserting a `--help` string names a
config key must assert the key text itself appears in rendered output, not
just that the flag exists.

## Narrow terminals

Panels wrap at the live terminal width (60–120 chars). A **failure message is
not one paragraph**: a long path followed by the actionable reason folds the
reason mid-phrase at 80 columns, which is exactly the case a user has to act
on — the reason stops being readable and stops being greppable. Render the
failure as a short static headline in the panel plus one detail line per fact
(`_print_path` uses `soft_wrap=True`, so the path and the reason stay on one
line and stay copyable). The installer's unreadable-config path carries its
parts on a `ConfigFileError` rather than in one flat string (#357).
