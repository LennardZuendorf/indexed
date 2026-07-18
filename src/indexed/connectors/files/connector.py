"""FileSystem connector for indexing local files.

This connector wraps the FilesDocumentReader (backed by indexed-parsing) and
FilesDocumentConverter to provide a standardized BaseConnector interface.
It also exposes change-tracking methods for incremental indexing.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, List, Literal

from indexed.config import ConfigService, ConfigurationError
from indexed.protocols import ConnectorMetadata, ConnectorRun, Manifest

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
        fail_fast: bool = False,
        *,
        change_tracking: Literal[
            "auto", "git", "content_hash", "mtime", "none"
        ] = "auto",
        ocr_enabled: bool = True,
        table_structure: bool = True,
        code_chunking: bool = True,
        max_chunk_tokens: int = 512,
        excluded_dirs: List[str] | None = None,
        respect_gitignore: bool = True,
    ) -> None:
        config = FileSystemConfig(
            path=path,
            include_patterns=include_patterns or ["*"],
            fail_fast=fail_fast,
            change_tracking=change_tracking,  # type: ignore[arg-type]
            ocr_enabled=ocr_enabled,
            table_structure=table_structure,
            code_chunking=code_chunking,
            max_chunk_tokens=max_chunk_tokens,
            excluded_dirs=excluded_dirs or [],
            respect_gitignore=respect_gitignore,
        )

        self._path = config.path
        self._include_patterns = config.include_patterns
        self._fail_fast = config.fail_fast
        self._config = config

        self._reader = FilesDocumentReader(
            base_path=self._path,
            include_patterns=self._include_patterns,
            fail_fast=self._fail_fast,
            ocr=config.ocr_enabled,
            table_structure=config.table_structure,
            max_tokens=config.max_chunk_tokens,
            excluded_dirs=config.excluded_dirs or None,
            respect_gitignore=config.respect_gitignore,
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
            f"include_patterns={self._include_patterns})"
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
                "description": "Patterns for files to include; prefix with '!' to exclude (e.g. ['*', '!*.pyc'])",
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
    def from_config(cls, config_service: ConfigService) -> "FileSystemConnector":
        config_service.register(FileSystemConfig, path="sources.files")
        provider = config_service.bind()
        cfg = provider.get(FileSystemConfig)

        return cls(
            path=cfg.path,
            include_patterns=cfg.include_patterns,
            fail_fast=cfg.fail_fast,
            change_tracking=cfg.change_tracking,
            ocr_enabled=cfg.ocr_enabled,
            table_structure=cfg.table_structure,
            max_chunk_tokens=cfg.max_chunk_tokens,
            excluded_dirs=cfg.excluded_dirs,
            respect_gitignore=cfg.respect_gitignore,
        )

    @classmethod
    def from_manifest(
        cls, manifest: Manifest, config_service: object, *, storage_path: str
    ) -> ConnectorRun:
        """Rebuild the files reader/converter for an incremental update.

        Loads the change-tracker state from ``storage_path`` and scopes the
        reader to changed files, returning the deletions to prune and a
        ``post_run`` hook that persists the new state. Runtime settings
        (ocr/table/max_tokens) come from the connector's own config defaults,
        matching the previous ``local_files_update_factory`` behavior;
        ``config_service`` is unused for this source.
        """
        rd = manifest.reader.model_dump(by_alias=True)
        base_path = rd.get("basePath")
        if not base_path:
            raise ConfigurationError(
                f"Files manifest for collection '{manifest.collection_name}' is "
                "missing 'basePath'; cannot rebuild connector for incremental update"
            )
        connector = cls(
            path=base_path,
            include_patterns=rd.get("includePatterns") or ["*"],
            fail_fast=rd.get("failFast", False),
            change_tracking=rd.get("changeTracking", "auto"),
            excluded_dirs=rd.get("excludedDirs") or None,
            respect_gitignore=rd.get("respectGitignore", True),
        )

        state = connector.load_state(storage_path)
        if state is not None:
            specific_files: List[str] | None = [
                str(p) for p in connector.get_files_to_process(state)
            ]
            deletions = connector.get_deletions(state)
        else:
            specific_files = None
            deletions = []

        cfg = connector._config
        reader = FilesDocumentReader(
            base_path=connector._path,
            include_patterns=connector._include_patterns,
            fail_fast=connector._fail_fast,
            ocr=cfg.ocr_enabled,
            table_structure=cfg.table_structure,
            max_tokens=cfg.max_chunk_tokens,
            excluded_dirs=cfg.excluded_dirs or None,
            specific_files=specific_files,
            respect_gitignore=cfg.respect_gitignore,
        )

        def _save_state() -> None:
            connector.save_state(storage_path)

        return ConnectorRun(reader, connector.converter, deletions, _save_state)


__all__ = ["FileSystemConnector"]
