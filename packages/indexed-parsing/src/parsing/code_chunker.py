"""AST-aware code chunker using tree-sitter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from .schema import ParsedChunk

# ---------------------------------------------------------------------------
# Language maps
# ---------------------------------------------------------------------------

LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".rs": "rust",
    ".go": "go",
}

SEMANTIC_NODES: dict[str, frozenset[str]] = {
    "python": frozenset(
        {"function_definition", "class_definition", "decorated_definition"}
    ),
    "typescript": frozenset(
        {
            "function_declaration",
            "class_declaration",
            "export_statement",
            "lexical_declaration",
        }
    ),
    "javascript": frozenset(
        {
            "function_declaration",
            "class_declaration",
            "export_statement",
            "lexical_declaration",
        }
    ),
    "java": frozenset(
        {"class_declaration", "method_declaration", "interface_declaration"}
    ),
    "rust": frozenset({"function_item", "impl_item", "struct_item", "enum_item"}),
    "go": frozenset({"function_declaration", "method_declaration", "type_declaration"}),
    "c": frozenset({"function_definition", "struct_specifier", "enum_specifier"}),
    "cpp": frozenset(
        {
            "function_definition",
            "class_specifier",
            "struct_specifier",
            "namespace_definition",
        }
    ),
}


def _get_language(lang_name: str) -> Any:
    """Return a tree-sitter ``Language`` object for *lang_name*."""
    import importlib

    import tree_sitter

    # tree-sitter-python → tree_sitter_python, etc.
    module_name = f"tree_sitter_{lang_name}"
    mod = importlib.import_module(module_name)

    # Some packages expose language() directly, others use language_<name>()
    # (e.g., tree_sitter_typescript exposes language_typescript / language_tsx)
    if hasattr(mod, "language"):
        capsule = mod.language()
    else:
        fn_name = f"language_{lang_name}"
        capsule = getattr(mod, fn_name)()

    return tree_sitter.Language(capsule)


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


class CodeChunker:
    """Chunk source files at semantic AST boundaries using tree-sitter."""

    def __init__(self, *, max_tokens: int = 512) -> None:
        self._max_tokens = max_tokens
        # rough chars-per-token estimate for code
        self._max_chars = max_tokens * 4

    def chunk_file(self, path: Path) -> list[ParsedChunk]:
        """Parse *path* and return chunks split at semantic boundaries."""
        ext = path.suffix.lower()
        lang_name = LANGUAGE_MAP.get(ext)

        if lang_name is None:
            return self._line_fallback(path)

        try:
            import tree_sitter

            language = _get_language(lang_name)
            parser = tree_sitter.Parser(language)

            source = path.read_bytes()
            tree = parser.parse(source)
            source_text = source.decode(errors="replace")

            semantic = SEMANTIC_NODES.get(lang_name, frozenset())
            raw = self._walk_nodes(
                tree.root_node, source_text, semantic, str(path), lang_name
            )

            return raw if raw else self._line_fallback(path)

        except Exception:
            logger.opt(exception=True).debug(
                "tree-sitter failed for {}; falling back to line-based chunking", path
            )
            return self._line_fallback(path)

    # -- recursive walk ---------------------------------------------------

    def _walk_nodes(
        self,
        node: Any,
        source: str,
        semantic: frozenset[str],
        file_path: str,
        language: str,
    ) -> list[ParsedChunk]:
        """Walk children of *node* and split at semantic boundaries."""
        chunks: list[ParsedChunk] = []
        accumulator: list[str] = []
        acc_start: int | None = None

        for child in node.children:
            text = source[child.start_byte : child.end_byte]

            if child.type in semantic:
                # flush accumulated non-semantic text
                if accumulator:
                    merged = "\n".join(accumulator)
                    chunks.append(
                        self._make_chunk(
                            merged,
                            file_path,
                            language,
                            "accumulated",
                            acc_start or child.start_point[0],
                            child.start_point[0] - 1,
                        )
                    )
                    accumulator.clear()
                    acc_start = None

                if len(text) > self._max_chars:
                    # oversized → recurse into children
                    chunks.extend(
                        self._walk_nodes(child, source, semantic, file_path, language)
                    )
                else:
                    chunks.append(
                        self._make_chunk(
                            text,
                            file_path,
                            language,
                            child.type,
                            child.start_point[0],
                            child.end_point[0],
                        )
                    )
            else:
                if text.strip():
                    if acc_start is None:
                        acc_start = child.start_point[0]
                    accumulator.append(text)

        # flush remaining
        if accumulator:
            merged = "\n".join(accumulator)
            last_line = node.end_point[0]
            chunks.append(
                self._make_chunk(
                    merged,
                    file_path,
                    language,
                    "accumulated",
                    acc_start or node.start_point[0],
                    last_line,
                )
            )

        return chunks

    # -- helpers ----------------------------------------------------------

    def _make_chunk(
        self,
        text: str,
        file_path: str,
        language: str,
        node_type: str,
        start_line: int,
        end_line: int,
    ) -> ParsedChunk:
        ctx = f"# {file_path}\n{text}"
        return ParsedChunk(
            text=text,
            contextualized_text=ctx,
            metadata={
                "language": language,
                "node_type": node_type,
                "start_line": start_line,
                "end_line": end_line,
                "file_path": file_path,
            },
            source_type="code",
        )

    def _line_fallback(self, path: Path) -> list[ParsedChunk]:
        """Simple line-based chunking when AST parsing is not available."""
        try:
            text = path.read_text(errors="replace")
        except Exception:
            logger.opt(exception=True).warning("Cannot read {}", path)
            return []

        if not text.strip():
            return []

        lines = text.splitlines(keepends=True)
        chunks: list[ParsedChunk] = []
        buf: list[str] = []
        buf_len = 0
        start_line = 0

        for i, line in enumerate(lines):
            if buf_len + len(line) > self._max_chars and buf:
                chunk_text = "".join(buf)
                chunks.append(
                    self._make_chunk(
                        chunk_text,
                        str(path),
                        "unknown",
                        "lines",
                        start_line,
                        i - 1,
                    )
                )
                buf.clear()
                buf_len = 0
                start_line = i

            buf.append(line)
            buf_len += len(line)

        if buf:
            chunk_text = "".join(buf)
            chunks.append(
                self._make_chunk(
                    chunk_text,
                    str(path),
                    "unknown",
                    "lines",
                    start_line,
                    len(lines) - 1,
                )
            )

        return chunks
