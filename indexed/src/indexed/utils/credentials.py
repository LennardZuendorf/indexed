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
    """Ensure required credentials are available for a source type.
    
    Checks for missing credentials and prompts the user to enter them.
    Non-sensitive values (email) are saved to config.toml.
    Sensitive values (tokens) are saved to .env file.
    
    Args:
        source_type: The source type (e.g., 'jiraCloud', 'confluence', 'localFiles')
        config_service: ConfigService instance for reading/writing config
        namespace: Optional config namespace override. If not provided, 
                   uses default based on source_type.
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
        ensure_atlassian_cloud_credentials(config_service, namespace, "Confluence Cloud")
    elif source_type == "jira":
        ensure_server_credentials(
            config_service, namespace, "Jira Server",
            token_env_var="JIRA_TOKEN",
            login_env_var="JIRA_LOGIN",
            password_env_var="JIRA_PASSWORD",
        )
    elif source_type == "confluence":
        ensure_server_credentials(
            config_service, namespace, "Confluence Server",
            token_env_var="CONF_TOKEN",
            login_env_var="CONF_LOGIN",
            password_env_var="CONF_PASSWORD",
        )


def ensure_atlassian_cloud_credentials(
    config_service: ConfigService,
    namespace: str,
    display_name: str,
) -> Dict[str, Any]:
    """Ensure Atlassian Cloud credentials (email + api_token) are available.
    
    Checks config and environment for existing credentials.
    Prompts for missing values and saves them appropriately.
    
    Args:
        config_service: ConfigService instance
        namespace: Config namespace (e.g., 'sources.jira')
        display_name: Display name for prompts (e.g., 'Jira Cloud')
        
    Returns:
        Dict with prompted/existing values: {'email': ..., 'api_token': ...}
        
    Raises:
        typer.Exit: If required credentials are not provided
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
        console.print(f"[{get_heading_style()}]{display_name} Credentials Required[/{get_heading_style()}]")
        console.print()
    
    result = {"email": email, "api_token": api_token}
    
    for field_name in missing_fields:
        if field_name == "email":
            value = console.input(f"[{get_accent_style()}]Atlassian Email[/{get_accent_style()}]: ")
            if not value:
                print_error("Email is required for Atlassian Cloud authentication")
                raise typer.Exit(1)
            # Save email to config.toml (non-sensitive)
            config_service.set_value(
                f"{namespace}.email",
                value,
                field_info={"sensitive": False}
            )
            result["email"] = value
            
        elif field_name == "api_token":
            value = Prompt.ask(f"[{get_accent_style()}]API Token[/{get_accent_style()}]", password=True)
            if not value:
                print_error("API token is required for Atlassian Cloud authentication")
                raise typer.Exit(1)
            # Save token to .env file (sensitive)
            config_service.set_value(
                f"{namespace}.api_token",
                value,
                field_info={"sensitive": True, "env_var": "ATLASSIAN_TOKEN"}
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
    """Ensure Server/DC credentials are available (token OR login+password).
    
    Checks config and environment for existing credentials.
    Prompts for missing values and saves them to .env file.
    
    Args:
        config_service: ConfigService instance
        namespace: Config namespace (e.g., 'sources.jira')
        display_name: Display name for prompts (e.g., 'Jira Server')
        token_env_var: Environment variable name for token (e.g., 'JIRA_TOKEN')
        login_env_var: Environment variable name for login (e.g., 'JIRA_LOGIN')
        password_env_var: Environment variable name for password (e.g., 'JIRA_PASSWORD')
        
    Returns:
        Dict with prompted/existing values
        
    Raises:
        typer.Exit: If required credentials are not provided
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
        console.print(f"[{get_heading_style()}]{display_name} Credentials Required[/{get_heading_style()}]")
        console.print()
        console.print(f"[{get_dim_style()}]Provide either a token OR username and password[/{get_dim_style()}]")
        console.print()
    
    # Ask which auth method
    auth_choice = console.input(f"[{get_accent_style()}]Use token auth? (y/n)[/{get_accent_style()}] [y]: ") or "y"
    
    result: Dict[str, Any] = {"token": None, "login": None, "password": None}
    
    if auth_choice.lower() in ("y", "yes"):
        token = Prompt.ask(f"[{get_accent_style()}]Token[/{get_accent_style()}]", password=True)
        if not token:
            print_error("Token is required")
            raise typer.Exit(1)
        config_service.set_value(
            f"{namespace}.token",
            token,
            field_info={"sensitive": True, "env_var": token_env_var}
        )
        os.environ[token_env_var] = token
        result["token"] = token
    else:
        # Prompt for login+password
        login = console.input(f"[{get_accent_style()}]Username[/{get_accent_style()}]: ")
        if not login:
            print_error("Username is required")
            raise typer.Exit(1)
        config_service.set_value(
            f"{namespace}.login",
            login,
            field_info={"sensitive": True, "env_var": login_env_var}
        )
        os.environ[login_env_var] = login
        result["login"] = login
        
        password = Prompt.ask(f"[{get_accent_style()}]Password[/{get_accent_style()}]", password=True)
        if not password:
            print_error("Password is required")
            raise typer.Exit(1)
        config_service.set_value(
            f"{namespace}.password",
            password,
            field_info={"sensitive": True, "env_var": password_env_var}
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
    """Prompt for a credential field and save it appropriately.
    
    Handles known credential fields (email, api_token, token, login, password)
    with proper prompts and env var mappings.
    
    Args:
        field_name: Name of the field to prompt for
        field_info: Field metadata dict (may be modified for special cases)
        config_service: ConfigService instance
        namespace: Config namespace (e.g., 'sources.jira')
        source_type: Optional source type for special handling (e.g., 'confluence' server)
        
    Returns:
        The entered value
        
    Raises:
        typer.Exit: If a required credential is not provided
    """
    value: str = ""
    updated_field_info = dict(field_info)  # Copy to avoid modifying original
    
    if field_name == "email":
        value = console.input(f"[{get_accent_style()}]Email[/{get_accent_style()}]: ")
        if not value:
            print_error("Email is required")
            raise typer.Exit(1)
            
    elif field_name in ["api_token", "token"]:
        value = Prompt.ask(f"[{get_accent_style()}]API token[/{get_accent_style()}]", password=True)
        if not value:
            print_error("API token is required")
            raise typer.Exit(1)
        # Set appropriate env var based on source type
        if field_name == "token" and source_type == "confluence":
            updated_field_info = {**field_info, "sensitive": True, "env_var": "CONF_TOKEN"}
            os.environ["CONF_TOKEN"] = value
        elif field_name == "token" and source_type == "jira":
            updated_field_info = {**field_info, "sensitive": True, "env_var": "JIRA_TOKEN"}
            os.environ["JIRA_TOKEN"] = value
        elif field_name == "api_token":
            updated_field_info = {**field_info, "sensitive": True, "env_var": "ATLASSIAN_TOKEN"}
            os.environ["ATLASSIAN_TOKEN"] = value
            
    elif field_name == "login":
        value = console.input(f"[{get_accent_style()}]Username[/{get_accent_style()}]: ")
        if not value:
            print_error("Username is required")
            raise typer.Exit(1)
        # Set appropriate env var based on source type
        if source_type == "confluence":
            updated_field_info = {**field_info, "sensitive": True, "env_var": "CONF_LOGIN"}
            os.environ["CONF_LOGIN"] = value
        else:
            updated_field_info = {**field_info, "sensitive": True, "env_var": "JIRA_LOGIN"}
            os.environ["JIRA_LOGIN"] = value
            
    elif field_name == "password":
        value = Prompt.ask(f"[{get_accent_style()}]Password[/{get_accent_style()}]", password=True)
        if not value:
            print_error("Password is required")
            raise typer.Exit(1)
        # Set appropriate env var based on source type
        if source_type == "confluence":
            updated_field_info = {**field_info, "sensitive": True, "env_var": "CONF_PASSWORD"}
            os.environ["CONF_PASSWORD"] = value
        else:
            updated_field_info = {**field_info, "sensitive": True, "env_var": "JIRA_PASSWORD"}
            os.environ["JIRA_PASSWORD"] = value
    else:
        # Unknown credential field, use generic prompt
        is_sensitive = field_info.get("sensitive", False)
        if is_sensitive:
            value = Prompt.ask(
                f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]",
                password=True,
            )
        else:
            value = console.input(f"[{get_accent_style()}]{field_name}[/{get_accent_style()}]: ")
    
    # Save the value using ConfigService
    config_service.set_value(
        f"{namespace}.{field_name}",
        value,
        field_info=updated_field_info
    )
    
    return value


def is_credential_field(field_name: str) -> bool:
    """Check if a field name is a credential field.
    
    Args:
        field_name: Name of the field
        
    Returns:
        True if the field is a credential field
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
        True if at least one auth method is available
    """
    has_token = validation_present.get("token") or os.getenv(token_env_var)
    has_login_password = (
        (validation_present.get("login") or os.getenv(login_env_var))
        and (validation_present.get("password") or os.getenv(password_env_var))
    )
    return bool(has_token or has_login_password)

