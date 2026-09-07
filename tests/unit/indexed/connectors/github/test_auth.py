import subprocess

import pytest

from indexed.config import ConfigurationError
from indexed.connectors.github import auth

pytestmark = pytest.mark.unit


def test_explicit_token_wins(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    assert auth.resolve_token("explicit-token") == "explicit-token"


def test_falls_back_to_github_token_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    assert auth.resolve_token(None) == "env-token"


def test_falls_back_to_gh_cli(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def fake_run(cmd, **kwargs):
        assert cmd == ["gh", "auth", "token"]
        return subprocess.CompletedProcess(cmd, 0, stdout="gh-cli-token\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert auth.resolve_token(None) == "gh-cli-token"


def test_gh_cli_failure_raises_configuration_error(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not logged in")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ConfigurationError, match="gh auth login"):
        auth.resolve_token(None)


def test_gh_not_installed_raises_configuration_error(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ConfigurationError, match="INDEXED__sources__github__token"):
        auth.resolve_token(None)


def test_gh_cli_called_without_hostname_for_cloud(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="cloud-token\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert auth.resolve_token(None, host="github.com") == "cloud-token"
    assert captured["cmd"] == ["gh", "auth", "token"]


def test_gh_cli_called_with_hostname_for_enterprise(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="ghes-token\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert auth.resolve_token(None, host="github.acme.internal") == "ghes-token"
    assert captured["cmd"] == [
        "gh",
        "auth",
        "token",
        "--hostname",
        "github.acme.internal",
    ]
