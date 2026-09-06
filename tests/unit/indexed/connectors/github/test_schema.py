import pytest
from pydantic import ValidationError

from indexed.connectors.github.schema import GITHUB_CLOUD_HOST, GitHubConfig


def test_github_cloud_host_constant():
    assert GITHUB_CLOUD_HOST == "github.com"


def test_defaults():
    cfg = GitHubConfig(repos=["octo/hello"])
    assert cfg.host == "github.com"
    assert cfg.state == "all"
    assert cfg.include_pull_requests is False
    assert cfg.include_comments is True
    assert cfg.page_size == 100
    assert cfg.verify_ssl is True


def test_host_strips_scheme_and_trailing_slash():
    cfg = GitHubConfig(repos=["octo/hello"], host="https://github.example.com/")
    assert cfg.host == "github.example.com"


def test_resolve_graphql_url_public_cloud():
    cfg = GitHubConfig(repos=["octo/hello"])
    assert cfg.resolve_graphql_url() == "https://api.github.com/graphql"


def test_resolve_graphql_url_data_residency():
    cfg = GitHubConfig(repos=["octo/hello"], host="octocorp.ghe.com")
    assert cfg.resolve_graphql_url() == "https://api.octocorp.ghe.com/graphql"


def test_resolve_graphql_url_ghes():
    cfg = GitHubConfig(repos=["octo/hello"], host="github.example.com")
    assert cfg.resolve_graphql_url() == "https://github.example.com/api/graphql"


def test_resolve_graphql_url_explicit_override_wins():
    cfg = GitHubConfig(
        repos=["octo/hello"],
        host="github.example.com",
        graphql_url="https://custom/graphql",
    )
    assert cfg.resolve_graphql_url() == "https://custom/graphql"


def test_is_cloud():
    assert GitHubConfig(repos=["octo/hello"]).is_cloud() is True
    assert (
        GitHubConfig(repos=["octo/hello"], host="github.example.com").is_cloud()
        is False
    )


def test_parsed_repos():
    cfg = GitHubConfig(repos=["octo/api", "octo/web"])
    assert cfg.parsed_repos() == [("octo", "api"), ("octo", "web")]


def test_parsed_repos_rejects_bad_selector():
    cfg = GitHubConfig(repos=["not-a-repo"])
    with pytest.raises(ValueError, match="owner/repo"):
        cfg.parsed_repos()


def test_parsed_project_none_by_default():
    assert GitHubConfig(repos=["octo/hello"]).parsed_project() is None


def test_parsed_project():
    cfg = GitHubConfig(repos=[], project="octo/12")
    assert cfg.parsed_project() == ("octo", 12)


def test_parsed_project_rejects_bad_selector():
    cfg = GitHubConfig(repos=[], project="octo/not-a-number")
    with pytest.raises(ValueError, match="owner/number"):
        cfg.parsed_project()


def test_get_token_uses_explicit_value(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cfg = GitHubConfig(repos=["octo/hello"], token="ghp_explicit")
    assert cfg.get_token() == "ghp_explicit"


def test_max_chunk_tokens_bounds():
    with pytest.raises(ValidationError):
        GitHubConfig(repos=["octo/hello"], max_chunk_tokens=1)
    with pytest.raises(ValidationError):
        GitHubConfig(repos=["octo/hello"], max_chunk_tokens=99999)
