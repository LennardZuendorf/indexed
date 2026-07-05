"""Unit tests for the connectors origin guard helper."""

import pytest

from connectors._url_guard import is_same_origin

pytestmark = [pytest.mark.unit, pytest.mark.connectors]


class TestIsSameOrigin:
    def test_identical_urls(self):
        assert is_same_origin(
            "https://acme.example.com/path",
            "https://acme.example.com",
        )

    def test_same_scheme_host_different_path(self):
        assert is_same_origin(
            "https://acme.example.com/secure/attachment/123/file.pdf",
            "https://acme.example.com",
        )

    def test_different_host(self):
        assert not is_same_origin(
            "https://evil.attacker.test/x",
            "https://acme.example.com",
        )

    def test_different_scheme(self):
        assert not is_same_origin(
            "http://acme.example.com/file.pdf",
            "https://acme.example.com",
        )

    def test_scheme_case_insensitive(self):
        assert is_same_origin(
            "HTTPS://acme.example.com/file.pdf",
            "https://acme.example.com",
        )

    def test_host_case_insensitive(self):
        assert is_same_origin(
            "https://ACME.EXAMPLE.COM/file.pdf",
            "https://acme.example.com",
        )

    def test_malformed_url_returns_false(self):
        assert not is_same_origin("not-a-url", "https://acme.example.com")

    def test_hostless_url_returns_false(self):
        assert not is_same_origin("/relative/path", "https://acme.example.com")

    def test_malformed_base_returns_false(self):
        assert not is_same_origin("https://acme.example.com/file.pdf", "not-a-url")

    def test_empty_url_returns_false(self):
        assert not is_same_origin("", "https://acme.example.com")

    def test_default_https_port_matches_implicit_port(self):
        # Explicit :443 vs implicit default port — same origin.
        assert is_same_origin(
            "https://acme.example.com:443/file.pdf",
            "https://acme.example.com",
        )

    def test_default_http_port_matches_implicit_port(self):
        # Explicit :80 vs implicit default port — same origin.
        assert is_same_origin(
            "http://acme.example.com:80/file.pdf",
            "http://acme.example.com",
        )

    def test_non_default_port_is_off_origin(self):
        # A different port is a different service on the same host — refuse creds.
        assert not is_same_origin(
            "https://acme.example.com:8443/file.pdf",
            "https://acme.example.com",
        )
