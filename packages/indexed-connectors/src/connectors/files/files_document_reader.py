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
from typing import TYPE_CHECKING, Any, Iterator

from loguru import logger

if TYPE_CHECKING:
    from parsing import ParsingModule
    from parsing.schema import ParsedDocument

from .schema import DEFAULT_EXCLUDED_DIRS
from .v1_adapter import V1FormatAdapter


class FilesDocumentReader:
    """Read and parse files from a local directory."""

    def __init__(
        self,
        base_path: str,
        include_patterns: list[str] | None = None,
        fail_fast: bool = False,
        start_from_time: datetime.datetime | None = None,
        specific_files: list[str] | None = None,
        *,
        ocr: bool = True,
        table_structure: bool = True,
        max_tokens: int = 512,
        excluded_dirs: list[str] | None = None,
        respect_gitignore: bool = True,
    ) -> None:
        self.base_path = base_path
        self.include_patterns = include_patterns or ["*"]
        self.fail_fast = fail_fast
        self.start_from_time = start_from_time
        self.specific_files = specific_files
        self._excluded_dirs = frozenset(
            excluded_dirs if excluded_dirs is not None else DEFAULT_EXCLUDED_DIRS
        )
        self._respect_gitignore = respect_gitignore

        # Split include_patterns into positive and negative (! prefix) at init.
        positive = [p for p in self.include_patterns if not p.startswith("!")]
        negative = [p[1:] for p in self.include_patterns if p.startswith("!")]
        self.compiled_include_patterns = [self._compile(p) for p in positive]
        self._compiled_exclude_patterns = [self._compile(p) for p in negative]

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
        if self.specific_files is not None:
            return len(self.specific_files)
        return len(list(self._iter_file_paths()))

    def get_reader_details(self) -> dict:
        return {
            "type": "localFiles",
            "basePath": self.base_path,
            "includePatterns": self.include_patterns,
            "failFast": self.fail_fast,
            "respectGitignore": self._respect_gitignore,
            "excludedDirs": list(self._excluded_dirs),
        }

    def _iter_file_paths(self) -> Iterator[str]:
        """Yield matching file paths.

        If ``specific_files`` is set, iterate only those paths, applying the
        negation patterns from ``include_patterns``. Otherwise walk the full
        directory tree, pruning excluded directories before descending.
        """
        if self.specific_files is not None:
            for full_path in self.specific_files:
                if not os.path.isfile(full_path):
                    continue
                relative_path = os.path.relpath(full_path, self.base_path)
                if not self._is_file_negated(relative_path):
                    yield full_path
            return

        # Accumulate (gitignore_dir, PathSpec) tuples as we descend.
        gitignore_specs: list[tuple[Path, Any]] = []

        for root, dirs, files in os.walk(self.base_path, topdown=True):
            root_path = Path(root)

            # Load .gitignore present in the current directory before pruning.
            if self._respect_gitignore:
                gi_file = root_path / ".gitignore"
                if gi_file.is_file():
                    try:
                        import pathspec as _pathspec

                        lines = gi_file.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()
                        spec = _pathspec.PathSpec.from_lines("gitwildmatch", lines)
                        gitignore_specs.append((root_path, spec))
                    except Exception:
                        pass

            # Prune subdirectories in-place to avoid descending into noise dirs.
            dirs[:] = [
                d
                for d in dirs
                if not self._is_dir_pruned(root_path / d, gitignore_specs)
            ]

            for file_name in files:
                full_path = os.path.join(root, file_name)
                relative_path = os.path.relpath(full_path, self.base_path)

                if (
                    os.path.isfile(full_path)
                    and self._is_file_included(relative_path)
                    and not self._is_file_negated(relative_path)
                    and not self._is_file_gitignored(Path(full_path), gitignore_specs)
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

    def _is_file_negated(self, file_path: str) -> bool:
        """Return True if the file matches any negation (!) pattern."""
        return any(
            pattern.fullmatch(file_path) for pattern in self._compiled_exclude_patterns
        )

    def _is_dir_pruned(
        self, dir_path: Path, gitignore_specs: list[tuple[Path, Any]]
    ) -> bool:
        """Return True if this directory should be excluded before descending."""
        if dir_path.name in self._excluded_dirs:
            return True
        if not self._respect_gitignore:
            return False
        for spec_dir, spec in gitignore_specs:
            try:
                rel = dir_path.relative_to(spec_dir)
            except ValueError:
                continue
            rel_str = rel.as_posix()
            if spec.match_file(rel_str + "/") or spec.match_file(rel_str):
                return True
        return False

    def _is_file_gitignored(
        self, file_path: Path, gitignore_specs: list[tuple[Path, Any]]
    ) -> bool:
        """Return True if this file is matched by any loaded gitignore spec."""
        if not self._respect_gitignore:
            return False
        for spec_dir, spec in gitignore_specs:
            try:
                rel = file_path.relative_to(spec_dir)
            except ValueError:
                continue
            if spec.match_file(rel.as_posix()):
                return True
        return False

    @staticmethod
    def _read_file_modification_time(file_path: str) -> datetime.datetime:
        mod_time = os.path.getmtime(file_path)
        return datetime.datetime.fromtimestamp(mod_time)
