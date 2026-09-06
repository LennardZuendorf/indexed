"""Placeholder auth module for GitHub connector (Task 2 implements full token resolution)."""


def resolve_token(explicit: str | None) -> str:
    """Resolve GitHub token from explicit config or environment.

    Args:
        explicit: Token value from config, or None

    Returns:
        The resolved token

    Raises:
        NotImplementedError: Task 2 implements full token resolution
    """
    if explicit:
        return explicit
    raise NotImplementedError("Task 2 implements full token resolution")
