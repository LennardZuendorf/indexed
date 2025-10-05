# Phase 2 Implementation Guide - Quick Reference

This guide provides ready-to-use code templates for implementing each component. Follow the order specified in `PHASE2_IMPLEMENTATION_PLAN.md`.

## Phase 2.1: Foundation

### Step 1: Config Models (config/models.py)

```python
"""Configuration models using Pydantic."""
from pydantic import BaseModel, Field, field_validator
from pathlib import Path
from typing import Optional, List, Dict, Any
import os


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
    dimension: int = 384  # Will be auto-detected
    batch_size: int = 32
    device: Optional[str] = None  # None = auto-detect


class VectorStoreConfig(BaseModel):
    """Vector store configuration."""
    type: str = "faiss"
    index_type: str = "IndexFlatL2"
    persistence_enabled: bool = True
    persistence_path: Optional[Path] = None
    
    @field_validator('persistence_path', mode='before')
    @classmethod
    def set_persistence_path(cls, v, info):
        """Set default persistence path."""
        return v or Path.home() / ".indexed" / "faiss_index"


class IndexingConfig(BaseModel):
    """Indexing pipeline configuration."""
    chunk_size: int = 512
    chunk_overlap: int = 50
    exclude_patterns: List[str] = Field(
        default_factory=lambda: ["*.pyc", "__pycache__", ".git", "node_modules", ".venv"]
    )
    include_patterns: List[str] = Field(
        default_factory=lambda: ["*.py", "*.md", "*.txt", "*.rst", "*.js", "*.ts"]
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
    """Root configuration model."""
    workspace: WorkspaceConfig
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    connectors: ConnectorConfig = Field(default_factory=ConnectorConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
```

### Step 2: Config Service (config/service.py)

```python
"""Configuration service for loading and saving TOML configs."""
import tomllib  # Python 3.11+, or use tomli for earlier versions
import tomlkit
from pathlib import Path
from typing import Optional
from platformdirs import user_config_dir

from .models import IndexedConfig


class ConfigService:
    """Loads, validates, and saves configuration."""
    
    def __init__(self, config_path: Optional[Path] = None):
        """Initialize config service.
        
        Args:
            config_path: Optional path to config file. If None, uses default.
        """
        self.config_path = config_path or self._default_config_path()
    
    def load_config(self, workspace_path: Optional[Path] = None) -> IndexedConfig:
        """Load and validate configuration.
        
        Args:
            workspace_path: Optional workspace path for workspace-specific config.
            
        Returns:
            Validated IndexedConfig instance.
        """
        # Load global config
        global_config = self._load_toml(self.config_path) if self.config_path.exists() else {}
        
        # Load workspace config if workspace_path provided
        workspace_config = {}
        if workspace_path:
            workspace_config_path = workspace_path / ".indexed" / "config.toml"
            if workspace_config_path.exists():
                workspace_config = self._load_toml(workspace_config_path)
        
        # Merge configs (workspace takes precedence)
        merged_config = self._merge_configs(global_config, workspace_config)
        
        # Validate with Pydantic
        return IndexedConfig(**merged_config)
    
    def save_config(self, config: IndexedConfig, path: Optional[Path] = None) -> None:
        """Save configuration to TOML file.
        
        Args:
            config: Config to save.
            path: Optional path to save to. If None, uses self.config_path.
        """
        save_path = path or self.config_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert Pydantic model to dict
        config_dict = config.model_dump(mode='json', exclude_none=True)
        
        # Convert Path objects to strings
        config_dict = self._serialize_paths(config_dict)
        
        # Write TOML
        with open(save_path, 'w') as f:
            tomlkit.dump(config_dict, f)
    
    def _load_toml(self, path: Path) -> dict:
        """Load TOML file."""
        with open(path, 'rb') as f:
            return tomllib.load(f)
    
    def _merge_configs(self, global_config: dict, workspace_config: dict) -> dict:
        """Merge workspace config with global config.
        
        Workspace config takes precedence for conflicting keys.
        """
        merged = global_config.copy()
        
        # Deep merge
        for key, value in workspace_config.items():
            if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                merged[key] = {**merged[key], **value}
            else:
                merged[key] = value
        
        return merged
    
    def _serialize_paths(self, config_dict: dict) -> dict:
        """Convert Path objects to strings recursively."""
        for key, value in config_dict.items():
            if isinstance(value, dict):
                config_dict[key] = self._serialize_paths(value)
            elif isinstance(value, Path):
                config_dict[key] = str(value)
        return config_dict
    
    @staticmethod
    def _default_config_path() -> Path:
        """Get default config path."""
        config_dir = Path(user_config_dir("indexed", "indexed"))
        return config_dir / "config.toml"
```

### Step 3: Base Interfaces (connectors/base.py)

```python
"""Base connector protocol."""
from typing import Protocol, Iterator
from pathlib import Path

from indexed_core.models.document import Document


class DocumentConnector(Protocol):
    """Protocol for document connectors."""
    
    def discover_documents(self, source: str) -> Iterator[Path]:
        """Discover documents from a source.
        
        Args:
            source: Source path or identifier.
            
        Yields:
            Path objects for discovered documents.
        """
        ...
    
    def read_document(self, path: Path) -> Document:
        """Read and parse a document.
        
        Args:
            path: Path to document.
            
        Returns:
            Document object.
        """
        ...
    
    def supports_path(self, path: Path) -> bool:
        """Check if this connector supports the given path.
        
        Args:
            path: Path to check.
            
        Returns:
            True if supported, False otherwise.
        """
        ...
```

### Step 4: Domain Models (models/document.py)

```python
"""Domain models for documents and search results."""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import uuid


@dataclass
class Document:
    """Represents a source document."""
    id: str
    content: str
    source_path: Path
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def from_file(cls, path: Path, content: str) -> "Document":
        """Create document from file."""
        return cls(
            id=str(uuid.uuid4()),
            content=content,
            source_path=path,
            metadata={
                "filename": path.name,
                "extension": path.suffix,
                "size": path.stat().st_size if path.exists() else 0,
                "modified": datetime.fromtimestamp(path.stat().st_mtime) if path.exists() else None,
            }
        )


@dataclass
class Chunk:
    """Represents a chunk of a document."""
    id: str
    document_id: str
    content: str
    index: int  # Chunk index within document
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_document(cls, document: Document, content: str, index: int) -> "Chunk":
        """Create chunk from document."""
        return cls(
            id=f"{document.id}_chunk_{index}",
            document_id=document.id,
            content=content,
            index=index,
            metadata={
                **document.metadata,
                "source_path": str(document.source_path),
                "chunk_index": index,
            }
        )


@dataclass
class SearchResult:
    """Represents a search result."""
    chunk: Chunk
    score: float
    document: Optional[Document] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "chunk_id": self.chunk.id,
            "content": self.chunk.content,
            "score": self.score,
            "metadata": self.chunk.metadata,
            "document_id": self.chunk.document_id,
        }
```

## Phase 2.2: Core Services

### Step 5: Storage Service (services/storage.py)

```python
"""Vector storage service using FAISS."""
import faiss
import numpy as np
import pickle
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import logging

logger = logging.getLogger(__name__)


class StorageService:
    """Manages vector storage with FAISS."""
    
    def __init__(
        self,
        dimension: int,
        index_type: str = "IndexFlatL2",
        persistence_path: Optional[Path] = None
    ):
        """Initialize storage service.
        
        Args:
            dimension: Embedding dimension.
            index_type: FAISS index type (IndexFlatL2, IndexIVFFlat, etc.).
            persistence_path: Path to save/load index.
        """
        self.dimension = dimension
        self.index_type = index_type
        self.persistence_path = persistence_path
        self.index = self._create_index(index_type)
        self.id_mapping: Dict[int, str] = {}  # FAISS index -> chunk ID
        self.reverse_mapping: Dict[str, int] = {}  # chunk ID -> FAISS index
        self.next_id = 0
        
        # Try to load existing index
        if persistence_path and persistence_path.exists():
            self.load()
    
    def _create_index(self, index_type: str) -> faiss.Index:
        """Create FAISS index."""
        if index_type == "IndexFlatL2":
            return faiss.IndexFlatL2(self.dimension)
        elif index_type == "IndexFlatIP":
            return faiss.IndexFlatIP(self.dimension)
        else:
            raise ValueError(f"Unsupported index type: {index_type}")
    
    def add_vectors(self, vectors: np.ndarray, ids: List[str]) -> None:
        """Add vectors to index.
        
        Args:
            vectors: Array of shape (n, dimension).
            ids: List of chunk IDs corresponding to vectors.
        """
        if vectors.shape[0] != len(ids):
            raise ValueError("Number of vectors must match number of IDs")
        
        # Ensure vectors are float32
        vectors = vectors.astype(np.float32)
        
        # Add to FAISS
        self.index.add(vectors)
        
        # Update mappings
        for i, chunk_id in enumerate(ids):
            faiss_idx = self.next_id + i
            self.id_mapping[faiss_idx] = chunk_id
            self.reverse_mapping[chunk_id] = faiss_idx
        
        self.next_id += len(ids)
        logger.info(f"Added {len(ids)} vectors to index. Total: {self.index.ntotal}")
    
    def search(self, query_vector: np.ndarray, top_k: int = 10) -> List[Tuple[str, float]]:
        """Search for similar vectors.
        
        Args:
            query_vector: Query vector of shape (dimension,).
            top_k: Number of results to return.
            
        Returns:
            List of (chunk_id, similarity_score) tuples.
        """
        # Ensure query is 2D and float32
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)
        query_vector = query_vector.astype(np.float32)
        
        # Search
        distances, indices = self.index.search(query_vector, top_k)
        
        # Map back to chunk IDs
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx == -1:  # No result
                continue
            chunk_id = self.id_mapping.get(int(idx))
            if chunk_id:
                # Convert L2 distance to similarity score (inverse)
                score = 1.0 / (1.0 + dist)
                results.append((chunk_id, float(score)))
        
        return results
    
    def delete_by_ids(self, ids: List[str]) -> None:
        """Remove vectors by chunk IDs.
        
        Note: FAISS doesn't support efficient deletion, so this requires rebuilding.
        """
        # Get FAISS indices to remove
        faiss_indices = [self.reverse_mapping.get(chunk_id) for chunk_id in ids if chunk_id in self.reverse_mapping]
        
        if not faiss_indices:
            return
        
        # For now, this is a placeholder
        # Full implementation would require rebuilding the index
        logger.warning("delete_by_ids not fully implemented - requires index rebuild")
    
    def save(self) -> None:
        """Persist index to disk."""
        if not self.persistence_path:
            logger.warning("No persistence path set, skipping save")
            return
        
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save FAISS index
        faiss.write_index(self.index, str(self.persistence_path))
        
        # Save mappings
        mapping_path = self.persistence_path.with_suffix('.mappings.pkl')
        with open(mapping_path, 'wb') as f:
            pickle.dump({
                'id_mapping': self.id_mapping,
                'reverse_mapping': self.reverse_mapping,
                'next_id': self.next_id,
            }, f)
        
        logger.info(f"Saved index to {self.persistence_path}")
    
    def load(self) -> None:
        """Load index from disk."""
        if not self.persistence_path or not self.persistence_path.exists():
            logger.warning("No index file found, starting fresh")
            return
        
        # Load FAISS index
        self.index = faiss.read_index(str(self.persistence_path))
        
        # Load mappings
        mapping_path = self.persistence_path.with_suffix('.mappings.pkl')
        if mapping_path.exists():
            with open(mapping_path, 'rb') as f:
                data = pickle.load(f)
                self.id_mapping = data['id_mapping']
                self.reverse_mapping = data['reverse_mapping']
                self.next_id = data['next_id']
        
        logger.info(f"Loaded index from {self.persistence_path}. Total vectors: {self.index.ntotal}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        return {
            "total_vectors": self.index.ntotal,
            "dimension": self.dimension,
            "index_type": self.index_type,
            "is_trained": self.index.is_trained,
        }
```

### Step 6: Embedding Service (services/embedding.py)

```python
"""Embedding service using sentence-transformers."""
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates embeddings using sentence-transformers."""
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: Optional[str] = None,
        batch_size: int = 32
    ):
        """Initialize embedding service.
        
        Args:
            model_name: Name of sentence-transformers model.
            device: Device to use ("cpu", "cuda", "mps"). None = auto-detect.
            batch_size: Batch size for encoding.
        """
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name, device=device)
        self.batch_size = batch_size
        logger.info(f"Model loaded. Dimension: {self.dimension}")
    
    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text.
        
        Args:
            text: Text to embed.
            
        Returns:
            Embedding vector of shape (dimension,).
        """
        return self.model.encode(text, convert_to_numpy=True)
    
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Embed multiple texts efficiently.
        
        Args:
            texts: List of texts to embed.
            
        Returns:
            Array of embeddings of shape (len(texts), dimension).
        """
        return self.model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 100
        )
    
    @property
    def dimension(self) -> int:
        """Return embedding dimension."""
        return self.model.get_sentence_embedding_dimension()
```

### Step 7: FileSystem Connector (connectors/filesystem.py)

```python
"""FileSystem connector for reading local files."""
import fnmatch
from pathlib import Path
from typing import Iterator, List
import logging

from indexed_core.models.document import Document

logger = logging.getLogger(__name__)


class FileSystemConnector:
    """Reads documents from filesystem."""
    
    def __init__(
        self,
        include_patterns: List[str],
        exclude_patterns: List[str]
    ):
        """Initialize filesystem connector.
        
        Args:
            include_patterns: Glob patterns for files to include.
            exclude_patterns: Glob patterns for files to exclude.
        """
        self.include_patterns = include_patterns
        self.exclude_patterns = exclude_patterns
    
    def discover_documents(self, source: str) -> Iterator[Path]:
        """Discover documents from a filesystem path.
        
        Args:
            source: File or directory path.
            
        Yields:
            Path objects for discovered documents.
        """
        source_path = Path(source).resolve()
        
        if not source_path.exists():
            logger.error(f"Source path does not exist: {source_path}")
            return
        
        if source_path.is_file():
            if self._should_include(source_path):
                yield source_path
            return
        
        # Recursively walk directory
        for path in source_path.rglob("*"):
            if path.is_file() and self._should_include(path):
                yield path
    
    def read_document(self, path: Path) -> Document:
        """Read file content and create Document.
        
        Args:
            path: Path to file.
            
        Returns:
            Document object.
        """
        try:
            # Try UTF-8 first
            content = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            # Fallback to latin-1
            logger.warning(f"Failed to read {path} as UTF-8, trying latin-1")
            content = path.read_text(encoding='latin-1')
        
        return Document.from_file(path, content)
    
    def supports_path(self, path: Path) -> bool:
        """Check if this connector supports the given path."""
        return path.exists() and (path.is_file() or path.is_dir())
    
    def _should_include(self, path: Path) -> bool:
        """Check if file should be included based on patterns."""
        # Check exclude patterns first
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(path.name, pattern) or any(
                fnmatch.fnmatch(part, pattern) for part in path.parts
            ):
                return False
        
        # Check include patterns
        for pattern in self.include_patterns:
            if fnmatch.fnmatch(path.name, pattern):
                return True
        
        return False
```

## Phase 2.3: Business Logic

### Steps 8-11: See `PHASE2_IMPLEMENTATION_PLAN.md` for service and controller templates

The services and controllers follow similar patterns:
- Services contain business logic
- Controllers orchestrate services
- All use constructor injection

## Quick Start Checklist

- [ ] Create branch: `git checkout -b phase2-controller-service`
- [ ] Implement Phase 2.1 (Foundation)
  - [ ] config/models.py
  - [ ] config/service.py
  - [ ] connectors/base.py
  - [ ] models/document.py
- [ ] Test config loading manually
- [ ] Implement Phase 2.2 (Core Services)
  - [ ] services/storage.py
  - [ ] services/embedding.py
  - [ ] connectors/filesystem.py
- [ ] Test each service in isolation
- [ ] Implement Phase 2.3 (Business Logic)
  - [ ] services/indexing.py
  - [ ] services/search.py
  - [ ] controllers/index_controller.py
  - [ ] controllers/search_controller.py
- [ ] Implement Phase 2.4 (Integration)
  - [ ] factory.py
  - [ ] default_config.toml
  - [ ] Update CLI commands
- [ ] Write tests
- [ ] Update documentation
- [ ] Merge to main

## Common Patterns

### Error Handling
```python
import logging
logger = logging.getLogger(__name__)

try:
    # operation
except SpecificException as e:
    logger.error(f"Operation failed: {e}")
    raise  # or handle appropriately
```

### Type Hints
```python
from typing import List, Optional, Dict, Any
from pathlib import Path

def method(param: str, optional: Optional[int] = None) -> List[str]:
    pass
```

### Dependency Injection
```python
class Service:
    def __init__(self, dependency: Dependency):
        self.dependency = dependency  # Inject, don't instantiate
```
