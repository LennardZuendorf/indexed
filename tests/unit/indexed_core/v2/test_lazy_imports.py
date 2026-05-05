"""Verify v2 packages remain side-effect-free at import time."""

from __future__ import annotations

import subprocess
import sys


def _run(snippet: str) -> str:
    result = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def test_core_v2_import_does_not_load_llama_index() -> None:
    snippet = (
        "import sys; import core.v2; "
        "print('OK' if 'llama_index.core' not in sys.modules else 'LEAKED')"
    )
    assert _run(snippet) == "OK"


def test_core_v2_services_import_does_not_load_llama_index() -> None:
    snippet = (
        "import sys; import core.v2.services; "
        "print('OK' if 'llama_index.core' not in sys.modules else 'LEAKED')"
    )
    assert _run(snippet) == "OK"


def test_index_attribute_resolves_lazily() -> None:
    from core.v2 import Index, IndexConfig

    assert Index is not None
    assert IndexConfig is not None
