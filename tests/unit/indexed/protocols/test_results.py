"""The result contract's declaration must match the payload it describes."""

from indexed.protocols import results


def test_source_type_is_optional():
    """Dropped when the manifest does not say — so it cannot be a required key."""
    assert "source_type" not in results.DocumentResult.__required_keys__
    assert "source_type" in results.DocumentResult.__optional_keys__


def test_hit_and_locator_required_keys():
    assert results.Hit.__required_keys__ == {"relevance", "score", "locator", "text"}
    assert results.Locator.__required_keys__ == {"kind"}
