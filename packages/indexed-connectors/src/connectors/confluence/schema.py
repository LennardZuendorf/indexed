"""Configuration schemas for Confluence connectors."""

import os
from typing import Optional

from pydantic import BaseModel, Field


class ConfluenceConfig(BaseModel):
    """Configuration for Confluence Server/Data Center."""

    url: str = Field(..., description="Confluence base URL")
    query: str = Field(..., description="CQL query to filter pages")
    token: Optional[str] = Field(None, description="Bearer token (env: CONF_TOKEN)")
    login: Optional[str] = Field(None, description="Username (env: CONF_LOGIN)")
    password: Optional[str] = Field(None, description="Password (env: CONF_PASSWORD)")
    read_all_comments: bool = Field(
        default=True, description="Read nested comments (yes/no)"
    )

    def get_token(self) -> Optional[str]:
        """
        Return the configured Confluence token or the CONF_TOKEN environment value.

        Returns:
            token (Optional[str]): The token from the instance if set; otherwise the value of the
            `CONF_TOKEN` environment variable; `None` if neither is provided.
        """
        return self.token or os.getenv("CONF_TOKEN")

    def get_login(self) -> Optional[str]:
        """
        Get the Confluence login from configuration or the CONF_LOGIN environment variable.

        Returns:
            The login string from configuration or environment, or `None` if neither is set.
        """
        return self.login or os.getenv("CONF_LOGIN")

    def get_password(self) -> Optional[str]:
        """
        Retrieve the configured Confluence password, falling back to the CONF_PASSWORD environment variable.

        Returns:
            str: The configured password if present in the instance or in the CONF_PASSWORD environment variable, `None` otherwise.
        """
        return self.password or os.getenv("CONF_PASSWORD")


class ConfluenceCloudConfig(BaseModel):
    """Configuration for Confluence Cloud."""

    url: str = Field(..., description="Confluence Cloud URL (*.atlassian.net)")
    query: str = Field(..., description="CQL query to filter pages")
    email: Optional[str] = Field(
        None, description="Atlassian account email (env: ATLASSIAN_EMAIL)"
    )
    api_token: Optional[str] = Field(
        None, description="API token (env: ATLASSIAN_TOKEN)"
    )
    read_all_comments: bool = Field(
        default=True, description="Read nested comments (yes/no)"
    )

    def get_email(self) -> str:
        """
        Return the Atlassian account email from the configuration or the ATLASSIAN_EMAIL environment variable.

        Returns:
            email (str): The Atlassian account email.

        Raises:
            ValueError: If neither the configuration nor the ATLASSIAN_EMAIL environment variable provide an email.
        """
        email = self.email or os.getenv("ATLASSIAN_EMAIL")
        if not email:
            raise ValueError("ATLASSIAN_EMAIL not set in config or environment")
        return email

    def get_api_token(self) -> str:
        """
        Retrieve the Atlassian API token from the configuration or the ATLASSIAN_TOKEN environment variable.

        Returns:
            The API token string.

        Raises:
            ValueError: If neither `api_token` is set on the config nor `ATLASSIAN_TOKEN` is present in the environment.
        """
        token = self.api_token or os.getenv("ATLASSIAN_TOKEN")
        if not token:
            raise ValueError("ATLASSIAN_TOKEN not set in config or environment")
        return token


__all__ = ["ConfluenceConfig", "ConfluenceCloudConfig"]
