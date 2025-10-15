"""Configuration settings schema using pydantic-settings.

Loads settings from indexed.toml, .env, and environment variables.
"""

import os
from typing import Optional, List, Dict, Callable
from pathlib import Path
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


# Simple .env loader cache
_DOTENV_CACHE: Optional[Dict[str, str]] = None


def _load_dotenv_file() -> Dict[str, str]:
    """Load .env key/values from project root without exporting to os.environ."""
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return _DOTENV_CACHE
    env_path = Path(".env")
    values: Dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            values[key] = val
    _DOTENV_CACHE = values
    return values


def _get_env_var(var_name: str) -> Optional[str]:
    """Get env var from process or .env file (non-exported)."""
    val = os.getenv(var_name)
    if val is not None:
        return val
    return _load_dotenv_file().get(var_name)


def indexed_toml_source(settings_cls):
    """Custom TOML source for indexed.toml in project root."""

    class FilteredTomlConfigSettingsSource(TomlConfigSettingsSource):
        def _read_file(self, file_path):
            """Read TOML file and filter out profiles and unknown root keys."""
            data = super()._read_file(file_path)
            if not data:
                return data
            # Remove profiles section to avoid validation errors
            if "profiles" in data:
                data = {k: v for k, v in data.items() if k != "profiles"}
            # Whitelist known top-level sections only
            allowed = {
                "paths",
                "search",
                "index",
                "sources",
                "mcp",
                "performance",
                "flags",
                "logging",
            }
            data = {k: v for k, v in data.items() if k in allowed}
            return data

    return FilteredTomlConfigSettingsSource(
        settings_cls, toml_file=Path("indexed.toml")
    )


def _filter_known_top_level_source(source: Callable) -> Callable:
    allowed = {
        "paths",
        "search",
        "index",
        "sources",
        "mcp",
        "performance",
        "flags",
        "logging",
    }

    def _inner(settings) -> Dict[str, any]:
        data = source(settings)
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items() if k in allowed}

    return _inner


class PathsSettings(BaseModel):
    """File system paths configuration."""

    collections_dir: str = Field(
        default="./data/collections", description="Directory for collections storage"
    )
    caches_dir: str = Field(
        default="./data/caches", description="Directory for document caches"
    )
    temp_dir: str = Field(default="./tmp", description="Temporary files directory")


class SearchSettings(BaseModel):
    """Search behavior configuration."""

    max_docs: int = Field(default=10, ge=1, description="Maximum documents to return")
    max_chunks: Optional[int] = Field(
        default=30, ge=1, description="Maximum chunks to return"
    )
    include_full_text: bool = Field(
        default=False, description="Include full document text in results"
    )
    include_all_chunks: bool = Field(
        default=False, description="Include all document chunks"
    )
    include_matched_chunks: bool = Field(
        default=False, description="Include only matched chunks"
    )
    score_threshold: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Minimum similarity score"
    )


class IndexSettings(BaseModel):
    """Indexing and embeddings configuration."""

    default_indexer: str = Field(
        default="indexer_FAISS_IndexFlatL2__embeddings_all-MiniLM-L6-v2",
        description="Default indexer to use for collections",
    )
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Sentence transformer model for embeddings",
    )
    embedding_batch_size: int = Field(
        default=64, ge=1, description="Batch size for embedding generation"
    )
    use_gpu: bool = Field(
        default=False, description="Use GPU for embeddings if available"
    )


class FilesSourceSettings(BaseModel):
    """Local files source configuration."""

    base_path: Optional[str] = Field(
        default=None, description="Base directory path for file indexing"
    )
    include_patterns: List[str] = Field(
        default_factory=list, description="File patterns to include"
    )
    exclude_patterns: List[str] = Field(
        default_factory=list, description="File patterns to exclude"
    )
    follow_symlinks: bool = Field(default=False, description="Follow symbolic links")
    max_file_size_mb: int = Field(
        default=50, ge=1, description="Maximum file size in MB"
    )

    @property
    def is_ready(self) -> bool:
        """Check if files source is ready for use."""
        return self.base_path is not None and Path(self.base_path).exists()


class JiraCloudSourceSettings(BaseModel):
    """Jira Cloud source configuration."""

    base_url: Optional[str] = Field(default=None, description="Jira Cloud base URL")
    email: Optional[str] = Field(
        default=None, description="Jira Cloud email for authentication"
    )
    api_token_env: str = Field(
        default="JIRA_API_TOKEN",
        description="Environment variable containing API token",
    )
    jql: str = Field(
        default="project = CURRENT", description="JQL query for issue selection"
    )
    max_results: int = Field(
        default=100, ge=1, description="Maximum results per API call"
    )
    timeout_sec: int = Field(default=30, ge=1, description="Request timeout in seconds")

    @property
    def is_ready(self) -> bool:
        """Check if Jira Cloud source is ready for use."""
        return (
            self.base_url is not None
            and self.email is not None
            and _get_env_var(self.api_token_env) is not None
        )


class ConfluenceCloudSourceSettings(BaseModel):
    """Confluence Cloud source configuration."""

    base_url: Optional[str] = Field(
        default=None, description="Confluence Cloud base URL"
    )
    email: Optional[str] = Field(
        default=None, description="Confluence Cloud email for authentication"
    )
    api_token_env: str = Field(
        default="CONFLUENCE_API_TOKEN",
        description="Environment variable containing API token",
    )
    cql: str = Field(
        default="space = DEV", description="CQL query for content selection"
    )
    include_comments: bool = Field(
        default=False, description="Include page comments in indexing"
    )
    page_limit: int = Field(default=100, ge=1, description="Maximum pages per API call")
    timeout_sec: int = Field(default=30, ge=1, description="Request timeout in seconds")

    @property
    def is_ready(self) -> bool:
        """Check if Confluence Cloud source is ready for use."""
        return (
            self.base_url is not None
            and self.email is not None
            and _get_env_var(self.api_token_env) is not None
        )


class SourcesSettings(BaseModel):
    """All source configurations."""

    files: FilesSourceSettings = Field(default_factory=FilesSourceSettings)
    jira_cloud: JiraCloudSourceSettings = Field(default_factory=JiraCloudSourceSettings)
    confluence_cloud: ConfluenceCloudSourceSettings = Field(
        default_factory=ConfluenceCloudSourceSettings
    )


class MCPSettings(BaseModel):
    """MCP server configuration."""

    host: str = Field(default="localhost", description="MCP server host")
    port: int = Field(default=8000, ge=1, le=65535, description="MCP server port")
    log_level: str = Field(default="WARNING", description="MCP server log level")
    enable_async_pool: bool = Field(
        default=False, description="Enable async processing pool"
    )
    mcp_json_output: bool = Field(
        default=True, description="Default JSON output for MCP responses"
    )


class PerformanceSettings(BaseModel):
    """Performance and caching configuration."""

    enable_cache: bool = Field(default=True, description="Enable search result caching")
    cache_max_entries: int = Field(
        default=32, ge=1, description="Maximum cache entries"
    )
    log_sqlite_queries: bool = Field(
        default=False, description="Log SQLite queries for debugging"
    )


class FlagsSettings(BaseModel):
    """Feature flags and experimental settings."""

    enable_profiles: bool = Field(
        default=True, description="Enable configuration profiles"
    )
    warn_on_legacy_cli: bool = Field(
        default=True, description="Warn when using legacy CLI commands"
    )
    cli_json_output: bool = Field(
        default=False, description="Default JSON output for CLI when flag not set"
    )


class LoggingSettings(BaseModel):
    """Central logging configuration."""

    level: str = Field(default="WARNING", description="Global log level")
    as_json: bool = Field(default=False, description="Emit JSON logs when true")


class IndexedSettings(BaseSettings):
    """Main configuration schema for Indexed application.

    Loads from:
    1. CLI/MCP overrides (highest precedence)
    2. Environment variables (INDEXED__*)
    3. .env file
    4. indexed.toml (project root)
    5. Built-in defaults (lowest precedence)
    """

    model_config = SettingsConfigDict(
        env_prefix="INDEXED__",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    # Configuration sections
    paths: PathsSettings = Field(default_factory=PathsSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    index: IndexSettings = Field(default_factory=IndexSettings)
    sources: SourcesSettings = Field(default_factory=SourcesSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    performance: PerformanceSettings = Field(default_factory=PerformanceSettings)
    flags: FlagsSettings = Field(default_factory=FlagsSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Customize settings sources with proper precedence."""
        return (
            init_settings,  # CLI/runtime overrides (highest precedence)
            env_settings,  # Environment variables
            dotenv_settings,  # .env file
            indexed_toml_source(settings_cls),  # indexed.toml
            # Built-in defaults are automatic (lowest precedence)
        )

    @model_validator(mode="after")
    def validate_configuration(self):
        """Cross-field validation for configuration consistency."""
        # Validate paths exist if specified
        if self.paths.collections_dir and not Path(self.paths.collections_dir).exists():
            Path(self.paths.collections_dir).mkdir(parents=True, exist_ok=True)

        if self.paths.caches_dir and not Path(self.paths.caches_dir).exists():
            Path(self.paths.caches_dir).mkdir(parents=True, exist_ok=True)

        if self.paths.temp_dir and not Path(self.paths.temp_dir).exists():
            Path(self.paths.temp_dir).mkdir(parents=True, exist_ok=True)

        return self
