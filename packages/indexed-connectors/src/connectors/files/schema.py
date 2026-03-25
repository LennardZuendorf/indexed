"""Configuration schema for FileSystem connector."""

import fnmatch
import re
from typing import List
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class FileSystemConfig(BaseModel):
    """Type-safe configuration for FileSystem connector."""

    path: str = Field(..., description="Path to files or directory")
    include_patterns: List[str] = Field(
        default=[".*"],
        description="Regex patterns for files to include (comma-separated)",
    )
    exclude_patterns: List[str] = Field(
        default=[],
        description="Regex patterns for files to exclude (comma-separated)",
    )
    fail_fast: bool = Field(
        default=False, description="Stop indexing on first error (yes/no)"
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
        """
        Validate that the provided filesystem path exists.

        Parameters:
            v (str): Path string to validate.

        Returns:
            str: The same path string when it exists.

        Raises:
            ValueError: If the path does not exist.
        """
        if not Path(v).exists():
            raise ValueError(f"Path does not exist: {v}")
        return v


# Alias for backward compatibility with registry
LocalFilesConfig = FileSystemConfig

__all__ = ["FileSystemConfig", "LocalFilesConfig"]
