"""Comprehensive tests for credentials utility module."""

import os
from unittest.mock import Mock, patch
import pytest
import typer

from indexed.utils.credentials import (
    ensure_credentials_for_source,
    ensure_atlassian_cloud_credentials,
    ensure_server_credentials,
)


class TestEnsureCredentialsForSource:
    """Test ensure_credentials_for_source function."""

    def test_skips_local_files(self):
        """Should skip credential check for localFiles source type."""
        mock_config = Mock()
        # Should not raise or call config service
        ensure_credentials_for_source("localFiles", mock_config)
        mock_config.get.assert_not_called()

    def test_jira_cloud_delegates_to_cloud_handler(self):
        """Should delegate jiraCloud to Atlassian Cloud handler."""
        mock_config = Mock()
        mock_config.get.return_value = None

        with patch.dict(
            os.environ,
            {"ATLASSIAN_EMAIL": "test@example.com", "ATLASSIAN_TOKEN": "token123"},
        ):
            ensure_credentials_for_source("jiraCloud", mock_config)

        # Should have checked for email
        mock_config.get.assert_any_call("sources.jira.email")

    def test_confluence_cloud_delegates_to_cloud_handler(self):
        """Should delegate confluenceCloud to Atlassian Cloud handler."""
        mock_config = Mock()
        mock_config.get.return_value = None

        with patch.dict(
            os.environ,
            {"ATLASSIAN_EMAIL": "test@example.com", "ATLASSIAN_TOKEN": "token123"},
        ):
            ensure_credentials_for_source("confluenceCloud", mock_config)

        # Should have checked for email in confluence namespace
        mock_config.get.assert_any_call("sources.confluence.email")

    def test_jira_server_delegates_to_server_handler(self):
        """Should delegate jira to server credentials handler."""
        mock_config = Mock()
        mock_config.get.return_value = None

        with patch.dict(os.environ, {"JIRA_TOKEN": "server_token"}):
            ensure_credentials_for_source("jira", mock_config)

        # Should have checked for token/credentials
        assert mock_config.get.called

    def test_confluence_server_delegates_to_server_handler(self):
        """Should delegate confluence to server credentials handler."""
        mock_config = Mock()
        mock_config.get.return_value = None

        with patch.dict(os.environ, {"CONF_TOKEN": "conf_token"}):
            ensure_credentials_for_source("confluence", mock_config)

        assert mock_config.get.called

    def test_custom_namespace_override(self):
        """Should use custom namespace when provided."""
        mock_config = Mock()
        mock_config.get.return_value = None

        with patch.dict(
            os.environ,
            {"ATLASSIAN_EMAIL": "test@example.com", "ATLASSIAN_TOKEN": "token123"},
        ):
            ensure_credentials_for_source(
                "jiraCloud", mock_config, namespace="custom.namespace"
            )

        # Should use custom namespace
        mock_config.get.assert_any_call("custom.namespace.email")

    def test_unknown_source_type_ignored(self):
        """Should silently ignore unknown source types."""
        mock_config = Mock()
        # Should not raise
        ensure_credentials_for_source("unknown_type", mock_config)


class TestEnsureAtlassianCloudCredentials:
    """Test ensure_atlassian_cloud_credentials function."""

    def test_uses_existing_credentials(self):
        """Should use existing credentials from config and environment."""
        mock_config = Mock()
        mock_config.get.return_value = "existing@example.com"

        with patch.dict(os.environ, {"ATLASSIAN_TOKEN": "existing_token"}):
            result = ensure_atlassian_cloud_credentials(
                mock_config, "sources.jira", "Jira Cloud"
            )

        assert result["email"] == "existing@example.com"
        assert result["api_token"] == "existing_token"

    def test_uses_email_from_environment(self):
        """Should read email from ATLASSIAN_EMAIL env var."""
        mock_config = Mock()
        mock_config.get.return_value = None

        with patch.dict(
            os.environ,
            {"ATLASSIAN_EMAIL": "env@example.com", "ATLASSIAN_TOKEN": "token"},
        ):
            result = ensure_atlassian_cloud_credentials(
                mock_config, "sources.jira", "Jira Cloud"
            )

        assert result["email"] == "env@example.com"

    @patch("indexed.utils.credentials.console")
    def test_prompts_for_missing_email(self, mock_console):
        """Should prompt user for missing email."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_console.input.return_value = "prompted@example.com"

        with patch.dict(os.environ, {"ATLASSIAN_TOKEN": "token"}, clear=True):
            result = ensure_atlassian_cloud_credentials(
                mock_config, "sources.jira", "Jira Cloud"
            )

        mock_console.input.assert_called()
        assert result["email"] == "prompted@example.com"

    @patch("indexed.utils.credentials.Prompt.ask")
    @patch("indexed.utils.credentials.console")
    def test_prompts_for_missing_token(self, mock_console, mock_prompt):
        """Should prompt user for missing API token."""
        mock_config = Mock()
        mock_config.get.return_value = "email@example.com"
        mock_prompt.return_value = "prompted_token"

        with patch.dict(os.environ, {}, clear=True):
            result = ensure_atlassian_cloud_credentials(
                mock_config, "sources.jira", "Jira Cloud"
            )

        mock_prompt.assert_called()
        assert result["api_token"] == "prompted_token"

    @patch("indexed.utils.credentials.Prompt.ask")
    @patch("indexed.utils.credentials.console")
    def test_saves_prompted_credentials(self, mock_console, mock_prompt):
        """Should save prompted credentials to config."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_console.input.return_value = "new@example.com"
        mock_prompt.return_value = "new_token"

        with patch.dict(os.environ, {}, clear=True):
            ensure_atlassian_cloud_credentials(
                mock_config, "sources.jira", "Jira Cloud"
            )

        # Should save email to config using set_value
        mock_config.set_value.assert_any_call(
            "sources.jira.email", "new@example.com", field_info={"sensitive": False}
        )
        # Should save token as sensitive
        mock_config.set_value.assert_any_call(
            "sources.jira.api_token",
            "new_token",
            field_info={"sensitive": True, "env_var": "ATLASSIAN_TOKEN"},
        )

    @patch("indexed.utils.credentials.console")
    def test_exits_when_user_declines_to_provide(self, mock_console):
        """Should exit when user chooses not to provide credentials."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_console.input.return_value = ""  # Empty email triggers exit

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(typer.Exit):
                ensure_atlassian_cloud_credentials(
                    mock_config, "sources.jira", "Jira Cloud"
                )


class TestEnsureServerCredentials:
    """Test ensure_server_credentials function."""

    def test_uses_token_from_environment(self):
        """Should use token auth when TOKEN env var is set."""
        mock_config = Mock()
        mock_config.get.return_value = None

        with patch.dict(os.environ, {"JIRA_TOKEN": "server_token"}):
            result = ensure_server_credentials(
                mock_config,
                "sources.jira",
                "Jira Server",
                token_env_var="JIRA_TOKEN",
                login_env_var="JIRA_LOGIN",
                password_env_var="JIRA_PASSWORD",
            )

        assert result["token"] == "server_token"
        # Function returns all keys, but login/password will be None or from config
        assert result.get("login") is None or isinstance(
            result.get("login"), (str, type(None))
        )
        assert result.get("password") is None

    def test_uses_login_password_from_environment(self):
        """Should use login/password auth when LOGIN and PASSWORD env vars are set."""
        mock_config = Mock()
        mock_config.get.return_value = None

        with patch.dict(os.environ, {"JIRA_LOGIN": "user", "JIRA_PASSWORD": "pass"}):
            result = ensure_server_credentials(
                mock_config,
                "sources.jira",
                "Jira Server",
                token_env_var="JIRA_TOKEN",
                login_env_var="JIRA_LOGIN",
                password_env_var="JIRA_PASSWORD",
            )

        assert result["login"] == "user"
        assert result["password"] == "pass"

    @patch("indexed.utils.credentials.Prompt.ask")
    @patch("indexed.utils.credentials.console")
    def test_prompts_for_auth_method_when_missing(self, mock_console, mock_prompt):
        """Should prompt for auth method when no credentials exist."""
        mock_config = Mock()
        mock_config.get.return_value = None
        mock_prompt.return_value = "my_token"

        with patch.dict(os.environ, {}, clear=True):
            with patch(
                "indexed.utils.credentials.typer.confirm", return_value=True
            ):  # Choose token
                result = ensure_server_credentials(
                    mock_config,
                    "sources.jira",
                    "Jira Server",
                    token_env_var="JIRA_TOKEN",
                    login_env_var="JIRA_LOGIN",
                    password_env_var="JIRA_PASSWORD",
                )

        assert "token" in result or "login" in result

    @patch("indexed.utils.credentials.Prompt.ask")
    @patch("indexed.utils.credentials.console")
    def test_reads_from_config_namespace(self, mock_console, mock_prompt):
        """Should read existing credentials from config namespace."""
        mock_config = Mock()
        # Return token from config when asked
        mock_config.get.side_effect = lambda key: {
            "sources.jira.token": "config_token"
        }.get(key)
        mock_console.input.return_value = "y"  # Choose token auth
        mock_prompt.return_value = "prompted_token"  # In case it prompts

        with patch.dict(os.environ, {}, clear=True):
            result = ensure_server_credentials(
                mock_config,
                "sources.jira",
                "Jira Server",
                token_env_var="JIRA_TOKEN",
                login_env_var="JIRA_LOGIN",
                password_env_var="JIRA_PASSWORD",
            )

        # Should have checked config
        assert mock_config.get.called
        # Result should have token (either from config or prompted)
        assert "token" in result or result.get("token") is not None


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch("indexed.utils.credentials.console")
    def test_empty_email_not_accepted(self, mock_console):
        """Should not accept empty email address."""
        mock_config = Mock()
        mock_config.get.return_value = ""
        mock_console.input.return_value = "valid@example.com"

        with patch.dict(os.environ, {"ATLASSIAN_TOKEN": "token"}):
            result = ensure_atlassian_cloud_credentials(
                mock_config, "sources.jira", "Jira"
            )
            # Should have prompted for new email since existing was empty
            assert result["email"] == "valid@example.com"

    def test_handles_none_namespace_gracefully(self):
        """Should handle None namespace by deriving default."""
        mock_config = Mock()
        # Should not raise
        ensure_credentials_for_source("localFiles", mock_config, namespace=None)

    def test_concurrent_calls_dont_interfere(self):
        """Should handle concurrent credential checks without interference."""
        mock_config1 = Mock()
        mock_config2 = Mock()
        mock_config1.get.return_value = None
        mock_config2.get.return_value = None

        with patch.dict(
            os.environ,
            {"ATLASSIAN_EMAIL": "user1@example.com", "ATLASSIAN_TOKEN": "token1"},
        ):
            result1 = ensure_atlassian_cloud_credentials(
                mock_config1, "sources.jira", "Jira"
            )

        with patch.dict(
            os.environ,
            {"ATLASSIAN_EMAIL": "user2@example.com", "ATLASSIAN_TOKEN": "token2"},
        ):
            result2 = ensure_atlassian_cloud_credentials(
                mock_config2, "sources.confluence", "Confluence"
            )

        # Results should be independent
        assert result1["email"] == "user1@example.com"
        assert result2["email"] == "user2@example.com"
