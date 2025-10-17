"""Test configuration and shared fixtures."""
import sys
from pathlib import Path

# Add source directories to Python path for test imports
indexed_src = str(Path(__file__).parent.parent / "indexed" / "src")
if indexed_src not in sys.path:
    sys.path.insert(0, indexed_src)

core_src = str(Path(__file__).parent.parent / "packages" / "indexed-core" / "src")
if core_src not in sys.path:
    sys.path.insert(0, core_src)

connectors_src = str(Path(__file__).parent.parent / "packages" / "indexed-connectors" / "src")
if connectors_src not in sys.path:
    sys.path.insert(0, connectors_src)


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers",
        "indexed: Tests for the main indexed application"
    )
    config.addinivalue_line(
        "markers",
        "connectors: Tests for the indexed-connectors package"
    )
    config.addinivalue_line(
        "markers",
        "core: Tests for the indexed-core package"
    )
    config.addinivalue_line(
        "markers",
        "utils: Tests for the indexed-utils package"
    )
    # Add more markers for other packages as needed