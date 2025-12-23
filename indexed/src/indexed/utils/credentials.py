"""Shared credential prompting utilities for CLI commands.

This module provides reusable functions for prompting and saving
credentials for various connector types (Jira, Confluence, etc.).
"""

import os
from typing import Dict, Any, Optional

import typer
from rich.prompt import Prompt

from indexed_config import ConfigService
from .logging import is_verbose_mode
from .console import console
from .components.theme import get_heading_style, get_dim_style, get_accent_style
from .components import print_error


def ensure_credentials_for_source(
    source_type: str,
    config_service: ConfigService,
    namespace: Optional[str] = None,
) -> None:
    """
    Ensure required credentials exist for the given source type, prompting the user and persisting any missing values.

    Determines a config namespace when not provided (jira/jiraCloud -> "sources.jira", confluence/confluenceCloud -> "sources.confluence"), skips processing for "localFiles", and delegates to the appropriate handler to gather and store credentials (Atlassian Cloud email + API token or server token/login+password). Unknown source types are ignored.

    Parameters:
        source_type (str): Source identifier (e.g., "jiraCloud", "confluence", "localFiles") that determines which credential flow to run.
        config_service (ConfigService): Service used to read and write configuration and environment-backed secrets.
        namespace (Optional[str]): Optional configuration namespace override; when omitted a default namespace is chosen based on the source_type.
    """
    # Skip credential check for local files
    if source_type == "localFiles":
        return

    # Determine namespace based on source type if not provided
    if namespace is None:
        if source_type in ("jira", "jiraCloud"):
            namespace = "sources.jira"
        elif source_type in ("confluence", "confluenceCloud"):
            namespace = "sources.confluence"
        else:
            return  # Unknown source type, skip

    # Check and prompt for credentials based on source type
    if source_type == "jiraCloud":
        ensure_atlassian_cloud_credentials(config_service, namespace, "Jira Cloud")
    elif source_type == "confluenceCloud":
        ensure_atlassian_cloud_credentials(
            config_service, namespace, "Confluence Cloud"
        )
    elif source_type == "jira":
        ensure_server_credentials(
            config_service,
            namespace,
            "Jira Server",
            token_env_var="JIRA_TOKEN",
            login_env_var="JIRA_LOGIN",
            password_env_var="JIRA_PASSWORD",
        )
    elif source_type == "confluence":
        ensure_server_credentials(
            config_service,
            namespace,
            "Confluence Server",
            token_env_var="CONF_TOKEN",
            login_env_var="CONF_LOGIN",
            password_env_var="CONF_PASSWORD",
        )


def ensure_atlassian_cloud_credentials(
    config_service: ConfigService,
    namespace: str,
    display_name: str,
) -> Dict[str, Any]:
    """
    Ensure Atlassian Cloud credentials (email and API token) are present, prompting the user for any missing values and persisting them.

    Reads existing values from the config under "{namespace}.email" and from the ATLASSIAN_EMAIL / ATLASSIAN_TOKEN environment variables. Prompts for any missing fields, saves the email to the config (non-sensitive) and the API token to the config as sensitive while also setting the ATLASSIAN_TOKEN environment variable for immediate use.

    Parameters:
        config_service (ConfigService): Service used to read/write configuration values.
        namespace (str): Config namespace for storing values (e.g., "sources.jira").
        display_name (str): Human-readable name shown in prompts (e.g., "Jira Cloud").

    Returns:
        dict: Dictionary with keys "email" and "api_token" containing the resulting credentials.

    Raises:
        typer.Exit: If the user does not provide a required credential when prompted.
    """
    # Check for existing values
    email = config_service.get(f"{namespace}.email") or os.getenv("ATLASSIAN_EMAIL")
    api_token = os.getenv("ATLASSIAN_TOKEN")

    missing_fields = []
    if not email:
        missing_fields.append("email")
    if not api_token:
        missing_fields.append("api_token")

    if not missing_fields:
        return {"email": email, "api_token": api_token}

    # Show header for credential prompts
    if not is_verbose_mode():
        console.print()
        console.print(
            f"[{get_heading_style()}]{display_name} Credentials Required[/{get_heading_style()}]"
        )
        console.print()

    result = {"email": email, "api_token": api_token}

    for field_name in missing_fields:
        if field_name == "email":
            value = console.input(
                f"[{get_accent_style()}]Atlassian Email[/{get_accent_style()}]: "
            )
            if not value:
                print_error("Email is required for Atlassian Cloud authentication")
                raise typer.Exit(1)
            # Save email to config.toml (non-sensitive)
            config_service.set_value(
                f"{namespace}.email", value, field_info={"sensitive": False}
            )
            result["email"] = value

        elif field_name == "api_token":
            value = Prompt.ask(
                f"[{get_accent_style()}]API Token[/{get_accent_style()}]", password=True
            )
            if not value:
                print_error("API token is required for Atlassian Cloud authentication")
                raise typer.Exit(1)
            # Save token to .env file (sensitive)
            config_service.set_value(
                f"{namespace}.api_token",
                value,
                field_info={"sensitive": True, "env_var": "ATLASSIAN_TOKEN"},
            )
            # Also set in environment for immediate use
            os.environ["ATLASSIAN_TOKEN"] = value
            result["api_token"] = value

    return result


def ensure_server_credentials(
    config_service: ConfigService,
    namespace: str,
    display_name: str,
    token_env_var: str,
    login_env_var: str,
    password_env_var: str,
) -> Dict[str, Any]:
    """
    Ensure server/Data Center credentials are present for the given namespace, prompting the user and saving values when necessary.

    Prompts for either a token or a username/password pair when no valid authentication is already present in the config or environment.

    Parameters:
        config_service (ConfigService): ConfigService instance used to read/write configuration.
        namespace (str): Config namespace (e.g., "sources.jira") where values are stored.
        display_name (str): Human-readable name shown in prompts (e.g., "Jira Server").
        token_env_var (str): Environment variable name for token (e.g., "JIRA_TOKEN").
        login_env_var (str): Environment variable name for login (e.g., "JIRA_LOGIN").
        password_env_var (str): Environment variable name for password (e.g., "JIRA_PASSWORD").

    Returns:
        dict: A dictionary with keys "token", "login", and "password". Each key maps to the existing or prompted value, or `None` if not provided for that method.

    Raises:
        typer.Exit: If a required credential is not provided when prompted.
    """
    # Check for existing values
    token = os.getenv(token_env_var)
    login = config_service.get(f"{namespace}.login") or os.getenv(login_env_var)
    password = os.getenv(password_env_var)

    # If any auth method is complete, we're good
    if token or (login and password):
        return {"token": token, "login": login, "password": password}

    # Need to prompt for credentials
    if not is_verbose_mode():
        console.print()
        console.print(
            f"[{get_heading_style()}]{display_name} Credentials Required[/{get_heading_style()}]"
        )
        console.print()
        console.print(
            f"[{get_dim_style()}]Provide either a token OR username and password[/{get_dim_style()}]"
        )
        console.print()

    # Ask which auth method
    auth_choice = (
        console.input(
            f"[{get_accent_style()}]Use token auth? (y/n)[/{get_accent_style()}] [y]: "
        )
        or "y"
    )

    result: Dict[str, Any] = {"token": None, "login": None, "password": None}

    if auth_choice.lower() in ("y", "yes"):
        token = Prompt.ask(
            f"[{get_accent_style()}]Token[/{get_accent_style()}]", password=True
        )
        if not token:
            print_error("Token is required")
            raise typer.Exit(1)
        config_service.set_value(
            f"{namespace}.token",
            token,
            field_info={"sensitive": True, "env_var": token_env_var},
        )
        os.environ[token_env_var] = token
        result["token"] = token
    else:
        # Prompt for login+password
        login = console.input(
            f"[{get_accent_style()}]Username[/{get_accent_style()}]: "
        )
        if not login:
            print_error("Username is required")
            raise typer.Exit(1)
        config_service.set_value(
            f"{namespace}.login", login, field_info={"sensitive": False}
        )
        result["login"] = login

        password = Prompt.ask(
            f"[{get_accent_style()}]Password[/{get_accent_style()}]", password=True
        )
        if not password:
            print_error("Password is required")
            raise typer.Exit(1)
        config_service.set_value(
            f"{namespace}.password",
            password,
            field_info={"sensitive": True, "env_var": password_env_var},
        )
        os.environ[password_env_var] = password
        result["password"] = password

    return result


def prompt_credential_field(
    field_name: str,
    field_info: Dict[str, Any],
    config_service: ConfigService,
    namespace: str,
    source_type: Optional[str] = None,
) -> str:
    """
    Prompt for a credential field, persist it to the config, and export any corresponding environment variable.

    Prompts are specialized for recognized credential names:
    - "email": plain text input.
    - "api_token" / "token": password-style input; sets ATLASSIAN_TOKEN, JIRA_TOKEN, or CONF_TOKEN as appropriate.
    - "login": plain text input; sets JIRA_LOGIN or CONF_LOGIN.
    - "password": password-style input; sets JIRA_PASSWORD or CONF_PASSWORD.
    Unknown fields use a password prompt when field_info["sensitive"] is true, otherwise a plain input.

    Parameters:
        field_name (str): Credential field name to prompt for.
        field_info (Dict[str, Any]): Metadata for the field; used to determine sensitivity and is copied before modification.
        config_service (ConfigService): Service used to persist the entered value.
        namespace (str): Config namespace where the value will be stored (e.g., "sources.jira").
        source_type (Optional[str]): Optional source identifier (e.g., "jira" or "confluence") to select environment variable mappings.

    Returns:
        str: The value entered by the user.

    Raises:
        typer.Exit: If a required value is not provided by the user.
    """
    value: str = ""
    updated_field_info = dict(field_info)  # Copy to avoid modifying original

    if field_name == "email":
        value = console.input(f"[{get_accent_style()}]Email[/{get_accent_style()}]: ")
        if not value:
            print_error("Email is required")
            raise typer.Exit(1)

    elif field_name in ["api_token", "token"]:
        value = Prompt.ask(
            f"[{get_accent_style()}]API token[/{get_accent_style()}]", password=True
        )
        if not value:
            print_error("API token is required")
            raise typer.Exit(1)
        # Set appropriate env var based on source type
        if field_name == "token" and source_type == "confluence":
            updated_field_info = {
                **field_info,
                "sensitive": True,
                "env_var": "CONF_TOKEN",
            }
            os.environ["CONF_TOKEN"] = value
        elif field_name == "token" and source_type == "jira":
            updated_field_info = {
                **field_info,
                "sensitive": True,
                "env_var": "JIRA_TOKEN",
            }
            os.environ["JIRA_TOKEN"] = value
        elif field_name == "api_token":
            updated_field_info = {
                **field_info,
                "sensitive": True,
                "env_var": "ATLASSIAN_TOKEN",
            }
            os.environ["ATLASSIAN_TOKEN"] = value

    elif field_name == "login":
        value = console.input(
            f"[{get_accent_style()}]Username[/{get_accent_style()}]: "
        )
        if not value:
            print_error("Username is required")
            raise typer.Exit(1)
        # Login is non-sensitive (like email) - store in TOML, not .env
        # Set env vars for immediate use if source type is known
        if source_type == "confluence":
            updated_field_info = {**field_info, "sensitive": False}
            os.environ["CONF_LOGIN"] = value
        elif source_type == "jira":
            updated_field_info = {**field_info, "sensitive": False}
            os.environ["JIRA_LOGIN"] = value
        else:
            # Unknown source type - mark as non-sensitive
            updated_field_info = {**field_info, "sensitive": False}

    elif field_name == "password":
        value = Prompt.ask(
            f"[{get_accent_style()}]Password[/{get_accent_style()}]", password=True
        )
        if not value:
            print_error("Password is required")
            raise typer.Exit(1)
        # Set appropriate env var based on source type
        if source_type == "confluence":
            updated_field_info = {
                **field_info,
                "sensitive": True,
                "env_var": "CONF_PASSWORD",
            }
            os.environ["CONF_PASSWORD"] = value
        elif source_type == "jira":
            updated_field_info = {
                **field_info,
                "sensitive": True,
                "env_var": "JIRA_PASSWORD",
            }
            os.environ["JIRA_PASSWORD"] = value
        else:
            # Unknown source type - don't set env var, just mark as sensitive
            updated_field_info = {**field_info, "sensitive": True}
    else:
        # Unknown credential field, use generic prompt
        is_sensitive = field_info.get("sensitive", False)
        if is_sensitive:
            value = Prompt.ask(
                f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]",
                password=True,
            )
        else:
            value = console.input(
                f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]: "
            )

    # Save the value using ConfigService
    config_service.set_value(
        f"{namespace}.{field_name}", value, field_info=updated_field_info
    )

    return value


def is_credential_field(field_name: str) -> bool:
    """
    Determine whether a field name corresponds to a recognized credential field.

    Parameters:
        field_name (str): The field name to check.

    Returns:
        True if `field_name` is one of "email", "api_token", "token", "login", or "password", False otherwise.
    """
    credential_fields = {"email", "api_token", "token", "login", "password"}
    return field_name in credential_fields


def check_server_auth_present(
    validation_present: Dict[str, Any],
    token_env_var: str,
    login_env_var: str,
    password_env_var: str,
) -> bool:
    """Check if server authentication credentials are present.

    Checks for either token-based OR login+password authentication.

    Args:
        validation_present: Dict of present field values from validate_requirements()
        token_env_var: Environment variable name for token
        login_env_var: Environment variable name for login
        password_env_var: Environment variable name for password

    Returns:
        True if at least one auth method is available.

    Notes:
        When either ``login`` or ``password`` is present in ``validation_present``,
        environment variables for these fields are intentionally ignored. This
        avoids ambiguous situations where one value comes from validation and
        the other from the environment, which can cause tests (and user
        expectations) to behave inconsistently across machines.
    """
    # Token-based auth
    token_value = validation_present.get("token") or os.getenv(token_env_var)

    # Login/password auth:
    # * If either field is present in validation_present, require BOTH to be
    #   present there and ignore environment variables for these keys.
    # * Otherwise, fall back to environment variables for both values.
    if "login" in validation_present or "password" in validation_present:
        login = validation_present.get("login")
        password = validation_present.get("password")
        # In this mixed-source scenario, only treat an explicit token value in
        # validation_present as valid; ignore any token coming from env vars.
        has_token = bool(validation_present.get("token"))
    else:
        login = os.getenv(login_env_var)
        password = os.getenv(password_env_var)
        has_token = bool(token_value)

    has_login_password = bool(login and password)

    return bool(has_token or has_login_password)
