"""Configuration schemas for Jira connectors."""

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


class JiraCloudConfig(BaseModel):
    """Configuration for Jira Cloud."""

    url: str = Field(..., description="Jira Cloud URL (*.atlassian.net)")
    query: str = Field(..., description="JQL query to filter issues")
    email: str = Field(
        ..., description="Atlassian account email (env: ATLASSIAN_EMAIL)"
    )
    api_token: str = Field(
        ..., description="API token (env: ATLASSIAN_TOKEN)"
    )


__all__ = ["JiraConfig", "JiraCloudConfig"]


