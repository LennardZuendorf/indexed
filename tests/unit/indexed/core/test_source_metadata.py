"""The shared reader-block projection (#108 slice A).

One allowlist for both engines: only `basePath`, the URL keys and `query` may
reach the output — every other reader key (a connector's own config) must not.
"""

import pytest

from indexed.core.source_metadata import SOURCE_KEYS, source_metadata

pytestmark = pytest.mark.unit


class TestSourceMetadataAllowlist:
    def test_jira_reader_maps_url_and_query(self):
        assert source_metadata(
            {
                "type": "jira",
                "baseUrl": "https://example.atlassian.net",
                "query": "project = ABC",
            }
        ) == {
            "source_path": None,
            "source_url": "https://example.atlassian.net",
            "source_query": "project = ABC",
        }

    def test_files_reader_maps_base_path(self):
        assert source_metadata({"type": "localFiles", "basePath": "/home/me/docs"}) == {
            "source_path": "/home/me/docs",
            "source_url": None,
            "source_query": None,
        }

    def test_url_falls_back_through_graphql_and_host(self):
        assert (
            source_metadata({"type": "github", "graphqlUrl": "https://g/q"})[
                "source_url"
            ]
            == "https://g/q"
        )
        assert (
            source_metadata({"type": "outline", "host": "https://o"})["source_url"]
            == "https://o"
        )

    def test_base_url_wins_over_the_fallbacks(self):
        assert (
            source_metadata(
                {"baseUrl": "https://a", "graphqlUrl": "https://b", "host": "https://c"}
            )["source_url"]
            == "https://a"
        )

    def test_unknown_reader_keys_never_leak(self):
        """The allowlist is the contract: config keys stay out even though they
        are not secrets."""
        projected = source_metadata(
            {
                "type": "jira",
                "baseUrl": "https://example.atlassian.net",
                "includePatterns": ["**/*.md"],
                "collectionIds": [42],
                "token": "should-never-be-projected",
            }
        )

        assert set(projected) == set(SOURCE_KEYS)

    def test_missing_none_and_empty_degrade_to_none(self):
        for reader in (
            None,
            {},
            {"basePath": None, "baseUrl": "", "query": "   "},
            {"basePath": [], "baseUrl": {}, "query": False},
        ):
            assert source_metadata(reader) == {
                "source_path": None,
                "source_url": None,
                "source_query": None,
            }

    def test_non_mapping_reader_is_tolerated(self):
        assert source_metadata("jira")["source_url"] is None  # type: ignore[arg-type]

    def test_scalar_values_are_coerced_to_text(self):
        assert source_metadata({"host": 8080, "query": 7}) == {
            "source_path": None,
            "source_url": "8080",
            "source_query": "7",
        }

    def test_text_is_trimmed(self):
        assert source_metadata({"basePath": "  /docs  "})["source_path"] == "/docs"
