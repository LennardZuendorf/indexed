"""FileSystem connector for indexing local files.

This connector wraps the FilesDocumentReader (backed by indexed-parsing) and
FilesDocumentConverter to provide a standardized BaseConnector interface.
It also exposes change-tracking methods for incremental indexing.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, List

from core.v1.connectors.metadata import ConnectorMetadata

from .change_tracker import ChangeTracker, FileChange, IndexState
from .files_document_converter import FilesDocumentConverter
from .files_document_reader import FilesDocumentReader
from .schema import FileSystemConfig


class FileSystemConnector:
    """Connector for local file system documents.

    Discovers and indexes files from a local directory, supporting various
    file formats through the indexed-parsing module (Docling + tree-sitter).

    Attributes:
        reader: FilesDocumentReader instance for discovering and reading files
        converter: FilesDocumentConverter instance for format conversion
    """

    META: ClassVar[ConnectorMetadata] = ConnectorMetadata(
        name="files",
        display_name="Local Files",
        description="Index documents from local filesystem",
        config_class=FileSystemConfig,
        version="2.0.0",
        min_core_version="1.0.0",
        example="indexed index create --type files --name docs",
    )

    def __init__(
        self,
        path: str,
        include_patterns: List[str] | None = None,
        exclude_patterns: List[str] | None = None,
        fail_fast: bool = False,
        *,
        change_tracking: str = "auto",
        ocr_enabled: bool = True,
        table_structure: bool = True,
        code_chunking: bool = True,
        max_chunk_tokens: int = 512,
        excluded_extensions: List[str] | None = None,
    ) -> None:
        config = FileSystemConfig(
            path=path,
            include_patterns=include_patterns or ["*"],
            exclude_patterns=exclude_patterns or [],
            fail_fast=fail_fast,
            change_tracking=change_tracking,  # type: ignore[arg-type]
            ocr_enabled=ocr_enabled,
            table_structure=table_structure,
            code_chunking=code_chunking,
            max_chunk_tokens=max_chunk_tokens,
            excluded_extensions=excluded_extensions or [],
        )

        self._path = config.path
        self._include_patterns = config.include_patterns
        self._exclude_patterns = config.exclude_patterns
        self._fail_fast = config.fail_fast
        self._config = config

        self._reader = FilesDocumentReader(
            base_path=self._path,
            include_patterns=self._include_patterns,
            exclude_patterns=self._exclude_patterns,
            fail_fast=self._fail_fast,
            ocr=config.ocr_enabled,
            table_structure=config.table_structure,
            max_tokens=config.max_chunk_tokens,
            excluded_extensions=config.excluded_extensions or None,
        )
        self._converter = FilesDocumentConverter()
        self._change_tracker = ChangeTracker(
            base_path=self._path,
            strategy=config.change_tracking,
        )

    # -- BaseConnector protocol -------------------------------------------

    @property
    def reader(self) -> FilesDocumentReader:
        return self._reader

    @property
    def converter(self) -> FilesDocumentConverter:
        return self._converter

    @property
    def connector_type(self) -> str:
        return "localFiles"

    def __repr__(self) -> str:
        return (
            f"FileSystemConnector(path='{self._path}', "
            f"include_patterns={self._include_patterns}, "
            f"exclude_patterns={self._exclude_patterns})"
        )

    # -- change tracking --------------------------------------------------

    def get_changes(self, state: IndexState | None = None) -> list[FileChange]:
        """Detect changes since *state* (or treat everything as new)."""
        file_paths = list(self._reader._iter_file_paths())
        return self._change_tracker.detect_changes(file_paths, state or IndexState())

    def get_files_to_process(self, state: IndexState | None = None) -> list[Path]:
        """Return paths of added/modified files (filtered through patterns)."""
        changes = self.get_changes(state)
        return [
            Path(self._path) / ch.path
            for ch in changes
            if ch.status in ("added", "modified")
        ]

    def get_deletions(self, state: IndexState | None = None) -> list[str]:
        """Return relative paths of deleted files (= document IDs)."""
        changes = self.get_changes(state)
        return [ch.path for ch in changes if ch.status == "deleted"]

    def build_state(self) -> IndexState:
        """Build a fresh state snapshot from current files."""
        file_paths = list(self._reader._iter_file_paths())
        return self._change_tracker.build_state(file_paths)

    def save_state(self, storage_path: str) -> None:
        state = self.build_state()
        state_file = Path(storage_path) / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(state.to_json())

    def load_state(self, storage_path: str) -> IndexState | None:
        state_file = Path(storage_path) / "state.json"
        if state_file.exists():
            return IndexState.from_json(state_file.read_text())
        return None

    # -- config integration -----------------------------------------------

    @classmethod
    def config_spec(cls) -> dict:
        return {
            "path": {
                "type": "str",
                "required": True,
                "secret": False,
                "description": "Root directory path to scan for files",
            },
            "include_patterns": {
                "type": "list",
                "required": False,
                "secret": False,
                "default": ["*"],
                "description": "List of patterns for files to include (glob or regex)",
            },
            "exclude_patterns": {
                "type": "list",
                "required": False,
                "secret": False,
                "default": [],
                "description": "List of regex patterns for files to exclude",
            },
            "fail_fast": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": False,
                "description": "Stop indexing on first error (True) or continue (False)",
            },
            "change_tracking": {
                "type": "str",
                "required": False,
                "secret": False,
                "default": "auto",
                "description": "Change detection strategy (auto/git/content_hash/mtime/none)",
            },
            "ocr_enabled": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": True,
                "description": "Enable OCR for scanned documents",
            },
            "table_structure": {
                "type": "bool",
                "required": False,
                "secret": False,
                "default": True,
                "description": "Enable table structure recognition",
            },
            "max_chunk_tokens": {
                "type": "int",
                "required": False,
                "secret": False,
                "default": 512,
                "description": "Maximum tokens per chunk",
            },
        }

    @classmethod
    def from_config(cls, config_service: object) -> "FileSystemConnector":
        config_service.register(FileSystemConfig, path="sources.files")  # type: ignore[union-attr]
        provider = config_service.bind()  # type: ignore[union-attr]
        cfg = provider.get(FileSystemConfig)

        return cls(
            path=cfg.path,
            include_patterns=cfg.include_patterns,
            exclude_patterns=cfg.exclude_patterns,
            fail_fast=cfg.fail_fast,
            change_tracking=cfg.change_tracking,
            ocr_enabled=cfg.ocr_enabled,
            table_structure=cfg.table_structure,
            max_chunk_tokens=cfg.max_chunk_tokens,
            excluded_extensions=cfg.excluded_extensions,
        )


__all__ = ["FileSystemConnector"]
