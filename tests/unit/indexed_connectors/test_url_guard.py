"""Unit tests for the connectors origin guard helper."""

import pytest

from connectors._url_guard import _client_host, is_cloud_host, is_same_origin

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

    def test_backslash_authority_differential_is_off_origin(self):
        # C3: urlsplit sees host "good.com", but urllib3 sends creds to
        # "evil.com" — the guard must fail closed on this parser differential.
        assert not is_same_origin("https://evil.com\\@good.com/x", "https://good.com")

    def test_trailing_dot_fqdn_matches(self):
        # C3: a legitimate trailing-dot FQDN must still match its bare form.
        assert is_same_origin("https://acme.example.com.", "https://acme.example.com")


class TestClientHost:
    def test_strips_credentials_and_port(self):
        assert _client_host("https://user:pass@acme.example.com:443/x") == (
            "acme.example.com"
        )

    def test_backslash_authority_yields_attacker_host(self):
        # The core of C3: everything before the first backslash is the real
        # authority the HTTP client connects to.
        assert _client_host("https://evil.com\\@good.com/x") == "evil.com"

    def test_trailing_dot_stripped(self):
        assert _client_host("https://good.com.") == "good.com"

    def test_no_scheme_delimiter_returns_none(self):
        assert _client_host("not-a-url") is None


class TestIsCloudHost:
    def test_plain_cloud_url(self):
        assert is_cloud_host("https://acme.atlassian.net")

    def test_cloud_url_with_wiki_path(self):
        # The host is parsed before the check, so a Confluence Cloud URL with a
        # trailing /wiki path is still recognized as Cloud.
        assert is_cloud_host("https://acme.atlassian.net/wiki")

    def test_cloud_url_trailing_slash_and_port(self):
        assert is_cloud_host("https://acme.atlassian.net:443/")

    def test_scheme_less_bare_host(self):
        # Backwards compatibility with a raw endswith on a scheme-less host.
        assert is_cloud_host("acme.atlassian.net")

    def test_server_url_is_not_cloud(self):
        assert not is_cloud_host("https://jira.example.com")

    def test_substring_injection_in_path_is_not_cloud(self):
        # The core regression: a raw ``url.endswith(".atlassian.net")`` would
        # treat this attacker URL as Cloud and send credentials to evil.com.
        # Parsing the host first (py/incomplete-url-substring-sanitization) closes it.
        assert not is_cloud_host("https://evil.com/x.atlassian.net")
        assert not is_cloud_host("https://evil.com/.atlassian.net")

    def test_suffix_lookalike_host_is_not_cloud(self):
        # Host ends with the literal but is not a subdomain of atlassian.net.
        assert not is_cloud_host("https://x.atlassian.net.evil.com")

    def test_no_leading_dot_bypass_is_not_cloud(self):
        assert not is_cloud_host("https://notatlassian.net")

    def test_backslash_authority_differential_is_not_cloud(self):
        # C3 parser differential: the client connects to evil.com, so this is
        # correctly rejected as non-Cloud.
        assert not is_cloud_host("https://evil.com\\@acme.atlassian.net/x")

    def test_credentials_are_stripped_before_check(self):
        assert is_cloud_host("https://user:token@acme.atlassian.net")

    def test_empty_is_not_cloud(self):
        assert not is_cloud_host("")
