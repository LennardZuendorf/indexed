"""File-system document reader.

Discovers files under a directory tree and parses them via ``indexed-parsing``.
The primary output is ``ParsedDocument``; a legacy ``read_all_documents()``
method is kept for backward compatibility with the v1 core contract.
"""

from __future__ import annotations

import datetime
import fnmatch
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

from loguru import logger

if TYPE_CHECKING:
    from parsing import ParsingModule
    from parsing.schema import ParsedDocument

from .schema import DEFAULT_EXCLUDED_EXTENSIONS
from .v1_adapter import V1FormatAdapter


class FilesDocumentReader:
    """Read and parse files from a local directory."""

    def __init__(
        self,
        base_path: str,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        fail_fast: bool = False,
        start_from_time: datetime.datetime | None = None,
        *,
        ocr: bool = True,
        table_structure: bool = True,
        max_tokens: int = 512,
        excluded_extensions: list[str] | None = None,
    ) -> None:
        self.base_path = base_path
        self.include_patterns = include_patterns or ["*"]
        self.exclude_patterns = exclude_patterns or []
        self.compiled_include_patterns = [
            self._compile(p) for p in self.include_patterns
        ]
        self.compiled_exclude_patterns = [
            self._compile(p) for p in self.exclude_patterns
        ]
        self.fail_fast = fail_fast
        self.start_from_time = start_from_time
        self._excluded_extensions = frozenset(
            excluded_extensions or DEFAULT_EXCLUDED_EXTENSIONS
        )

        # Lazy-init parsing module on first use
        self._parsing: ParsingModule | None = None
        self._ocr = ocr
        self._table_structure = table_structure
        self._max_tokens = max_tokens

    @staticmethod
    def _compile(pattern: str) -> re.Pattern[str]:
        """Compile a pattern as regex, falling back to glob."""
        try:
            return re.compile(pattern)
        except re.error:
            return re.compile(fnmatch.translate(pattern))

    @property
    def parsing(self) -> ParsingModule:
        """Lazily create the parsing module."""
        if self._parsing is None:
            from parsing import ParsingModule as _ParsingModule

            self._parsing = _ParsingModule(
                ocr=self._ocr,
                table_structure=self._table_structure,
                max_tokens=self._max_tokens,
            )
        return self._parsing

    # -- primary API (new) -----------------------------------------------

    def read_all_parsed(self) -> Iterator[ParsedDocument]:
        """Yield a ``ParsedDocument`` for every matching file."""
        success_files: list[str] = []
        error_files: list[str] = []

        for file_path in self._iter_file_paths():
            try:
                doc = self.parsing.parse(Path(file_path))
                # Populate modified_time in metadata
                doc.metadata["modified_time"] = self._read_file_modification_time(
                    file_path
                ).isoformat()

                if doc.metadata.get("error"):
                    error_files.append(file_path)
                else:
                    success_files.append(file_path)

                yield doc
            except Exception as exc:
                error_files.append(file_path)
                if self.fail_fast:
                    raise RuntimeError(f"Error reading file {file_path}") from exc
                logger.error("Error reading file {}: {}", file_path, exc)

        logger.info("Parsed {} files successfully", len(success_files))
        if error_files:
            logger.warning(
                "Could not parse {} file(s):\n{}",
                len(error_files),
                "\n".join(f"  - {f}" for f in error_files),
            )

    # -- backward-compat v1 API ------------------------------------------

    def read_all_documents(self) -> Iterator[dict]:
        """Yield v1-format dicts — backward compatible with core v1.

        Each dict has keys: ``fileRelativePath``, ``fileFullPath``,
        ``modifiedTime``, ``content``.
        """
        for parsed in self.read_all_parsed():
            yield V1FormatAdapter.reader_output(parsed, self.base_path)

    # -- helpers ----------------------------------------------------------

    def get_number_of_documents(self) -> int:
        return len(list(self._iter_file_paths()))

    def get_reader_details(self) -> dict:
        return {
            "type": "localFiles",
            "basePath": self.base_path,
            "includePatterns": self.include_patterns,
            "excludePatterns": self.exclude_patterns,
            "failFast": self.fail_fast,
        }

    def _iter_file_paths(self) -> Iterator[str]:
        """Walk the directory and yield matching file paths."""
        for root, _, files in os.walk(self.base_path):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(full_path, self.base_path)

                if (
                    os.path.isfile(full_path)
                    and self._is_file_included(relative_path)
                    and not any(
                        relative_path.endswith(ext) for ext in self._excluded_extensions
                    )
                    and not self._is_file_excluded(relative_path)
                    and (
                        self.start_from_time is None
                        or self._read_file_modification_time(full_path)
                        >= self.start_from_time
                    )
                ):
                    yield full_path

    def _is_file_included(self, file_path: str) -> bool:
        return any(
            pattern.fullmatch(file_path) for pattern in self.compiled_include_patterns
        )

    def _is_file_excluded(self, file_path: str) -> bool:
        return any(
            pattern.fullmatch(file_path) for pattern in self.compiled_exclude_patterns
        )

    @staticmethod
    def _read_file_modification_time(file_path: str) -> datetime.datetime:
        mod_time = os.path.getmtime(file_path)
        return datetime.datetime.fromtimestamp(mod_time)
