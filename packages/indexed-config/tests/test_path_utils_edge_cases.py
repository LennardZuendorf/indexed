"""Additional tests for path_utils to reach 100% coverage."""
from indexed_config.path_utils import delete_by_path


def test_delete_by_path_not_found_key():
    """Test delete_by_path returns False when final key not found."""
    data = {"a": {"b": {"c": 42}}}
    # Key exists but final key doesn't
    assert delete_by_path(data, "a.b.d") is False
    assert data == {"a": {"b": {"c": 42}}}


def test_delete_by_path_deep_merge_edge_case():
    """Test deep_merge with edge case that creates new dict."""
    from indexed_config.path_utils import deep_merge
    
    base = {"a": {"x": 1}}
    overlay = {"a": {"y": 2}}
    result = deep_merge(base, overlay)
    assert result == {"a": {"x": 1, "y": 2}}
    # Original should not be modified
    assert base == {"a": {"x": 1}}



