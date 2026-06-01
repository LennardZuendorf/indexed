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

PYPROJECT = Path("apps/indexed/pyproject.toml")
VERSION_RE = re.compile(r'^(version\s*=\s*")[^"]*(")', re.MULTILINE)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: sync_version.py <tag>", file=sys.stderr)
        sys.exit(1)

    raw_tag = sys.argv[1]
    version = raw_tag.lstrip("v")

    if not SEMVER_RE.match(version):
        print(f"[sync_version] '{raw_tag}' is not a semver tag — skipping.")
        return

    content = PYPROJECT.read_text(encoding="utf-8")
    match = VERSION_RE.search(content)
    if not match:
        print(
            f"[sync_version] Could not find version field in {PYPROJECT}",
            file=sys.stderr,
        )
        sys.exit(1)

    current = match.group(0).split('"')[1]
    if current == version:
        print(f"[sync_version] Version already {version} — no change needed.")
        return

    updated = VERSION_RE.sub(rf"\g<1>{version}\g<2>", content, count=1)
    PYPROJECT.write_text(updated, encoding="utf-8")
    print(f"[sync_version] Updated version: {current} → {version}")


if __name__ == "__main__":
    main()
