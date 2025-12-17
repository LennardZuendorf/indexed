"""Tests for path_utils module."""
import pytest
from indexed_config.path_utils import (
    get_by_path,
    set_by_path,
    delete_by_path,
    deep_merge,
)


def test_get_by_path_basic():
    """Test basic get_by_path functionality."""
    data = {"a": {"b": {"c": 42}}}
    assert get_by_path(data, "a.b.c") == 42
    assert get_by_path(data, "a.b") == {"c": 42}
    assert get_by_path(data, "a") == {"b": {"c": 42}}


def test_get_by_path_not_found():
    """Test get_by_path returns default when path not found."""
    data = {"a": {"b": 42}}
    assert get_by_path(data, "a.b.c") is None
    assert get_by_path(data, "a.b.c", default="missing") == "missing"
    assert get_by_path(data, "x.y") is None


def test_get_by_path_non_mapping():
    """Test get_by_path handles non-mapping values."""
    data = {"a": {"b": "not_a_dict"}}
    assert get_by_path(data, "a.b.c") is None
    assert get_by_path(data, "a.b.c", default="default") == "default"


def test_get_by_path_empty_path():
    """Test get_by_path with empty path."""
    data = {"a": 42}
    assert get_by_path(data, "") == data


def test_set_by_path_basic():
    """Test basic set_by_path functionality."""
    data = {}
    set_by_path(data, "a.b.c", 42)
    assert data == {"a": {"b": {"c": 42}}}


def test_set_by_path_existing():
    """Test set_by_path updates existing values."""
    data = {"a": {"b": {"c": 1}}}
    set_by_path(data, "a.b.c", 42)
    assert data == {"a": {"b": {"c": 42}}}


def test_set_by_path_creates_intermediate():
    """Test set_by_path creates intermediate dictionaries."""
    data = {"a": {}}
    set_by_path(data, "a.b.c", 42)
    assert data == {"a": {"b": {"c": 42}}}


def test_set_by_path_overwrites_non_dict():
    """Test set_by_path overwrites non-dict intermediate values."""
    data = {"a": {"b": "not_a_dict"}}
    set_by_path(data, "a.b.c", 42)
    assert data == {"a": {"b": {"c": 42}}}


def test_set_by_path_empty_path():
    """Test set_by_path raises error for empty path."""
    data = {}
    with pytest.raises(ValueError, match="dot_path must not be empty"):
        set_by_path(data, "", 42)


def test_delete_by_path_basic():
    """Test basic delete_by_path functionality."""
    data = {"a": {"b": {"c": 42}}}
    assert delete_by_path(data, "a.b.c") is True
    assert data == {"a": {"b": {}}}


def test_delete_by_path_not_found():
    """Test delete_by_path returns False when path not found."""
    data = {"a": {"b": 42}}
    assert delete_by_path(data, "a.b.c") is False
    assert delete_by_path(data, "x.y") is False
    assert data == {"a": {"b": 42}}


def test_delete_by_path_non_mapping():
    """Test delete_by_path returns False when intermediate is not a mapping."""
    data = {"a": {"b": "not_a_dict"}}
    assert delete_by_path(data, "a.b.c") is False
    assert data == {"a": {"b": "not_a_dict"}}


def test_delete_by_path_empty_path():
    """Test delete_by_path returns False for empty path."""
    data = {"a": 42}
    assert delete_by_path(data, "") is False


def test_deep_merge_basic():
    """Test basic deep_merge functionality."""
    base = {"a": 1, "b": 2}
    overlay = {"b": 3, "c": 4}
    result = deep_merge(base, overlay)
    assert result == {"a": 1, "b": 3, "c": 4}
    # Original base should not be modified
    assert base == {"a": 1, "b": 2}


def test_deep_merge_nested():
    """Test deep_merge with nested dictionaries."""
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    overlay = {"a": {"y": 20, "z": 30}, "c": 4}
    result = deep_merge(base, overlay)
    assert result == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3, "c": 4}


def test_deep_merge_overwrites_dict():
    """Test deep_merge overwrites dict with non-dict."""
    base = {"a": {"x": 1}}
    overlay = {"a": 42}
    result = deep_merge(base, overlay)
    assert result == {"a": 42}


def test_deep_merge_overwrites_non_dict():
    """Test deep_merge overwrites non-dict with dict."""
    base = {"a": 42}
    overlay = {"a": {"x": 1}}
    result = deep_merge(base, overlay)
    assert result == {"a": {"x": 1}}



