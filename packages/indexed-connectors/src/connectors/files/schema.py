"""Configuration schema for FileSystem connector."""

import fnmatch
import re
from pathlib import Path
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator

# Default excluded extensions (binary, archive, media, etc.)
DEFAULT_EXCLUDED_EXTENSIONS: List[str] = [
    ".DS_Store",
    # Archive and compressed formats
    ".zip",
    ".tar",
    ".jar",
    ".rar",
    ".gz",
    ".tgz",
    ".7z",
    ".bz2",
    ".xz",
    ".lz4",
    ".zst",
    ".cab",
    ".deb",
    ".rpm",
    ".pkg",
    ".dmg",
    ".iso",
    ".img",
    # Executable and binary formats
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".app",
    ".msi",
    ".bin",
    ".run",
    # Compiled code
    ".class",
    ".pyc",
    ".pyo",
    ".o",
    ".obj",
    ".lib",
    ".a",
    ".bundle",
    # Video formats
    ".mp4",
    ".avi",
    ".mkv",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".3gp",
    ".mpg",
    ".mpeg",
    ".vob",
    ".ogv",
    # Audio formats
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".ogg",
    ".wma",
    ".m4a",
    ".opus",
    ".aiff",
    ".au",
    ".ra",
    # Font formats
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".eot",
    # Database formats
    ".db",
    ".sqlite",
    ".sqlite3",
    ".mdb",
    ".accdb",
    # Virtual machine and disk images
    ".vmdk",
    ".vdi",
    ".qcow2",
    ".vhd",
    ".vhdx",
    # Other binary formats
    ".swf",
    ".fla",
    ".unity3d",
    ".unitypackage",
    ".blend",
    ".max",
    ".3ds",
    ".fbx",
    ".dae",
    ".stl",
    ".ply",
]


class FileSystemConfig(BaseModel):
    """Type-safe configuration for FileSystem connector."""

    path: str = Field(..., description="Path to files or directory")
    include_patterns: List[str] = Field(
        default=["*"],
        description="Patterns for files to include (glob or regex, comma-separated)",
    )
    exclude_patterns: List[str] = Field(
        default=[],
        description="Regex patterns for files to exclude (comma-separated)",
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
    excluded_extensions: List[str] = Field(
        default_factory=lambda: list(DEFAULT_EXCLUDED_EXTENSIONS),
        description="File extensions to exclude from indexing",
    )

    @field_validator("include_patterns", "exclude_patterns", mode="before")
    @classmethod
    def normalize_patterns(cls, patterns: List[str]) -> List[str]:
        """Accept both regex and glob patterns.

        Valid regex is kept as-is. Patterns that fail regex compilation are
        treated as globs and converted via fnmatch.translate, e.g. ``*.md``
        becomes ``(?s:.*\\.md)\\Z``.
        """
        result = []
        for pattern in patterns:
            try:
                re.compile(pattern)
                result.append(pattern)
            except re.error:
                result.append(fnmatch.translate(pattern))
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

__all__ = ["FileSystemConfig", "LocalFilesConfig", "DEFAULT_EXCLUDED_EXTENSIONS"]
