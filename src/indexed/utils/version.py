"""Installed-distribution version lookup.

``pyproject.toml`` declares ``dynamic = ["version"]`` and hatch-vcs writes the
version from the git tag at build time, so the *only* authoritative answer at
runtime is the installed metadata — there is no version string in the source
tree to read. The ``importlib.metadata`` import stays inside the function:
importing it pulls in ``email``/``csv``/``zipfile`` and costs the CLI several
milliseconds on every start, and only a handful of code paths ever ask.
"""

from __future__ import annotations

DIST_NAME = "indexed-sh"


def installed_version(dist: str = DIST_NAME, fallback: str = "unknown") -> str:
    """Return the installed version of *dist*, or *fallback* when it is absent.

    A bare source checkout (no installed distribution metadata) resolves to
    *fallback* rather than raising, so callers surface a value instead of a
    traceback.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(dist)
    except PackageNotFoundError:
        return fallback


__all__ = ["DIST_NAME", "installed_version"]
