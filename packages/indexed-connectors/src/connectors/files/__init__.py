"""Local Files connector package."""

from .connector import FileSystemConnector
from .schema import FileSystemConfig, LocalFilesConfig

__all__ = ["FileSystemConnector", "FileSystemConfig", "LocalFilesConfig"]

# Register FileSystem connector config spec (best-effort)
try:
    from indexed_config import ConfigService

    ConfigService.instance().register(FileSystemConfig, path="connectors.files")
except Exception:
    pass
