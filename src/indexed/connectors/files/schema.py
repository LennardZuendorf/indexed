"""Configuration schema for FileSystem connector."""

import fnmatch
import re
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

# Directories always pruned during traversal (VCS metadata, build artefacts, env dirs).
DEFAULT_EXCLUDED_DIRS: List[str] = [
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".eggs",
]


class FileSystemConfig(BaseModel):
    """Type-safe configuration for FileSystem connector."""

    path: str = Field(..., description="Path to files or directory")
    include_patterns: List[str] = Field(
        default=["*"],
        description=(
            "Patterns for files to include (glob or regex). "
            "Prefix a pattern with '!' to exclude matching files, e.g. ['*', '!*.pyc', '!dist/*']."
        ),
    )
    fail_fast: bool = Field(
        default=False, description="Stop indexing on first error (yes/no)"
    )

    # New fields for upgraded connector
    change_tracking: Literal["auto", "git", "content_hash", "mtime", "none"] = Field(
        default="auto",
        description="Change detection strategy for incremental indexing",
    )
    ocr_enabled: bool = Field(
        default=True, description="Enable OCR for scanned documents"
    )
    table_structure: bool = Field(
        default=True, description="Enable table structure recognition"
    )
    code_chunking: bool = Field(
        default=True, description="Enable AST-aware code chunking"
    )
    max_chunk_tokens: int = Field(default=512, description="Maximum tokens per chunk")
    excluded_dirs: List[str] = Field(
        default_factory=lambda: list(DEFAULT_EXCLUDED_DIRS),
        description="Directory names to prune before descending (e.g. node_modules, .venv)",
    )
    respect_gitignore: bool = Field(
        default=True,
        description="Respect .gitignore files and skip default noise directories (node_modules, .venv, __pycache__, etc.)",
    )

    @field_validator("include_patterns", mode="before")
    @classmethod
    def normalize_patterns(cls, patterns: List[str]) -> List[str]:
        """Accept both regex and glob patterns; strip '!' prefix before compiling.

        Valid regex is kept as-is. Patterns that fail regex compilation are
        treated as globs and converted via fnmatch.translate, e.g. ``*.md``
        becomes ``(?s:.*\\.md)\\Z``.
        """
        result = []
        for pattern in patterns:
            prefix = "!" if pattern.startswith("!") else ""
            bare = pattern[1:] if prefix else pattern
            try:
                re.compile(bare)
                result.append(prefix + bare)
            except re.error:
                result.append(prefix + fnmatch.translate(bare))
        return result

    @field_validator("path")
    @classmethod
    def validate_path_exists(cls, v: str) -> str:
        """Validate that the provided filesystem path exists."""
        if not Path(v).exists():
            raise ValueError(f"Path does not exist: {v}")
        return v


# Alias for backward compatibility with registry
LocalFilesConfig = FileSystemConfig

__all__ = [
    "FileSystemConfig",
    "LocalFilesConfig",
    "DEFAULT_EXCLUDED_DIRS",
]
