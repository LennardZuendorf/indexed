"""Machine stdout purity: a log record must never enter the JSON payload.

`.spec/tech-app.md` (§ Logging Strategy) and the search-output contract reserve
stdout for command results: under `--simple-output` (and, once the result-shape
work lands, `--json`) stdout holds the payload and nothing else. The notices
half is guarded inside the search command; the log half is decided by the sink
the app callback (`indexed.cli.app`) hands to `bootstrap_logging`.

This test drives the REAL wiring end to end — the root app callback runs the
real `bootstrap_logging` (nothing stubbed) and a WARNING fires mid-command —
because a test that stubs logging cannot see the sink at all.
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from loguru import logger as loguru_logger
from typer.testing import CliRunner

from indexed.cli.app import app as root_app
from indexed.cli.knowledge.commands import search as search_cmd

pytestmark = pytest.mark.unit

#: click >= 8.2 captures stdout and stderr separately (no ``mix_stderr`` knob).
runner = CliRunner()

PROBE = "probe-warning-line"

#: One searchable collection with one hit — enough to build the JSON payload.
RAW_RESULTS = {
    "probe-coll": {
        "collectionName": "probe-coll",
        "indexerName": "e5-small",
        "sourceType": "localFiles",
        "results": [
            {
                "id": "docs/search.md",
                "url": "file:///repo/docs/search.md",
                "matchedChunks": [
                    {
                        "chunkNumber": 1,
                        "score": 0.5,
                        "content": {
                            "indexedData": "## Output shape\n\nstdout is the payload.",
                            "metadata": {"headings": ["Search", "Output shape"]},
                        },
                    }
                ],
            }
        ],
    }
}


def _patch_search(monkeypatch) -> None:
    """Run the real command and the real sink — only the engine call is faked."""

    status = Mock()
    status.name = "probe-coll"
    status.indexers = ["default"]
    status.source_type = "localFiles"

    def fake_svc_search(query, configs, **_kwargs):
        # A real record from the default (WARNING) verbosity gate.
        loguru_logger.warning(PROBE)
        return RAW_RESULTS

    ctx = type(
        "MockCtx",
        (),
        {"collections_path": "/tmp/test-collections", "mode": "global"},
    )()

    monkeypatch.setattr(search_cmd, "status", lambda *a, **kw: [status])
    monkeypatch.setattr(search_cmd, "svc_search", fake_svc_search)
    monkeypatch.setattr(search_cmd, "SourceConfig", lambda **kw: Mock())
    monkeypatch.setattr(
        "indexed.cli.composition.resolve_collections_context",
        lambda *a, **kw: ctx,
    )


def test_warning_during_simple_output_search_stays_off_stdout(monkeypatch) -> None:
    _patch_search(monkeypatch)

    result = runner.invoke(root_app, ["--simple-output", "index", "search", "q"])

    assert result.exit_code == 0, result.output
    # The consumer contract: stdout is the payload, so this parse must not see
    # a log line in front of the JSON document.
    payload = json.loads(result.stdout)
    assert payload["query"] == "q"
    assert PROBE not in result.stdout
    # ...and the record really fired — it is relocated, never swallowed.
    assert PROBE in result.stderr
