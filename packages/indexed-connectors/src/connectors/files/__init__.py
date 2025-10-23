"""Local Files connector package."""

from .connector import FileSystemConnector

__all__ = ["FileSystemConnector"]

# Register FileSystem connector config spec (best-effort)
try:
    from indexed_config import ConfigService
    from .schema import FileSystemConfig

    ConfigService.instance().register(FileSystemConfig, path="connectors.files")
except Exception:
    pass
