"""Configuration schema for FileSystem connector."""

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

    @field_validator("path")
    @classmethod
    def validate_path_exists(cls, v: str) -> str:
        if not Path(v).exists():
            raise ValueError(f"Path does not exist: {v}")
        return v


__all__ = ["FileSystemConfig"]


