"""Configuration models using Pydantic for type-safe configuration."""
from pydantic import BaseModel, Field, field_validator
from pathlib import Path
from typing import Optional, List


class WorkspaceConfig(BaseModel):
    """Workspace-level configuration."""
    
    name: str = "default"
    root_path: Path
    index_path: Optional[Path] = None
    
    @field_validator('index_path', mode='before')
    @classmethod
    def set_index_path(cls, v, info):
        """Set default index path if not provided."""
        if v is None and 'root_path' in info.data:
            return info.data['root_path'] / ".indexed"
        return v


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""
    
    provider: str = "sentence-transformers"
    model_name: str = "all-MiniLM-L6-v2"
    dimension: int = 384  # Will be auto-detected from model
    batch_size: int = 32
    device: Optional[str] = None  # None = auto-detect (cuda/mps/cpu)


class VectorStoreConfig(BaseModel):
    """Vector store configuration."""
    
    type: str = "faiss"
    index_type: str = "IndexFlatL2"
    persistence_enabled: bool = True
    persistence_path: Optional[Path] = None
    
    @field_validator('persistence_path', mode='before')
    @classmethod
    def set_persistence_path(cls, v, info):
        """Set default persistence path if not provided."""
        if v is None:
            return Path.home() / ".indexed" / "faiss_index"
        return v


class IndexingConfig(BaseModel):
    """Indexing pipeline configuration."""
    
    chunk_size: int = 512
    chunk_overlap: int = 50
    exclude_patterns: List[str] = Field(
        default_factory=lambda: [
            "*.pyc", 
            "__pycache__", 
            ".git", 
            "node_modules", 
            ".venv",
            "venv",
            ".env",
            "*.log"
        ]
    )
    include_patterns: List[str] = Field(
        default_factory=lambda: [
            "*.py", 
            "*.md", 
            "*.txt", 
            "*.rst", 
            "*.js", 
            "*.ts",
            "*.jsx",
            "*.tsx",
            "*.java",
            "*.go",
            "*.rs"
        ]
    )


class ConnectorConfig(BaseModel):
    """Connector configuration."""
    
    filesystem_enabled: bool = True
    filesystem_watch: bool = False
    git_enabled: bool = False


class SearchConfig(BaseModel):
    """Search configuration."""
    
    default_top_k: int = 10
    similarity_threshold: float = 0.0  # 0.0 = no threshold


class IndexedConfig(BaseModel):
    """Root configuration model for the indexed system."""
    
    workspace: WorkspaceConfig
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    connectors: ConnectorConfig = Field(default_factory=ConnectorConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
