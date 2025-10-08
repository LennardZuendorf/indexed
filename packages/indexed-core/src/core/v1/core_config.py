"""Configuration management for indexed."""

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class Config(BaseModel):
    """Main configuration for indexed.
    
    Provides simple configuration management with defaults and optional
    TOML file loading. All settings can be overridden via environment
    variables or programmatically.
    
    Examples:
        >>> config = Config.load()
        >>> config.embedding_model = "all-MiniLM-L6-v2"
        >>> config.chunk_size = 512
        >>> config.save()
    """
    
    # Embedding configuration
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Embedding model to use for vectorization"
    )
    
    # Indexing configuration
    chunk_size: int = Field(
        default=512,
        description="Text chunk size in characters"
    )
    chunk_overlap: int = Field(
        default=50,
        description="Overlap between consecutive chunks"
    )
    batch_size: int = Field(
        default=32,
        description="Batch size for processing documents"
    )
    
    # Search configuration
    default_max_results: int = Field(
        default=10,
        description="Default maximum number of search results"
    )
    similarity_threshold: float = Field(
        default=0.7,
        description="Minimum similarity score for search results"
    )
    
    # Storage configuration
    storage_path: Path = Field(
        default=Path("./data/collections"),
        description="Base path for storing collections"
    )
    
    # Default indexer configuration
    default_indexer: str = Field(
        default="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
        description="Default FAISS indexer configuration name"
    )
    
    class Config:
        """Pydantic model configuration."""
        arbitrary_types_allowed = True
    
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """Load configuration from file or use defaults.
        
        Attempts to load configuration from indexed.toml in the current
        directory or specified path. Falls back to defaults if no config
        file is found.
        
        Args:
            config_path: Optional path to indexed.toml file
            
        Returns:
            Config instance with loaded or default values
            
        Examples:
            >>> config = Config.load()  # Load from ./indexed.toml or defaults
            >>> config = Config.load(Path("/path/to/indexed.toml"))
        """
        # TODO: Implement TOML file loading
        # For now, return defaults
        # Future: Load from config_path or find ./indexed.toml
        return cls()
    
    @classmethod
    def from_file(cls, path: str) -> "Config":
        """Load configuration from specific file path.
        
        Args:
            path: Path to configuration file (string)
            
        Returns:
            Config instance loaded from file
            
        Examples:
            >>> config = Config.from_file("./my-config.toml")
        """
        return cls.load(Path(path))
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to TOML file.
        
        Saves current configuration to indexed.toml in the current directory
        or to the specified path.
        
        Args:
            path: Optional path to save configuration file
                 (defaults to ./indexed.toml)
                 
        Examples:
            >>> config = Config.load()
            >>> config.chunk_size = 1024
            >>> config.save()  # Saves to ./indexed.toml
        """
        # TODO: Implement TOML file saving
        # For now, pass (will be implemented in next iteration)
        save_path = path or Path("./indexed.toml")
        pass
    
    def pretty_print(self) -> str:
        """Generate a formatted string representation of the configuration.
        
        Returns:
            Formatted string showing all configuration values
            
        Examples:
            >>> config = Config.load()
            >>> print(config.pretty_print())
        """
        lines = ["Configuration:"]
        
        # Group related settings
        lines.append("\nEmbedding:")
        lines.append(f"  Model: {self.embedding_model}")
        
        lines.append("\nIndexing:")
        lines.append(f"  Chunk Size: {self.chunk_size}")
        lines.append(f"  Chunk Overlap: {self.chunk_overlap}")
        lines.append(f"  Batch Size: {self.batch_size}")
        lines.append(f"  Default Indexer: {self.default_indexer}")
        
        lines.append("\nSearch:")
        lines.append(f"  Default Max Results: {self.default_max_results}")
        lines.append(f"  Similarity Threshold: {self.similarity_threshold}")
        
        lines.append("\nStorage:")
        lines.append(f"  Path: {self.storage_path}")
        
        return "\n".join(lines)
