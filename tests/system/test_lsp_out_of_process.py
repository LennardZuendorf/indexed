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


# ---------------------------------------------------------------------------
# Tier 1 evidence: one checked-in stdio transcript and golden payload per new
# method. The files under ``lsp_evidence/`` are the acceptance artifacts for
# ``textDocument/definition``, ``textDocument/references`` and
# ``publishDiagnostics``; the tests below regenerate the exchange from a real
# subprocess and fail if it no longer matches what is committed. See
# ``lsp_evidence/README.md`` for how they were captured and how to refresh them.
# ---------------------------------------------------------------------------

EVIDENCE_DIR = Path(__file__).parent / "lsp_evidence"
GOLDEN_DIR = EVIDENCE_DIR / "golden"
TRANSCRIPT_DIR = EVIDENCE_DIR / "transcripts"


def _normalize(value: Any, corpus: Path) -> Any:
    """Make a recorded session comparable across machines.

    Two things differ on every run and carry no evidence: the fixture's temp
    path (in every URI) and the package version (in ``serverInfo``). Everything
    else — ids, methods, ranges, messages — must match the committed file
    byte for byte, which is the point of committing it.
    """
    corpus_uri = corpus.as_uri()

    def walk(node: Any) -> Any:
        if isinstance(node, str):
            return node.replace(corpus_uri, "file://<corpus>")
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, dict):
            return {key: walk(item) for key, item in node.items()}
        return node

    normalized = walk(value)
    for frame in normalized:
        answer = frame.get("server", {})
        result = answer.get("result")
        if isinstance(result, dict) and "serverInfo" in result:
            result["serverInfo"]["version"] = "<version>"
    return normalized


def _assert_committed(path: Path, actual: Any) -> None:
    text = json.dumps(actual, indent=2) + "\n"
    if os.environ.get("INDEXED_LSP_EVIDENCE_UPDATE") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    assert path.is_file(), f"missing committed evidence: {path}"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, (
        f"{path.name} no longer matches the server. Re-run with "
        "INDEXED_LSP_EVIDENCE_UPDATE=1 and review the diff as a behaviour change."
    )


def _close_session(session: LspSession, request_id: int) -> None:
    session.request(request_id, "shutdown")
    session.notify("exit")
    assert session.close() == 0


#: Tier 1 capability → the evidence file stem that proves it. Adding a
#: capability to `initialize` without adding it here (and adding the files)
#: fails the guard below.
TIER1_EVIDENCE = {
    "definitionProvider": "definition",
    "referencesProvider": "references",
    "textDocumentSync": "diagnostics",
}

#: Advertised since Tier 0, proven over stdio by
#: `test_lsp_stdio_session_covers_tier_zero` (hover markdown, symbol locations).
TIER0_COVERED = {"hoverProvider", "workspaceSymbolProvider"}


def test_every_advertised_capability_has_evidence() -> None:
    """No capability ships without a committed transcript behind it."""
    frames = json.loads((TRANSCRIPT_DIR / "diagnostics.json").read_text("utf-8"))
    answers = [
        frame["server"] for frame in frames if frame.get("server", {}).get("id") == 1
    ]
    assert len(answers) == 1, "the transcript must record exactly one initialize"
    advertised = answers[0]["result"]["capabilities"]

    assert set(advertised) == set(TIER1_EVIDENCE) | TIER0_COVERED, (
        "the advertised capability set moved without moving this guard: "
        f"{sorted(set(advertised))}"
    )
    for capability, stem in TIER1_EVIDENCE.items():
        assert (TRANSCRIPT_DIR / f"{stem}.json").is_file(), (
            f"{capability} is advertised but has no committed transcript"
        )
        assert (GOLDEN_DIR / f"{stem}.json").is_file(), (
            f"{capability} is advertised but has no golden payload"
        )


def test_lsp_definition_transcript_and_golden(
    local_workspace, lsp_corpus: Path
) -> None:
    """``textDocument/definition`` over stdio: an exact span, then a file-level range."""
    _create_collection(lsp_corpus)
    sample, notes = lsp_corpus / "sample.py", lsp_corpus / "notes.md"
    span_params = {
        "textDocument": {"uri": sample.as_uri()},
        "position": {"line": 0, "character": 5},  # inside "alpha"
    }
    file_level_params = {
        "textDocument": {"uri": notes.as_uri()},
        "position": {"line": 2, "character": 3},  # inside the "Scoring" heading
    }
    session = LspSession(local_workspace.root)
    try:
        session.request(1, "initialize", {"capabilities": CLIENT_CAPABILITIES})
        session.notify("initialized", {})
        span = session.request(2, "textDocument/definition", span_params)["result"]
        file_level = session.request(3, "textDocument/definition", file_level_params)[
            "result"
        ]
        _close_session(session, 4)
    finally:
        if session.process.poll() is None:
            session.process.kill()

    # Chunk-level, not a symbol table: the chunk carrying "def alpha" comes
    # first (its own indexed span, lines 0-1), and the chunk that merely calls
    # alpha (lines 4-5) is also a chunk that mentions the identifier. That
    # second hit is the documented limitation, frozen here so it cannot drift
    # silently.
    assert span == [
        {
            "uri": sample.as_uri(),
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 1, "character": 12},
            },
        },
        {
            "uri": sample.as_uri(),
            "range": {
                "start": {"line": 4, "character": 0},
                "end": {"line": 5, "character": 18},
            },
        },
    ]
    # Notes.md is a span-less source (heading chunk): the honest answer is the
    # document's measured extent, never a fabricated 0,0.
    assert file_level == [
        {
            "uri": notes.as_uri(),
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": 5, "character": 0},
            },
        }
    ]

    _assert_committed(
        TRANSCRIPT_DIR / "definition.json", _normalize(session.transcript, lsp_corpus)
    )
    _assert_committed(
        GOLDEN_DIR / "definition.json",
        _normalize(
            [
                {
                    "method": "textDocument/definition",
                    "params": span_params,
                    "result": span,
                },
                {
                    "method": "textDocument/definition",
                    "params": file_level_params,
                    "result": file_level,
                },
            ],
            lsp_corpus,
        ),
    )


def test_lsp_references_transcript_and_golden(
    local_workspace, lsp_corpus: Path
) -> None:
    """``textDocument/references`` over stdio: plural, and ``[]`` never ``null``."""
    _create_collection(lsp_corpus)
    sample = lsp_corpus / "sample.py"
    params = {
        "textDocument": {"uri": sample.as_uri()},
        "position": {"line": 0, "character": 5},  # inside "alpha"
        "context": {"includeDeclaration": True},
    }
    session = LspSession(local_workspace.root)
    try:
        session.request(1, "initialize", {"capabilities": CLIENT_CAPABILITIES})
        session.notify("initialized", {})
        references = session.request(2, "textDocument/references", params)["result"]
        empty = session.request(
            3,
            "textDocument/references",
            {
                "textDocument": {"uri": sample.as_uri()},
                "position": {"line": 2, "character": 0},  # blank line, no token
                "context": {"includeDeclaration": True},
            },
        )["result"]
        _close_session(session, 4)
    finally:
        if session.process.poll() is None:
            session.process.kill()

    # Every chunk of the file that mentions "alpha" as a whole token: the
    # declaration chunk first, then the chunk that calls it. Chunks carry no
    # declaration bit, so includeDeclaration cannot remove the declaration — it
    # is returned as one of the references.
    assert [location["range"] for location in references] == [
        {"start": {"line": 0, "character": 0}, "end": {"line": 1, "character": 12}},
        {"start": {"line": 4, "character": 0}, "end": {"line": 5, "character": 18}},
    ]
    assert all(location["uri"] == sample.as_uri() for location in references)
    # LSP treats null here as a protocol violation: no references is [].
    assert empty == []

    _assert_committed(
        TRANSCRIPT_DIR / "references.json", _normalize(session.transcript, lsp_corpus)
    )
    _assert_committed(
        GOLDEN_DIR / "references.json",
        _normalize(
            [
                {
                    "method": "textDocument/references",
                    "params": params,
                    "result": references,
                }
            ],
            lsp_corpus,
        ),
    )


def test_lsp_diagnostics_transcript_and_golden(
    local_workspace, lsp_corpus: Path
) -> None:
    """``publishDiagnostics`` over stdio: healthy ``[]``, one provable fact, clear."""
    _create_collection(lsp_corpus)
    sample = lsp_corpus / "sample.py"
    uri = sample.as_uri()
    session = LspSession(local_workspace.root)
    steps: list[Dict[str, Any]] = []
    try:
        session.request(1, "initialize", {"capabilities": CLIENT_CAPABILITIES})
        session.notify("initialized", {})

        opened = {"textDocument": {"uri": uri}}
        session.notify("textDocument/didOpen", opened)
        steps.append(
            {
                "trigger": {"method": "textDocument/didOpen", "params": opened},
                "published": session.expect_notification(
                    "textDocument/publishDiagnostics"
                )["params"],
            }
        )

        # Edited AFTER indexing, with no reindex — see lsp_evidence/README.md.
        sample.write_text(
            SAMPLE_PY + "\n\ndef gamma():\n    return 2\n", encoding="utf-8"
        )
        saved = {"textDocument": {"uri": uri}}
        session.notify("textDocument/didSave", saved)
        steps.append(
            {
                "trigger": {"method": "textDocument/didSave", "params": saved},
                "published": session.expect_notification(
                    "textDocument/publishDiagnostics"
                )["params"],
            }
        )

        session.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
        steps.append(
            {
                "trigger": {
                    "method": "textDocument/didClose",
                    "params": {"textDocument": {"uri": uri}},
                },
                "published": session.expect_notification(
                    "textDocument/publishDiagnostics"
                )["params"],
            }
        )
        _close_session(session, 2)
    finally:
        if session.process.poll() is None:
            session.process.kill()

    healthy, stale, cleared = (step["published"] for step in steps)
    assert healthy == {"uri": uri, "diagnostics": []}
    assert cleared == {"uri": uri, "diagnostics": []}
    assert len(stale["diagnostics"]) == 1
    assert stale["diagnostics"][0]["code"] == "index-stale"
    assert stale["diagnostics"][0]["severity"] == 3  # Information, never Error

    # The recorded session is the whole exchange, including the initialize
    # answer, so a reader can see which capabilities the client declared.
    _assert_committed(
        TRANSCRIPT_DIR / "diagnostics.json", _normalize(session.transcript, lsp_corpus)
    )
    _assert_committed(GOLDEN_DIR / "diagnostics.json", _normalize(steps, lsp_corpus))
