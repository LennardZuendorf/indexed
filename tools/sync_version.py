#!/usr/bin/env python3
# Sync apps/indexed/pyproject.toml version with a release tag.
#
# Usage:
#   uv run python tools/sync_version.py <tag>
#
# The tag may include or omit the 'v' prefix (e.g. 'v0.1.0' or '0.1.0').
# If the tag is not a valid semver string the script exits successfully with
# a warning so that workflow_dispatch runs on branch refs are not blocked.

import re
import sys
from pathlib import Path

PYPROJECT: Path = Path("apps/indexed/pyproject.toml")
VERSION_RE: re.Pattern[str] = re.compile(r'^(version\s*=\s*")[^"]*(")', re.MULTILINE)
SEMVER_RE: re.Pattern[str] = re.compile(r"^\d+\.\d+\.\d+$")


def parse_version(raw_tag: str) -> str | None:
    """Return normalized semver from a tag, or None if not valid."""
    version = raw_tag[1:] if raw_tag.startswith("v") else raw_tag
    if not SEMVER_RE.match(version):
        return None
    return version


def sync_version(raw_tag: str, pyproject: Path = PYPROJECT) -> bool:
    """Update pyproject version from tag. Returns True if file was changed."""
    version = parse_version(raw_tag)
    if version is None:
        print(f"[sync_version] '{raw_tag}' is not a semver tag — skipping.")
        return False

    content = pyproject.read_text(encoding="utf-8")
    match = VERSION_RE.search(content)
    if not match:
        print(
            f"[sync_version] Could not find version field in {pyproject}",
            file=sys.stderr,
        )
        sys.exit(1)

    current = match.group(0).split('"')[1]
    if current == version:
        print(f"[sync_version] Version already {version} — no change needed.")
        return False

    updated = VERSION_RE.sub(rf"\g<1>{version}\g<2>", content, count=1)
    pyproject.write_text(updated, encoding="utf-8")
    print(f"[sync_version] Updated version: {current} → {version}")
    return True


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: sync_version.py <tag>", file=sys.stderr)
        sys.exit(1)

    sync_version(sys.argv[1])


if __name__ == "__main__":
    main()
