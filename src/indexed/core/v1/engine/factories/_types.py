"""Shared DI factory type aliases for the update path.

Leaf module: imports only the protocol contracts (downward), so it never
re-introduces a services<->factories cycle.
"""

from collections.abc import Callable

from indexed.protocols import ConnectorRun, Manifest

# The single update-time seam: the app's composition layer supplies this, and it
# dispatches to the right connector's ``from_manifest`` for a collection's stored
# manifest. Core calls it once for every source — no per-connector branches.
ManifestFactory = Callable[[Manifest, str], ConnectorRun]
