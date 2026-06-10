---
type: branch
scope: parsing
parent: tech.md
covers: ParsingModule, FileRouter, Docling, tree-sitter CodeChunker, ParsedDocument output
updated: 2026-06-09
---

# Tech Branch: Parsing (`indexed-parsing`)

Reusable parsing module shared across connectors (Files, Confluence, Outline).
Lazy-loaded to keep CLI startup fast.

**Parent: [tech.md](tech.md).** Consumed by [tech-connectors.md](tech-connectors.md).

---

## Components

| Component | Role |
|-----------|------|
| **FileRouter** | Map file extension → parsing strategy (Docling, AST, plaintext, fallback) |
| **DoclingParser** | PDF/DOCX/PPTX/HTML/images via Docling, OCR (RapidOCR default) |
| **CodeChunker** | AST-aware code chunking via tree-sitter (Python, TS, JS, Java, Rust, Go, C, C++) — splits at function/class/method boundaries |
| **PlaintextParser** | Markdown via Docling (structure-aware); other text via paragraph splitting |
| **ParsingModule** | Facade routing files to the correct parser |

---

## Output

Framework-free `ParsedDocument` containing `ParsedChunk` objects:
- raw text
- contextualized text (heading/path prefix for embedding)
- metadata
- content hashes
