# indexed-parsing

Reusable document parsing module for the indexed project. Provides Docling-based document parsing, tree-sitter code chunking, and plaintext parsing.

## Architecture

```
FileRouter → ParsingStrategy → Parser → ParsedDocument
                                  ├── DoclingParser    (PDF, DOCX, PPTX, HTML, images)
                                  ├── CodeChunker      (Python, TS, JS, Java, Rust, Go, C/C++)
                                  └── PlaintextParser  (Markdown, JSON, YAML, TXT, CSV, etc.)
```

## Components

### FileRouter
Maps file extensions to parsing strategies. Case-insensitive.

| Strategy | Extensions |
|----------|-----------|
| `CODE_AST` | `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.java`, `.c`, `.cpp`, `.h`, `.rs`, `.go`, `.rb`, `.cs`, `.swift`, `.kt`, `.scala`, `.sh`, `.sql`, `.proto`, `.lua`, `.r` |
| `DOCLING` | `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.htm`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.tex` |
| `PLAINTEXT` | `.md`, `.txt`, `.rst`, `.csv`, `.json`, `.yaml`, `.yml`, `.toml`, `.xml`, `.ini`, `.cfg`, `.env`, `.log` |
| `DOCLING_FALLBACK` | Everything else (tries Docling, falls back to plaintext) |

### DoclingParser
Rich document parsing via Docling's `DocumentConverter` + `HierarchicalChunker`. Supports OCR (RapidOCR with bundled ONNX models by default — no downloads needed), table structure recognition, and heading-aware chunking.

### CodeChunker
AST-aware chunking via tree-sitter. Splits at semantic boundaries:
- **Python:** `function_definition`, `class_definition`, `decorated_definition`
- **TypeScript/JS:** `function_declaration`, `class_declaration`, `export_statement`, `lexical_declaration`
- **Java:** `class_declaration`, `method_declaration`, `interface_declaration`
- **Rust:** `function_item`, `impl_item`, `struct_item`, `enum_item`
- **Go:** `function_declaration`, `method_declaration`, `type_declaration`

Falls back to line-based chunking for unsupported languages.

### PlaintextParser
Markdown and RST are parsed via Docling for structure-aware chunking with heading hierarchy. Everything else (JSON, YAML, CSV, etc.) is split at paragraph boundaries.

## Data Models

```python
@dataclass(frozen=True)
class ParsedChunk:
    text: str                    # Raw content
    contextualized_text: str     # With heading/path prefix (what gets embedded)
    metadata: dict               # Headings, page numbers, language, line numbers, etc.
    source_type: Literal["document", "code", "plaintext"]
    content_hash: str            # xxhash for deduplication/change detection

@dataclass
class ParsedDocument:
    file_path: str
    chunks: list[ParsedChunk]
    metadata: dict               # Format, size, modified_time, etc.
```

## Usage

```python
from parsing import ParsingModule

module = ParsingModule(ocr=True, table_structure=True, max_tokens=512)

# Parse a file
doc = module.parse(Path("report.pdf"))
for chunk in doc.chunks:
    print(chunk.contextualized_text)

# Parse in-memory bytes
doc = module.parse_bytes(data, "attachment.docx")
```

## Dependencies

- `docling` + `docling-core` — Document conversion and chunking
- `tree-sitter` + language grammars — AST parsing
- `xxhash` — Content hashing
- `loguru` — Logging
