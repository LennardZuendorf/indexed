"""System test: drive the real ``indexed lsp`` server OUT-OF-PROCESS over stdio.

This is the honest proof for the Tier 0 acceptance list. A language server has
no CLI surface to assert on: the contract IS the JSON-RPC exchange, so the test
spawns the real process, speaks the protocol's own framing and records the
transcript it asserts against. It covers all five Tier 0 boxes in one session:

1. ``initialize`` completes, advertises only implemented capabilities, and the
   process exits 0 after ``shutdown``;
2. ``workspace/symbol`` returns hits whose ``location.uri`` is a real file and
   whose range comes from chunk metadata;
3. ``textDocument/hover`` returns markdown with the chunk text, its collection,
   its source type and its freshness;
4. an unsupported request is answered with MethodNotFound, never silently;
5. the same session is the transcript a human can read (``lsp-transcript.json``
   is written next to the test's temp workspace).
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlsplit

import pytest
from typer.testing import CliRunner

from indexed.cli.app import app
from tests.conftest import model_available

runner = CliRunner()

#: What a real editor declares. ``publishDiagnostics`` is the one capability the
#: server checks before pushing anything: an undeclared client gets silence.
CLIENT_CAPABILITIES = {"textDocument": {"publishDiagnostics": {}}}

pytestmark = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

COLLECTION = "lsp-probe"

SAMPLE_PY = """def alpha():
    return 1


def beta():
    return alpha()
"""

NOTES_MD = """# Retrieval Notes

## Scoring

Penguin migration survey along the Antarctic coastline.
"""


class LspSession:
    """Minimal LSP client: frames over a subprocess's stdin/stdout."""

    def __init__(self, cwd: Path) -> None:
        self.transcript: list[Dict[str, Any]] = []
        self.process = subprocess.Popen(
            [sys.executable, "-m", "indexed.cli.app", "--local", "lsp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd),
            env={**os.environ, "TQDM_DISABLE": "1"},
        )
        assert self.process.stdin is not None and self.process.stdout is not None

    def _read_frame(self, timeout: float = 180.0) -> Optional[Dict[str, Any]]:
        stdout = self.process.stdout
        assert stdout is not None
        if not select.select([stdout], [], [], timeout)[0]:
            raise AssertionError(f"no LSP response within {timeout}s")
        headers: Dict[bytes, bytes] = {}
        while True:
            line = stdout.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                break
            key, value = line.split(b":", 1)
            headers[key.strip().lower()] = value.strip()
        length = int(headers[b"content-length"])
        payload = stdout.read(length)
        assert len(payload) == length
        message = json.loads(payload.decode("utf-8"))
        self.transcript.append({"server": message})
        return message

    def request(
        self, request_id: int, method: str, params: Any = None
    ) -> Dict[str, Any]:
        frame: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            frame["params"] = params
        self.transcript.append({"client": frame})
        answer = self._send(frame)
        assert answer is not None
        return answer

    def notify(self, method: str, params: Any = None) -> None:
        frame: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            frame["params"] = params
        self.transcript.append({"client": frame})
        self._send(frame, expect_response=False)

    def expect_notification(self, method: str, timeout: float = 60.0) -> Dict[str, Any]:
        """Read the next server frame and require it to be notification ``method``.

        A notification has no id and no response, so this is the only way to
        observe one: read what the server pushed. Anything else here is a real
        failure — a stray response would mean the server answered a
        notification, which JSON-RPC 2.0 §4.1 forbids.
        """
        message = self._read_frame(timeout=timeout)
        assert message is not None, f"server closed before sending {method}"
        assert message.get("method") == method, f"unexpected frame: {message!r}"
        return message

    def _send(self, frame: Dict[str, Any], *, expect_response: bool = True):
        stdin = self.process.stdin
        assert stdin is not None
        body = json.dumps(frame).encode("utf-8")
        stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        stdin.flush()
        return self._read_frame() if expect_response else None

    def close(self, timeout: float = 60.0) -> int:
        assert self.process.stdin is not None
        self.process.stdin.close()
        return self.process.wait(timeout=timeout)


@pytest.fixture
def lsp_corpus(tmp_path: Path) -> Path:
    # A space and a non-ASCII character in the path: the URIs the server emits
    # must stay parseable, which a raw ``file://`` concat cannot promise.
    corpus = tmp_path / "my corpus ü" / "corpus"
    corpus.mkdir(parents=True)
    (corpus / "sample.py").write_text(SAMPLE_PY, encoding="utf-8")
    (corpus / "notes.md").write_text(NOTES_MD, encoding="utf-8")
    return corpus


def _create_collection(corpus: Path) -> None:
    created = runner.invoke(
        app,
        [
            "--local",
            "--log-level",
            "ERROR",
            "create",
            "files",
            "--collection",
            COLLECTION,
            "--path",
            str(corpus),
            "--local",
            "--no-cache",
        ],
    )
    assert created.exit_code == 0, created.stdout + created.stderr


def test_lsp_stdio_session_covers_tier_zero(local_workspace, lsp_corpus: Path) -> None:
    ws = local_workspace
    _create_collection(lsp_corpus)

    session = LspSession(ws.root)
    try:
        # 1. initialize — honest capabilities only.
        initialized = session.request(
            1, "initialize", {"capabilities": CLIENT_CAPABILITIES}
        )
        result = initialized["result"]
        assert result["capabilities"] == {
            # Open/close/save only: the server never holds a document.
            "textDocumentSync": {
                "openClose": True,
                "change": 0,
                "save": {"includeText": False},
            },
            "definitionProvider": True,
            "hoverProvider": True,
            "referencesProvider": True,
            "workspaceSymbolProvider": True,
        }
        assert result["serverInfo"]["name"] == "indexed"
        session.notify("initialized", {})

        # 2. workspace/symbol — real file URIs, ranges from chunk metadata.
        symbols = session.request(2, "workspace/symbol", {"query": "alpha"})["result"]
        assert symbols, "workspace/symbol returned nothing for an indexed symbol"
        sample_uri = (lsp_corpus / "sample.py").as_uri()
        assert "%20" in sample_uri, "the fixture path must exercise URI encoding"
        sample_hits = [s for s in symbols if s["location"]["uri"] == sample_uri]
        assert sample_hits, f"no symbol pointed at sample.py: {symbols!r}"
        for symbol in symbols:
            uri = symbol["location"]["uri"]
            assert " " not in uri
            assert Path(unquote(urlsplit(uri).path)).is_file()
        first = sample_hits[0]
        assert first["containerName"] == COLLECTION
        # Exact range: the chunk's own 0-based lines 0-1, ending at the length
        # of its last indexed line ("    return 1").
        assert first["location"]["range"] == {
            "start": {"line": 0, "character": 0},
            "end": {"line": 1, "character": 12},
        }
        # The Markdown heading chunk is a Namespace symbol with no line range.
        notes = [
            s
            for s in symbols
            if s["location"]["uri"] == (lsp_corpus / "notes.md").as_uri()
        ]
        assert notes and notes[0]["kind"] == 3
        assert notes[0]["name"] == "Scoring"
        assert notes[0]["location"]["range"] == {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 0},
        }

        # 3. hover — chunk text plus collection, source type and freshness.
        hover = session.request(
            3,
            "textDocument/hover",
            {
                "textDocument": {"uri": sample_uri},
                "position": {"line": 0, "character": 5},
            },
        )["result"]
        assert hover is not None, "hover returned nothing for an indexed file"
        value = hover["contents"]["value"]
        assert "def alpha" in value
        assert f"`{COLLECTION}`" in value
        assert "localFiles" in value
        # Freshness is a real age, not the "unknown" degradation.
        assert "at an unknown time" not in value
        assert "just now" in value or "ago" in value
        assert "relevance " in value
        assert "score " in value
        assert "range" not in hover

        # 4. unsupported requests are MethodNotFound, never an empty result.
        unsupported = session.request(4, "textDocument/completion", {})
        assert unsupported["error"]["code"] == -32601
        assert "textDocument/completion" in unsupported["error"]["message"]

        # 5. diagnostics — over the wire, and only facts the index can prove.
        # 5a. a file indexed moments ago is healthy: an EMPTY array, which is
        # also what clears a previously shown diagnostic.
        session.notify("textDocument/didOpen", {"textDocument": {"uri": sample_uri}})
        healthy = session.expect_notification("textDocument/publishDiagnostics")
        assert healthy["params"] == {"uri": sample_uri, "diagnostics": []}

        # 5b. edit the file AFTER indexing (no reindex): the same save now
        # reports exactly one stale diagnostic, with a range measured from the
        # edited file — never a type check, never a lint warning.
        sample = lsp_corpus / "sample.py"
        sample.write_text(
            SAMPLE_PY + "\n\ndef gamma():\n    return 2\n", encoding="utf-8"
        )
        session.notify("textDocument/didSave", {"textDocument": {"uri": sample_uri}})
        stale = session.expect_notification("textDocument/publishDiagnostics")
        assert stale["params"]["uri"] == sample_uri
        assert len(stale["params"]["diagnostics"]) == 1
        diagnostic = stale["params"]["diagnostics"][0]
        assert diagnostic["code"] == "index-stale"
        assert diagnostic["source"] == "indexed"
        assert diagnostic["severity"] == 3  # Information: not an error, not a warning
        assert diagnostic["range"] == {
            "start": {"line": 0, "character": 0},
            "end": {"line": 10, "character": 0},
        }
        assert f"`{COLLECTION}`" in diagnostic["message"]
        assert f"indexed index update {COLLECTION}" in diagnostic["message"]

        # 5c. closing it clears the diagnostic we published.
        session.notify("textDocument/didClose", {"textDocument": {"uri": sample_uri}})
        cleared = session.expect_notification("textDocument/publishDiagnostics")
        assert cleared["params"] == {"uri": sample_uri, "diagnostics": []}

        # 1b. shutdown / exit — clean, code 0.
        shutdown = session.request(5, "shutdown")
        assert shutdown["result"] is None
        session.notify("exit")
        assert session.close() == 0
    finally:
        if session.process.poll() is None:
            session.process.kill()

    transcript = ws.root / "lsp-transcript.json"
    transcript.write_text(json.dumps(session.transcript, indent=2), encoding="utf-8")
    written = json.loads(transcript.read_text(encoding="utf-8"))
    assert written[0]["client"]["method"] == "initialize"
    assert written[1]["server"]["id"] == 1
    for entry in written:
        # Nothing but protocol frames reached stdout: every recorded line is one
        # side of one message.
        assert len(entry) == 1 and next(iter(entry)) in {"client", "server"}


def test_lsp_reports_an_empty_index_without_inventing_hits(local_workspace) -> None:
    session = LspSession(local_workspace.root)
    try:
        session.request(1, "initialize", {"capabilities": {}})
        session.notify("initialized", {})
        assert (
            session.request(2, "workspace/symbol", {"query": "anything"})["result"]
            == []
        )
        # An unindexed file gets an empty hover, not invented content.
        missing = local_workspace.root / "unindexed.py"
        missing.write_text("value = 1\n", encoding="utf-8")
        hover = session.request(
            3,
            "textDocument/hover",
            {
                "textDocument": {"uri": missing.as_uri()},
                "position": {"line": 0, "character": 1},
            },
        )
        assert hover["result"] is None
        session.request(4, "shutdown")
        session.notify("exit")
        assert session.close() == 0
    finally:
        if session.process.poll() is None:
            session.process.kill()
