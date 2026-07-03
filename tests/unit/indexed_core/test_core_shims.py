"""Coverage for core protocol re-export shims."""

import pytest


@pytest.mark.parametrize(
    "import_path,attr",
    [
        ("core.v1.connectors", "BaseConnector"),
        ("core.v1.connectors.base", "DocumentReader"),
        ("core.v1.connectors.metadata", "ConnectorMetadata"),
        ("core.v1.constants", "DEFAULT_INDEXER"),
    ],
)
def test_core_shim_reexports(import_path: str, attr: str) -> None:
    import importlib

    mod = importlib.import_module(import_path)
    assert hasattr(mod, attr)
