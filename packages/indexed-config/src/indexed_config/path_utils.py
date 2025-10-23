from __future__ import annotations

from typing import Any, Dict, Mapping, MutableMapping


def get_by_path(data: Mapping[str, Any], dot_path: str, default: Any | None = None) -> Any:
    cur: Any = data
    for key in dot_path.split(".") if dot_path else []:
        if not isinstance(cur, Mapping) or key not in cur:
            return default
        cur = cur[key]
    return cur


def set_by_path(data: MutableMapping[str, Any], dot_path: str, value: Any) -> None:
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
    res: Dict[str, Any] = dict(base)
    for k, v in overlay.items():
        if k in res and isinstance(res[k], dict) and isinstance(v, Mapping):
            res[k] = deep_merge(res[k], v)
        else:
            res[k] = v  # type: ignore[index]
    return res
