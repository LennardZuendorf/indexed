# indexed-parsing — Document & code parsing

> Scope: this package. Workflow, rules, and verify gate live in the root
> [`AGENTS.md`](../../AGENTS.md). Canonical design: [`.spec/tech-parsing.md`](../../.spec/tech-parsing.md).

## What this is

A reusable parsing module shared across connectors (Files, Confluence, Outline).
Routes each input to the right strategy and emits framework-free chunks. Heavy
parsers are **lazy-loaded** to keep CLI startup fast.

## Layer & dependencies

Shared foundation. May import: `utils`. MUST NOT import core engine, connectors,
CLI, or MCP — it is consumed by connectors, not the other way around.

## Where to find what

```
src/parsing/
  router.py            FileRouter — extension → strategy (Docling / AST / plaintext / fallback)
  docling_parser.py    PDF/DOCX/PPTX/HTML/images via Docling, OCR (RapidOCR default)
  code_chunker.py      tree-sitter AST chunking (Python, TS, JS, Java, Rust, Go, C, C++)
  plaintext_parser.py  Markdown via Docling (structure-aware); other text by paragraph
  schema.py            ParsedDocument / ParsedChunk
```

## Architecture notes

- **`ParsingModule`** is the facade routing files to the correct parser via
  `FileRouter`.
- **`CodeChunker`** splits at function/class/method boundaries (AST-aware), not
  fixed-size windows.
- **Output:** `ParsedDocument` of `ParsedChunk` objects, each carrying raw text,
  *contextualized* text (heading/path prefix for better embedding), metadata, and
  content hashes. No engine/connector types leak into the output.
- Keep Docling/tree-sitter imports inside functions — they are heavy.
