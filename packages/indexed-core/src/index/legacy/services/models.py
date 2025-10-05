from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, List
from dataclasses import dataclass


class SourceConfig(BaseModel):
    """Configuration for a document collection source."""

    name: str
    type: Literal["jira", "jiraCloud", "confluence", "confluenceCloud", "localFiles"]
    base_url_or_path: str = Field(
        ..., description="baseUrl for remote sources OR basePath for files"
    )
    query: Optional[str] = None
    indexer: str
    reader_opts: Dict = Field(
        default_factory=dict, description="Type-specific reader options"
    )


@dataclass
class CollectionStatus:
    """Status information for a collection."""

    name: str
    number_of_documents: int
    number_of_chunks: int
    updated_time: str
    last_modified_document_time: str
    indexers: List[str]
    index_size: Optional[int] = None
    # Newly added optional metadata
    source_type: Optional[str] = None
    relative_path: Optional[str] = None
    disk_size_bytes: Optional[int] = None
