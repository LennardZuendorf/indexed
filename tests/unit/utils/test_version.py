"""Tests for the installed-distribution version helper."""

from importlib.metadata import version as dist_version

from indexed.utils.version import DIST_NAME, installed_version

MISSING = "this-package-does-not-exist-xyz"


def test_default_dist_is_indexed_sh() -> None:
    """The CLI's own distribution is the default lookup."""
    assert DIST_NAME == "indexed-sh"
    assert installed_version() == dist_version("indexed-sh")


def test_returns_version_of_named_distribution() -> None:
    """Any installed distribution resolves to its metadata version."""
    assert installed_version("typer") == dist_version("typer")


def test_missing_distribution_falls_back_to_unknown() -> None:
    """A bare source tree must not raise — it answers 'unknown'."""
    assert installed_version(MISSING) == "unknown"


def test_missing_distribution_honours_custom_fallback() -> None:
    """Callers with their own vocabulary pass their own fallback string."""
    assert installed_version(MISSING, fallback="not installed") == "not installed"
