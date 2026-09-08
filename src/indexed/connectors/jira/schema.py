"""Configuration schemas for Jira connectors."""

import os
from typing import Optional

from pydantic import BaseModel, Field


class JiraConfig(BaseModel):
    """Configuration for Jira Server/Data Center."""

    url: str = Field(..., description="Jira base URL")
    query: str = Field(..., description="JQL query to filter issues")
    token: Optional[str] = Field(None, description="Bearer token (env: JIRA_TOKEN)")
    login: Optional[str] = Field(None, description="Username (env: JIRA_LOGIN)")
    password: Optional[str] = Field(None, description="Password (env: JIRA_PASSWORD)")
    include_attachments: bool = Field(
        default=False, description="Fetch and parse issue attachments"
    )
    max_chunk_tokens: int = Field(
        default=512, ge=64, le=2048, description="Max tokens per chunk"
    )
    ocr_enabled: bool = Field(
        default=True, description="Enable OCR for image attachments"
    )
    max_attachment_size_mb: int = Field(
        default=10, ge=1, le=100, description="Max attachment size in MB to download"
    )

    def get_token(self) -> Optional[str]:
        """
        Retrieve the Jira bearer token from the configuration or the JIRA_TOKEN environment variable.

        Returns:
            token (Optional[str]): The token from the instance if set; otherwise the value of the JIRA_TOKEN environment variable, or `None` if neither is present.
        """
        return self.token or os.getenv("JIRA_TOKEN")

    def get_login(self) -> Optional[str]:
        """
        Retrieve the configured Jira login, falling back to the JIRA_LOGIN environment variable.

        Returns:
            Optional[str]: The login from the configuration if set, otherwise the value of the JIRA_LOGIN environment variable, or None if neither is set.
        """
        return self.login or os.getenv("JIRA_LOGIN")

    def get_password(self) -> Optional[str]:
        """
        Return the configured Jira password or the value of the JIRA_PASSWORD environment variable.

        Returns:
            str | None: The password if set, `None` otherwise.
        """
        return self.password or os.getenv("JIRA_PASSWORD")


class JiraCloudConfig(BaseModel):
    """Configuration for Jira Cloud."""

    url: str = Field(..., description="Jira Cloud URL (*.atlassian.net)")
    query: str = Field(..., description="JQL query to filter issues")
    email: Optional[str] = Field(
        None, description="Atlassian account email (env: ATLASSIAN_EMAIL)"
    )
    api_token: Optional[str] = Field(
        None, description="API token (env: ATLASSIAN_TOKEN)"
    )
    include_attachments: bool = Field(
        default=False, description="Fetch and parse issue attachments"
    )
    max_chunk_tokens: int = Field(
        default=512, ge=64, le=2048, description="Max tokens per chunk"
    )
    ocr_enabled: bool = Field(
        default=True, description="Enable OCR for image attachments"
    )
    max_attachment_size_mb: int = Field(
        default=10, ge=1, le=100, description="Max attachment size in MB to download"
    )

    def get_email(self) -> str:
        """
        Retrieve the Atlassian account email from the configuration or the ATLASSIAN_EMAIL environment variable.

        Returns:
            email (str): The configured email or the value of ATLASSIAN_EMAIL.

        Raises:
            ValueError: If neither the configured email nor ATLASSIAN_EMAIL is set.
        """
        email = self.email or os.getenv("ATLASSIAN_EMAIL")
        if not email:
            raise ValueError("ATLASSIAN_EMAIL not set in config or environment")
        return email

    def get_api_token(self) -> str:
        """
        Retrieve the Atlassian API token from the instance configuration or the ATLASSIAN_TOKEN environment variable.

        Returns:
            api_token (str): The resolved API token.

        Raises:
            ValueError: If neither the instance `api_token` nor the `ATLASSIAN_TOKEN` environment variable is set.
        """
        token = self.api_token or os.getenv("ATLASSIAN_TOKEN")
        if not token:
            raise ValueError("ATLASSIAN_TOKEN not set in config or environment")
        return token


__all__ = ["JiraConfig", "JiraCloudConfig"]
