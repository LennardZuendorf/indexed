---
type: tech
updated: 2026-11-22
applies: "src/indexed/parsing/**"
---

# Components

| Component | Role |
|-----------|------|
| **FileRouter** | Map file extension → parsing strategy (Docling, AST, plaintext, fallback) |
| **DoclingParser** | PDF/DOCX/PPTX/HTML/images via Docling, OCR (RapidOCR default) |
| **CodeChunker** | AST-aware code chunking via tree-sitter (Python, TS, JS, Java, Rust, Go, C, C++) — splits at function/class/method boundaries |
| **PlaintextParser** | Markdown via Docling (structure-aware); other text via paragraph splitting |
| **ParsingModule** | Facade routing files to the correct parser; `code_chunking=False` sends code extensions to `PlaintextParser` (paragraph windows) instead of `CodeChunker` (AST boundaries) |
