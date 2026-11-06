"""Configuration for the opt-in collection watcher (``indexed index watch``).

There is deliberately no ``enabled`` switch: nothing starts the watcher
implicitly. Running ``indexed index watch <collection>`` *is* the opt-in — the
loop lives in the foreground of that process and dies with it. These keys only
tune its cadence.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - typing only
    from indexed.config import ConfigService


class WatchConfig(BaseModel):
    """Cadence of the foreground file watcher for one ``localFiles`` collection."""

    debounce_seconds: float = Field(
        default=2.0,
        gt=0,
        description="Quiet period after the last observed change before one update runs",
    )
    poll_interval_seconds: float = Field(
        default=2.0,
        gt=0,
        description="Seconds between scans of the watched source tree",
    )


def resolve_watch_config(config_service: "ConfigService") -> WatchConfig:
    """The bound ``[watch]`` config, or its defaults when the section is absent.

    ``bind().get`` only carries sections that exist in the resolved config file,
    so an unconfigured project (the normal case) must fall back to defaults
    rather than crash. A genuine validation failure for ``watch`` still raises.
    """
    from indexed.config.errors import ConfigValidationError

    try:
        return config_service.bind().get(WatchConfig)
    except ConfigValidationError as exc:
        if getattr(exc, "path", None) == "watch":
            raise
        return WatchConfig()
    except Exception:
        return WatchConfig()


__all__ = ["WatchConfig", "resolve_watch_config"]
