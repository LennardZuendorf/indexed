"""Configuration schemas for Jira connectors."""

import os
from typing import Optional

from pydantic import BaseModel, Field


class JiraConfig(BaseModel):
    """Configuration for Jira Server/Data Center."""

    url: str = Field(..., description="Jira base URL")
    query: str = Field(..., description="JQL query to filter issues")
    token: Optional[str] = Field(
        None, description="Bearer token (env: JIRA_TOKEN)"
    )
    login: Optional[str] = Field(
        None, description="Username (env: JIRA_LOGIN)"
    )
    password: Optional[str] = Field(
        None, description="Password (env: JIRA_PASSWORD)"
    )

    def get_token(self) -> Optional[str]:
        """Get token from config or environment."""
        return self.token or os.getenv("JIRA_TOKEN")

    def get_login(self) -> Optional[str]:
        """Get login from config or environment."""
        return self.login or os.getenv("JIRA_LOGIN")

    def get_password(self) -> Optional[str]:
        """Get password from config or environment."""
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

    def get_email(self) -> str:
        """Get email from config or environment."""
        email = self.email or os.getenv("ATLASSIAN_EMAIL")
        if not email:
            raise ValueError("ATLASSIAN_EMAIL not set in config or environment")
        return email

    def get_api_token(self) -> str:
        """Get API token from config or environment."""
        token = self.api_token or os.getenv("ATLASSIAN_TOKEN")
        if not token:
            raise ValueError("ATLASSIAN_TOKEN not set in config or environment")
        return token


__all__ = ["JiraConfig", "JiraCloudConfig"]


