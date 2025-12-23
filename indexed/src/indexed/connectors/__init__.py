"""Connector registry for CLI with version compatibility validation.

Provides dynamic discovery of connectors by scanning the `connectors`
package for subpackages that expose a `connector` module containing
classes with a `META` attribute (ConnectorMetadata).
"""

from typing import Dict, List, Type
import warnings

from packaging import version
import importlib
import inspect
import pkgutil

import connectors as connectors_pkg


def _discover_connectors() -> List[Type]:
    """Discover connector classes dynamically.

    Strategy:
    - Iterate subpackages of `connectors`
    - Attempt to import `<subpkg>.connector`
    - Collect classes defined in that module that expose `META`
    """
    discovered: List[Type] = []

    for module_info in pkgutil.iter_modules(
        connectors_pkg.__path__, connectors_pkg.__name__ + "."
    ):
        if not module_info.ispkg:
            continue

        connector_module_name = module_info.name + ".connector"
        try:
            module = importlib.import_module(connector_module_name)
        except Exception:
            # If the subpackage doesn't expose a connector module, skip
            continue

        # Collect classes defined in this module that have META
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if getattr(cls, "__module__", None) != module.__name__:
                continue
            if hasattr(cls, "META"):
                discovered.append(cls)

    return discovered


# List of all available connectors (discovered dynamically)
CONNECTORS = _discover_connectors()


def validate_connector_compatibility(connector_class) -> tuple[bool, str]:
    """Validate connector is compatible with current core version.

    Args:
        connector_class: Connector class with META attribute

    Returns:
        Tuple of (is_compatible, error_message)
    """
    from core.v1 import __version__ as core_version

    meta = connector_class.META

    # Check if connector specifies minimum core version
    if not getattr(meta, "min_core_version", None):
        return True, ""

    try:
        current = version.parse(core_version)
        required = version.parse(meta.min_core_version)

        if current < required:
            return False, (
                f"Connector '{meta.name}' requires core >= {meta.min_core_version}, "
                f"but current version is {core_version}"
            )

        return True, ""
    except Exception as e:
        # If version parsing fails, warn but allow
        warnings.warn(
            f"Could not validate version for connector '{meta.name}': {e}",
            RuntimeWarning,
        )
        return True, ""


def get_connector_registry() -> Dict[str, Type]:
    """Get registry mapping connector names to classes.

    Only includes connectors compatible with current core version.
    Incompatible connectors are skipped with a warning.

    Returns:
        Dict mapping connector names (e.g., "files") to connector classes
    """
    registry: Dict[str, Type] = {}

    for connector_class in CONNECTORS:
        # Skip connectors that don't expose metadata yet
        if not hasattr(connector_class, "META"):
            continue
        # Validate compatibility
        is_compatible, error_msg = validate_connector_compatibility(connector_class)

        if not is_compatible:
            warnings.warn(
                f"Skipping incompatible connector: {error_msg}", RuntimeWarning
            )
            continue

        # Add to registry
        registry[connector_class.META.name] = connector_class

    return registry


def list_connector_names() -> list[str]:
    """List available connector names (only compatible ones)."""
    return list(get_connector_registry().keys())


def check_all_connectors_compatibility() -> Dict[str, tuple[bool, str]]:
    """Check compatibility of all connectors.

    Returns:
        Dict mapping connector names to (is_compatible, message) tuples
    """
    results: Dict[str, tuple[bool, str]] = {}
    for connector_class in CONNECTORS:
        if not hasattr(connector_class, "META"):
            continue
        is_compatible, msg = validate_connector_compatibility(connector_class)
        results[connector_class.META.name] = (is_compatible, msg)
    return results


__all__ = [
    "get_connector_registry",
    "list_connector_names",
    "CONNECTORS",
    "validate_connector_compatibility",
    "check_all_connectors_compatibility",
]
