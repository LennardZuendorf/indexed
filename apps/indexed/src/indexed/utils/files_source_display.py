"""Shared display helpers for local-files source summaries."""

import os
from connectors.files.schema import DEFAULT_EXCLUDED_DIRS


def find_gitignore_files(base_path: str, max_dirs: int = 200) -> list[str]:
    """Walk base_path and return paths of discovered .gitignore files."""
    excluded = frozenset(DEFAULT_EXCLUDED_DIRS)
    found: list[str] = []
    dirs_visited = 0
    for root, dirs, files in os.walk(base_path, topdown=True):
        dirs_visited += 1
        if dirs_visited > max_dirs:
            break
        if ".gitignore" in files:
            found.append(os.path.join(root, ".gitignore"))
        dirs[:] = [d for d in dirs if d not in excluded]
    return found


def count_gitignore_patterns(gitignore_paths: list[str]) -> int:
    """Count total non-comment, non-empty lines across all .gitignore files."""
    total = 0
    for gi_path in gitignore_paths:
        try:
            for line in open(gi_path, encoding="utf-8", errors="replace"):
                line = line.strip()
                if line and not line.startswith("#"):
                    total += 1
        except OSError:
            pass
    return total


def build_excluded_row_text(
    path: str,
    include_patterns: list[str],
    excluded_dirs: list[str],
    respect_gitignore: bool,
) -> str:
    """Build the display string for the Excluded info row."""
    parts: list[str] = [f"{len(excluded_dirs)} dirs"]

    negation_count = sum(1 for p in include_patterns if p.startswith("!"))
    if negation_count:
        parts.append(
            f"{negation_count} exclusion {'pattern' if negation_count == 1 else 'patterns'}"
        )

    if respect_gitignore:
        gitignore_files = find_gitignore_files(path)
        if gitignore_files:
            file_count = len(gitignore_files)
            pattern_count = count_gitignore_patterns(gitignore_files)
            parts.append(
                f".gitignore ({file_count} {'file' if file_count == 1 else 'files'}, {pattern_count} patterns)"
            )

    return " · ".join(parts)
