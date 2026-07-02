from dataclasses import dataclass
from typing import Callable, Literal, Optional, Protocol

from pydantic import BaseModel, Field


class SourceConfig(BaseModel):
    """Configuration for a document collection source."""

    name: str
    type: Literal[
        "jira", "jiraCloud", "confluence", "confluenceCloud", "localFiles", "outline"
    ]
    base_url_or_path: str = Field(
        ..., description="baseUrl for remote sources OR basePath for files"
    )
    query: Optional[str] = None
    indexer: Optional[str] = None
    reader_opts: dict = Field(
        default_factory=dict, description="Type-specific reader options"
    )


@dataclass
class ProgressUpdate:
    """Progress update information for long-running operations.

    This dataclass provides structured progress information that can be used
    by CLI progress bars, logging systems, or other UI components to show
    real-time progress of operations like document reading, indexing, and searching.
    """

    stage: str  # e.g., "reading", "indexing", "searching", "inspecting"
    current: int  # Current item count
    total: Optional[int]  # Total items (None if unknown)
    message: str  # Human-readable message


# Type alias for progress callback functions (simple, legacy)
ProgressCallback = Optional[Callable[[ProgressUpdate], None]]


class PhasedProgressCallback(Protocol):
    """Protocol for phased progress reporting.

    Supports multi-stage operations where each stage has its own progress
    indicator (spinner or bar). The CLI implements this with Rich Progress;
    the MCP server or tests can use a no-op implementation.

    Stages for indexing: "Loading model", "Fetching documents",
    "Parsing & chunking", "Generating embeddings", "Building FAISS index",
    "Writing to disk".
    """

    def start_phase(self, name: str, total: Optional[int] = None) -> None:
        """Begin a named phase. If total is given, a progress bar is shown;
        otherwise a spinner is used."""
        ...

    def advance(self, name: str, amount: int = 1) -> None:
        """Advance the named phase by amount items."""
        ...

    def finish_phase(self, name: str) -> None:
        """Mark the named phase as complete."""
        ...

    def log(self, message: str) -> None:
        """Display a log message within the progress context."""
        ...


__all__ = [
    "PhasedProgressCallback",
    "ProgressCallback",
    "ProgressUpdate",
    "SourceConfig",
]
