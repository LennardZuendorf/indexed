from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping


def get_by_path(
    data: Mapping[str, Any], dot_path: str, default: Any | None = None
) -> Any:
    """
    Retrieve a value from a nested mapping using a dot-separated path.

    If `dot_path` is empty or any path segment is missing (or an intermediate
    value is not a Mapping), `default` is returned. Traversal treats each
    segment between dots as a key into the current mapping.

    Parameters:
        data (Mapping[str, Any]): The mapping to traverse.
        dot_path (str): Dot-separated keys (e.g. "a.b.c"); may be empty.
        default (Any, optional): Value returned when the path does not exist. Defaults to None.

    Returns:
        Any: The value found at the given path, or `default` if the path is missing or invalid.
    """
    cur: Any = data
    for key in dot_path.split(".") if dot_path else []:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def set_by_path(data: MutableMapping[str, Any], dot_path: str, value: Any) -> None:
    """
    Set a value inside a nested mutable mapping using a dot-separated path, creating intermediate mappings as needed.

    Parameters:
        data: The root mutable mapping to modify.
        dot_path: Dot-separated keys specifying where to set the value (e.g., "a.b.c"); must not be empty.
        value: The value to assign at the final key.

    Raises:
        ValueError: If `dot_path` is an empty string.
    """
    if not dot_path:
        raise ValueError("dot_path must not be empty")
    parts = dot_path.split(".")
    cur: MutableMapping[str, Any] = data
    for key in parts[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, MutableMapping):
            nxt = {}
            cur[key] = nxt
        cur = nxt  # type: ignore[assignment]
    cur[parts[-1]] = value


def delete_by_path(data: MutableMapping[str, Any], dot_path: str) -> bool:
    """
    Remove the mapping entry specified by a dot-separated path from a nested mutable mapping.

    Parameters:
        data (MutableMapping[str, Any]): Root mapping to operate on; intermediate mappings may be created or traversed as dictionaries.
        dot_path (str): Dot-separated key path (e.g. "a.b.c"); an empty string is considered invalid.

    Returns:
        bool: `True` if the final key existed and was deleted, `False` if the path was empty, any intermediate segment was not a mapping, or the final key was missing.
    """
    if not dot_path:
        return False
    parts = dot_path.split(".")
    cur: MutableMapping[str, Any] = data
    for key in parts[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, MutableMapping):
            return False
        cur = nxt  # type: ignore[assignment]
    if parts[-1] in cur:
        del cur[parts[-1]]
        return True
    return False


def deep_merge(base: Dict[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge two mappings into a new dictionary, with values from `overlay` overriding or extending `base`.

    Parameters:
        base (Dict[str, Any]): Starting dictionary whose values are used unless overridden.
        overlay (Mapping[str, Any]): Mapping whose values take precedence; nested mappings are merged recursively.

    Returns:
        Dict[str, Any]: A new dictionary containing the deep-merged result.
    """
    res: Dict[str, Any] = dict(base)
    for k, v in overlay.items():
        if k in res and isinstance(res[k], dict) and isinstance(v, Mapping):
            res[k] = deep_merge(res[k], v)
        else:
            res[k] = v  # type: ignore[index]
    return res
