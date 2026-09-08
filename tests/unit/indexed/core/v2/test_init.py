"""Unit tests for the core.v2 lazy package facade (core-v2/2a)."""

from __future__ import annotations

import pytest


def test_all_exports_resolve() -> None:
    import indexed.core.v2 as v2

    for name in v2.__all__:
        assert getattr(v2, name) is not None


def test_dir_matches_exports() -> None:
    import indexed.core.v2 as v2

    assert set(dir(v2)) == v2._EXPORTS


def test_unknown_attribute_raises() -> None:
    import indexed.core.v2 as v2

    with pytest.raises(AttributeError):
        v2.does_not_exist  # type: ignore[attr-defined]
