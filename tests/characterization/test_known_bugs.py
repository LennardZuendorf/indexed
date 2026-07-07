"""Characterization: red bug-specs for every CONFIRMED audit bug (foundation/1).

One ``xfail(strict=True)`` spec per CONFIRMED defect in the foundation bug
catalogue (``.spec/features/foundation/tech-bugfixes.md``). Each spec asserts the
DESIRED (correct) behavior, so it FAILS today and will flip to a hard failure
(``xpassed`` under ``strict=True``) the moment the bug is fixed in a later unit —
turning the whole file into a live checklist for the foundation fix work.

Groups → fixing unit:
  A1-A6  search recall      → foundation/2
  B1-B4  storage durability → foundation/3
  C1-C4  security & secrets → foundation/4
  D1-D4  connector fidelity → foundation/5
  E1-E12 honest CLI/MCP     → foundation/6
  F1-F5  reporting          → foundation/6

The 3 PLAUSIBLE bugs (B5, D5, F6) are intentionally excluded. Specs that need
real embeddings/search are gated on ``model_available()``; pure-unit specs are
never gated.
"""

from __future__ import annotations

# Warm the engine through the services package first: this is the import entry
# that resolves the cold-import cycle (importing the factories / creator / a
# searcher directly fails cold — see .spec/lessons.md and test_lifecycle_cloud).
import core.v1.engine.services  # noqa: F401

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from indexed.app import app
from tests.conftest import model_available

runner = CliRunner()

needs_model = pytest.mark.skipif(
    not model_available(),
    reason="Embedding model not cached (requires all-MiniLM-L6-v2)",
)

FIX_A = "fixed in foundation/2"
FIX_B = "fixed in foundation/3"
FIX_C = "fixed in foundation/4"
FIX_D = "fixed in foundation/5"
FIX_E = "fixed in foundation/6"
FIX_F = "fixed in foundation/6"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _local(*args: str, **kwargs):
    """Invoke the CLI in local mode with a quiet base flag set."""
    return runner.invoke(app, ["--local", "--log-level", "ERROR", *args], **kwargs)


def _create_files_collection(name: str, corpus: Path) -> None:
    """Create a real files collection through the CLI (real FAISS + embeddings)."""
    result = _local(
        "create",
        "files",
        "--collection",
        name,
        "--path",
        str(corpus),
        "--local",
        "--no-cache",
    )
    assert result.exit_code == 0, result.stdout + (result.stderr or "")


def _search_service(collections_dir: Path):
    from core.v1.engine.services.search_service import SearchService

    return SearchService(collections_path=str(collections_dir))


# ===========================================================================
# Group A — Search recall correctness → foundation/2
# ===========================================================================


@needs_model
def test_bug_a1_chunker_respects_model_token_window(tmp_path: Path) -> None:
    """A1: a large headingless doc must be split into chunks that each fit the
    embedder's ``max_seq_length`` (max_tokens is ignored today → oversize chunks
    whose tail is silently truncated at embed and thus unsearchable)."""
    from core.v1.engine.indexes.embeddings.sentence_embeder import SentenceEmbedder
    from parsing import PlaintextParser

    sentence = (
        "The nightly ingestion pipeline embeds every document chunk into the "
        "vector index and reconciles the manifest against the on-disk shards. "
    )
    para = sentence * 14  # each paragraph is well past the model window on its own
    doc_text = "\n\n".join(f"{para} marker{i}." for i in range(3))
    src = tmp_path / "headingless.txt"
    src.write_text(doc_text)

    doc = PlaintextParser(max_tokens=512).parse(src)

    embedder = SentenceEmbedder()
    max_seq_length = embedder.model.max_seq_length
    tokenizer = embedder.model.tokenizer
    token_counts = [
        len(tokenizer.encode(chunk.text, add_special_tokens=False))
        for chunk in doc.chunks
    ]

    assert len(doc.chunks) > 1, "a multi-window document must produce >1 chunk"
    assert max(token_counts) <= max_seq_length, (
        f"every chunk must fit the model window ({max_seq_length}); "
        f"got a chunk of {max(token_counts)} tokens"
    )


def test_bug_a2_code_chunker_slices_bytes_not_decoded_str(tmp_path: Path) -> None:
    """A2: a code file whose first function contains a non-ASCII comment must
    still yield byte-exact chunks for later functions (tree-sitter byte offsets
    are wrongly applied to the decoded ``str`` today → every later slice shifts)."""
    from parsing import CodeChunker

    source = (
        "def first():\n"
        "    # café ééé non-ascii comment adds multibyte bytes here\n"
        "    return 1\n"
        "\n"
        "def second_function_marker():\n"
        "    return 'SECOND_BODY_UNIQUE'\n"
    )
    src = tmp_path / "s.py"
    src.write_bytes(source.encode("utf-8"))

    chunks = CodeChunker(max_tokens=512).chunk_file(src)

    assert any(
        chunk.text.lstrip().startswith("def second_function_marker") for chunk in chunks
    ), (
        "the second function's chunk must be byte-exact "
        f"(got: {[c.text[:40] for c in chunks]!r})"
    )


def test_bug_a3_plaintext_splitter_handles_no_blank_lines(tmp_path: Path) -> None:
    """A3: a large file with no blank lines (e.g. a log) must split into multiple
    chunks (the generic splitter breaks only on ``\\n\\n`` today → one chunk that
    is truncated at the model window)."""
    from parsing import PlaintextParser

    log = tmp_path / "big.log"
    log.write_text(
        "\n".join(
            f"2026-07-06 12:00:{i % 60:02d} INFO handled request id={i} "
            f"latency={i * 3}ms path=/api/v1/resource/{i}"
            for i in range(2000)
        )
    )

    doc = PlaintextParser(max_tokens=512).parse(log)

    assert len(doc.chunks) > 1, (
        "a 2000-line blank-line-free file must produce multiple chunks, "
        f"got {len(doc.chunks)}"
    )


@needs_model
def test_bug_a4_embedder_distinguishes_beyond_model_window() -> None:
    """A4: two documents sharing an identical 256-token prefix but differing
    suffixes must embed to a non-zero distance (the model truncates at 256 with
    no chunk-time guard, so both embed identically → distance 0)."""
    import numpy as np

    from core.v1.engine.indexes.embeddings.sentence_embeder import SentenceEmbedder

    embedder = SentenceEmbedder()
    tokenizer = embedder.model.tokenizer
    filler = (
        "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo "
        "lima mike november oscar papa quebec romeo sierra tango "
    ) * 20
    prefix = tokenizer.decode(tokenizer.encode(filler, add_special_tokens=False)[:300])
    doc_a = prefix + " zzz_unique_suffix_alpha the caldera volcano erupted loudly"
    doc_b = prefix + " qqq_unique_suffix_beta the penguin migration survey ran"

    vec_a = embedder.embed_batch([doc_a])[0]
    vec_b = embedder.embed_batch([doc_b])[0]
    distance = float(np.sum((vec_a - vec_b) ** 2))

    assert distance > 1e-6, (
        "documents differing past the model window must not collide "
        f"(squared-L2 distance was {distance})"
    )


@needs_model
def test_bug_a5_topk_starvation_returns_all_matching_docs(
    local_workspace, tmp_path: Path
) -> None:
    """A5: when one large many-chunk document and three smaller documents all
    match a query, ``max_docs>=4`` must return all four distinct documents (the
    large doc's chunks fill the fixed neighbour pool today → other docs starve)."""
    ws = local_workspace
    query = "kubernetes horizontal pod autoscaler scales pods on cpu metrics"
    corpus = ws.root / "k8s"
    corpus.mkdir()
    big_paras = [(query + ". ") * 18 + f"section {j}" for j in range(20)]
    (corpus / "big.txt").write_text("\n\n".join(big_paras))
    (corpus / "s1.txt").write_text(
        "Our platform team manages several clusters and reviews scaling "
        "behaviour during peak traffic windows.\n"
    )
    (corpus / "s2.txt").write_text(
        "The operations runbook describes how workloads consume compute "
        "resources across nodes over time.\n"
    )
    (corpus / "s3.txt").write_text(
        "Engineers tune resource requests so services stay responsive when "
        "demand grows quickly.\n"
    )

    _create_files_collection("a5", corpus)
    result = _search_service(ws.collections_dir).search(
        query, max_docs=4, include_matched_chunks=True
    )["a5"]

    assert "error" not in result, result
    assert len(result["results"]) >= 4, (
        "all four matching documents must be returned, not starved by the "
        f"large document (got {len(result['results'])})"
    )


def test_bug_a6_score_threshold_accepts_real_l2_range() -> None:
    """A6: ``score_threshold`` must accept the engine's real squared-L2 range
    (``[0, 4]``); today it is capped at ``le=1.0``, so a sane 1.5 threshold (the
    service docstring's own example) fails validation."""
    from core.v1.config_models import CoreV1SearchConfig

    cfg = CoreV1SearchConfig(score_threshold=1.5)
    assert cfg.score_threshold == 1.5


# ===========================================================================
# Group B — Storage durability → foundation/3
# ===========================================================================


@needs_model
def test_bug_b1_deletions_only_update_persists_faiss(
    local_workspace,
) -> None:
    """B1: after a deletions-only update, a reloaded collection must search
    cleanly with the deleted content gone (today the FAISS file is never
    re-saved, so a query whose neighbours hit the orphan vector raises
    ``KeyError`` → the whole collection errors permanently)."""
    ws = local_workspace
    corpus = ws.root / "corpus"
    corpus.mkdir()
    (corpus / "keep1.txt").write_text(
        "General notes about deployment pipelines and yaml manifests.\n"
    )
    (corpus / "keep2.txt").write_text(
        "Observability dashboards track latency and error budgets weekly.\n"
    )
    (corpus / "needle.txt").write_text(
        "The penguin migration survey recorded record numbers along the "
        "Antarctic coastline in austral summer.\n"
    )
    _create_files_collection("b1", corpus)

    (corpus / "needle.txt").unlink()  # deletions-only update
    updated = _local("update", "b1")
    assert updated.exit_code == 0, updated.stdout

    result = _search_service(ws.collections_dir).search(
        "penguin migration survey Antarctic coastline",
        max_docs=5,
        include_matched_chunks=True,
    )["b1"]

    assert "error" not in result, (
        f"reloaded collection must not error after a deletions-only update: {result}"
    )
    assert not any(Path(doc["id"]).name == "needle.txt" for doc in result["results"]), (
        "deleted content must be absent from results"
    )


def test_bug_b2_zero_chunk_batch_does_not_crash_indexer() -> None:
    """B2: indexing zero chunks (a source of empty-body documents) must be a
    safe no-op, not a crash (``encode([])`` returns shape ``(0,)`` which FAISS
    ``add_with_ids`` fails to unpack today)."""
    import numpy as np

    from core.v1.engine.indexes.indexers.faiss_indexer import FaissIndexer

    class StubEmbedder:
        def get_number_of_dimensions(self) -> int:
            return 8

        def embed_batch(self, texts, batch_size=64, progress_callback=None):
            # mirrors SentenceTransformer.encode([]) -> shape (0,)
            return np.asarray([], dtype="float32")

    indexer = FaissIndexer("stub", StubEmbedder())
    indexer.index_texts([], [])  # must not raise
    assert indexer.get_size() == 0


def test_bug_b3_config_set_null_preserves_file(local_workspace) -> None:
    """B3: a ``config set`` with an unserializable value (``null`` → ``None``)
    must leave ``config.toml`` byte-identical (today ``TomlStore.write`` truncates
    the file in ``"w"`` mode, then ``tomlkit.dump`` raises → file lost)."""
    ws = local_workspace
    config_toml = ws.local_root / "config.toml"

    seeded = _local("config", "set", "core.v1.indexing.chunk_size", "512")
    assert seeded.exit_code == 0, seeded.stdout
    before = config_toml.read_bytes()
    assert before, "expected a non-empty config.toml to exist before the bad write"

    _local("config", "set", "core.v1.indexing.chunk_size", "null")

    after = config_toml.read_bytes() if config_toml.exists() else b""
    assert after == before, "a failed set must leave config.toml byte-identical"


def test_bug_b4_failed_create_preserves_existing_collection(tmp_path: Path) -> None:
    """B4: a create that fails mid-build must leave the pre-existing collection
    intact (today ``__create_collection`` deletes the collection folder up front,
    before reading anything → a failed re-create destroys prior data)."""
    from core.v1.engine.core.documents_collection_creator import (
        OPERATION_TYPE,
        DocumentCollectionCreator,
    )
    from core.v1.engine.persisters.disk_persister import DiskPersister

    base = tmp_path / "collections"
    keep = base / "keep"
    keep.mkdir(parents=True)
    (keep / "manifest.json").write_text(
        json.dumps({"collectionName": "keep", "numberOfDocuments": 3})
    )
    (keep / "marker.txt").write_text("precious original data")

    class RaisingReader:
        def get_number_of_documents(self):
            raise RuntimeError("simulated mid-build failure (bad path / network)")

        def read_all_documents(self):
            raise RuntimeError("unreachable")

        def get_reader_details(self):
            return {}

    creator = DocumentCollectionCreator(
        collection_name="keep",
        document_reader=RaisingReader(),
        document_converter=object(),
        document_indexers=[object()],
        persister=DiskPersister(base_path=str(base)),
        operation_type=OPERATION_TYPE.CREATE,
    )

    with pytest.raises(Exception):
        creator.run()

    assert (keep / "manifest.json").exists(), (
        "a failed re-create must not destroy the existing collection"
    )


# ===========================================================================
# Group C — Security & secrets → foundation/4
# ===========================================================================


def test_bug_c1_config_set_secret_never_hits_toml_or_stdout(
    local_workspace,
) -> None:
    """C1: setting a secret must route to ``.env`` and be masked — never written
    to ``config.toml`` in cleartext nor echoed in the summary card
    (``_is_sensitive_key`` is defined but applied on none of these paths today)."""
    ws = local_workspace
    config_toml = ws.local_root / "config.toml"

    result = _local("config", "set", "sources.jira.api_token", "supersecret123")

    toml_text = config_toml.read_text() if config_toml.exists() else ""
    assert "supersecret123" not in toml_text, "secret must not land in config.toml"
    assert "supersecret123" not in (result.stdout or ""), (
        "secret must not be echoed to stdout"
    )


def test_bug_c2_env_secret_not_baked_into_config(local_workspace, monkeypatch) -> None:
    """C2: an ``INDEXED__*`` env-supplied secret must stay an in-memory overlay —
    an unrelated ``config set`` must not round-trip it into ``config.toml`` (today
    ``save_raw`` persists the env-merged dict)."""
    ws = local_workspace
    monkeypatch.setenv("INDEXED__SOURCES__JIRA__API_TOKEN", "envsecretXYZ")

    _local("config", "set", "core.v1.indexing.chunk_size", "256")

    config_toml = ws.local_root / "config.toml"
    toml_text = config_toml.read_text() if config_toml.exists() else ""
    assert "envsecretXYZ" not in toml_text, (
        "env-supplied secret must not be persisted into config.toml"
    )


def test_bug_c3_url_guard_rejects_backslash_authority() -> None:
    """C3: ``is_same_origin`` must reject a parser-differential authority like
    ``https://evil.com\\@good.com`` (urlsplit sees host ``good.com`` and approves,
    but the HTTP client sends credentials to ``evil.com``)."""
    from connectors._url_guard import is_same_origin

    assert is_same_origin("https://evil.com\\@good.com/x", "https://good.com") is False


def test_bug_c4_env_writer_quotes_secrets(tmp_path: Path) -> None:
    """C4: a secret containing ``" #"`` must survive a dotenv round-trip
    byte-identical (the writer emits unquoted ``KEY=value`` today, so ``#`` starts
    a comment and the token is truncated on reload)."""
    from dotenv import dotenv_values

    from indexed_config.env_writer import EnvFileWriter

    env_path = tmp_path / ".env"
    secret = "abc #x def"
    EnvFileWriter(lambda: str(env_path)).write("JIRA_TOKEN", secret)

    reloaded = dotenv_values(str(env_path)).get("JIRA_TOKEN")
    assert reloaded == secret, (
        f"token must round-trip unchanged through dotenv (got {reloaded!r})"
    )


# ===========================================================================
# Group D — Connector fidelity → foundation/5
# ===========================================================================


@pytest.mark.xfail(strict=True, reason=FIX_D)
def test_bug_d1_jira_attachment_follows_redirect(monkeypatch) -> None:
    """D1: a Jira Cloud attachment served via a 302 to the media host must be
    downloaded (the async client lacks ``follow_redirects`` and
    ``raise_for_status`` raises on the 302 → the attachment is silently dropped)."""
    import asyncio

    import httpx

    from connectors.jira import async_jira_cloud_reader as mod
    from connectors.jira.async_jira_cloud_reader import AsyncJiraCloudDocumentReader

    class FakeResp:
        def __init__(self, status, content=b"", location=None):
            self.status_code = status
            self.content = content
            self.headers = {"location": location} if location else {}

        @property
        def is_success(self):
            return 200 <= self.status_code < 300

        def raise_for_status(self):
            if not self.is_success:
                raise httpx.HTTPStatusError(
                    str(self.status_code), request=None, response=None
                )

    class FakeClient:
        def __init__(self, follow_redirects=False, **kwargs):
            self.follow_redirects = follow_redirects

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, follow_redirects=None, **kwargs):
            follows = (
                self.follow_redirects if follow_redirects is None else follow_redirects
            )
            if follows:
                return FakeResp(200, content=b"PDFBYTES")
            return FakeResp(302, location="https://media.example.com/x")

    monkeypatch.setattr(mod.httpx, "AsyncClient", lambda **kwargs: FakeClient(**kwargs))

    reader = AsyncJiraCloudDocumentReader(
        base_url="https://acme.atlassian.net",
        query="project = TEST",
        email="e@acme.com",
        api_token="token",
        include_attachments=True,
        max_attachment_size_mb=10,
    )
    issues = [
        {
            "key": "JIRA-1",
            "fields": {
                "attachment": [
                    {
                        "filename": "report.pdf",
                        "content": "https://acme.atlassian.net/att/1",
                        "size": 1024,
                        "mimeType": "application/pdf",
                    }
                ]
            },
        }
    ]

    enriched = asyncio.run(reader._enrich_with_attachments(issues))
    attachments = enriched[0].get("attachments", [])
    assert any(att.get("bytes") == b"PDFBYTES" for att in attachments), (
        "attachment body must be downloaded across the 302 redirect"
    )


@pytest.mark.xfail(strict=True, reason=FIX_D)
def test_bug_d2_change_tracker_unquotes_non_ascii_paths(tmp_path: Path) -> None:
    """D2: the git change-tracker must C-unquote git's octal-escaped path output
    so non-ASCII filenames are matched (``"caf\\303\\251.txt"`` is compared raw
    today → ``café.py`` is never re-indexed)."""
    from connectors.files.change_tracker import ChangeTracker

    tracker = ChangeTracker(str(tmp_path), strategy="git")
    git_output = 'M\t"caf\\303\\251.txt"\n'  # git's C-quoted form of café.txt

    result = tracker._parse_diff_name_status(git_output, None, {"café.txt"})

    assert result.get("café.txt") == "modified", (
        f"non-ASCII path must be unquoted and matched (got {result!r})"
    )


@pytest.mark.xfail(strict=True, reason=FIX_D)
def test_bug_d3_jira_adf_leaf_nodes_extracted() -> None:
    """D3: ADF leaf nodes carry their data in ``attrs`` (mention display name,
    inlineCard url); ``_parse_adf_nodes`` walks only ``content`` today → these are
    dropped from indexed Jira text."""
    from connectors.jira.unified_jira_document_converter import (
        UnifiedJiraDocumentConverter,
    )

    adf_doc = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Assigned to "},
                    {
                        "type": "mention",
                        "attrs": {"id": "557058:abc", "text": "@Alice"},
                    },
                    {"type": "text", "text": " see "},
                    {
                        "type": "inlineCard",
                        "attrs": {"url": "https://example.com/card"},
                    },
                ],
            }
        ],
    }

    text = UnifiedJiraDocumentConverter()._parse_adf_content(adf_doc)

    assert "@Alice" in text, "mention display name must be in the text"
    assert "https://example.com/card" in text, "inlineCard url must be in the text"


@pytest.mark.xfail(strict=True, reason=FIX_D)
def test_bug_d4_confluence_image_filename_extracted() -> None:
    """D4: Confluence storage-format ``ac:image``/``ri:attachment`` filenames live
    in attributes; ``get_text()`` extracts only text nodes today → the filename is
    dropped from indexed content."""
    from connectors.confluence.unified_confluence_document_converter import (
        UnifiedConfluenceDocumentConverter,
    )

    xml = '<p>See <ac:image><ri:attachment ri:filename="diagram.png"/></ac:image></p>'
    text = UnifiedConfluenceDocumentConverter._get_cleaned_body(
        {"body": {"storage": {"value": xml}}}
    )

    assert "diagram.png" in text, "image filename must appear in the cleaned text"


# ===========================================================================
# Group E — Honest CLI & MCP behavior → foundation/6
# ===========================================================================


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e1_missing_collection_fails_cleanly(local_workspace) -> None:
    """E1: a missing collection must produce a clean non-zero exit — never a raw
    ``IndexError`` traceback for ``search -c`` and never exit 0 for ``update``
    (the zero-filled placeholder status defeats every guard today)."""
    search = _local(
        "--simple-output", "search", "hello", "--collection", "nonexistent-xyz"
    )
    assert search.exception is None, (
        f"search of a missing collection must not raise a traceback: "
        f"{search.exception!r}"
    )

    update = _local("update", "nonexistent-xyz")
    assert update.exit_code != 0, "update of a missing collection must exit non-zero"


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e2_rich_markup_injection_does_not_crash() -> None:
    """E2: rendering a search result whose content carries Rich markup like
    ``[/bold]`` (or ``arr[i]``) must not crash and must show both substrings
    verbatim (the card row builder feeds untrusted content straight into
    ``Text.from_markup`` today → ``MarkupError``)."""
    import io

    from rich.console import Console

    from indexed.utils.components.cards import create_info_rows_with_spacing

    content = "match: arr[i] returned [/bold] unexpectedly"
    renderables = create_info_rows_with_spacing([("Excerpt", content)])

    console = Console(file=io.StringIO(), width=200, force_terminal=False)
    for renderable in renderables:
        console.print(renderable)
    output = console.file.getvalue()

    assert "arr[i]" in output and "[/bold]" in output, (
        "markup-bearing content must render verbatim without raising"
    )


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e3_verbose_flag_is_honored(local_workspace) -> None:
    """E3: ``--verbose`` must actually raise the effective log level (each command
    calls ``setup_root_logger(None)`` → ``bootstrap_logging("WARNING")`` today,
    clobbering the callback's resolved level back to WARNING)."""
    from indexed.utils.logging import get_current_log_level

    runner.invoke(app, ["--verbose", "--local", "search", "hello"])

    assert get_current_log_level() in ("INFO", "DEBUG"), (
        f"--verbose must leave the log level at INFO/DEBUG, "
        f"got {get_current_log_level()!r}"
    )


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e4_failed_create_does_not_persist_overrides(local_workspace) -> None:
    """E4: a failed ``create`` must not persist its CLI overrides to
    ``config.toml`` (the bad path is written before creation is attempted today →
    a later create silently reuses it)."""
    ws = local_workspace

    result = _local(
        "create",
        "files",
        "--collection",
        "e4",
        "--path",
        "/nonexistent-bad-path-xyz",
        "--local",
        "--no-cache",
    )
    assert result.exit_code != 0

    config_toml = ws.local_root / "config.toml"
    toml_text = config_toml.read_text() if config_toml.exists() else ""
    assert "/nonexistent-bad-path-xyz" not in toml_text, (
        "a failed create must not leave its path override in config.toml"
    )


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e5_empty_files_path_is_rejected(local_workspace) -> None:
    """E5: pressing Enter at the files-path prompt must be rejected, not accepted
    as ``""`` (which equals ``Path(".")`` and indexes the whole CWD today)."""
    result = _local("create", "files", "--collection", "e5", input="\n")
    output = result.stdout or ""

    assert "Scanning Files" not in output, (
        "empty path input must be rejected before the current directory is scanned"
    )


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e6_cloud_detection_normalizes_url() -> None:
    """E6: Cloud/Server detection must normalize whitespace and a trailing slash
    (``endswith(".atlassian.net")`` misroutes ``https://x.atlassian.net/`` to
    Server → wrong config class + credential scheme)."""
    from indexed.knowledge.commands.create import _is_cloud

    assert _is_cloud("https://x.atlassian.net/ ") is True


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e7_files_path_stored_normalized() -> None:
    """E7: the files source path must be stored expanded + absolute in the reader
    details / manifest (it is stored raw today, so an ``update`` from a different
    CWD resolves a relative / ``~`` path against the wrong directory)."""
    import os

    from connectors.files.files_document_reader import FilesDocumentReader

    base_path = FilesDocumentReader(
        base_path="./some/relative/docs"
    ).get_reader_details()["basePath"]

    assert os.path.isabs(base_path), (
        f"the stored files path must be normalized to an absolute path, "
        f"got {base_path!r}"
    )


@needs_model
@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e8_update_all_continues_past_failure(local_workspace, monkeypatch) -> None:
    """E8: ``update`` (all) must attempt every collection even when one fails
    (today it ``break``s the loop on the first failure → later collections stay
    stale and unlisted)."""
    ws = local_workspace
    for name in ("cola", "colb"):
        corpus = ws.root / name
        corpus.mkdir()
        (corpus / "f.txt").write_text(
            f"content for collection {name} about search indexing and retrieval.\n"
        )
        _create_files_collection(name, corpus)

    import indexed.knowledge.commands.update as update_mod

    attempted: list[str] = []

    def failing_update_service(configs, **kwargs):
        attempted.append(configs[0].name)
        raise RuntimeError(f"simulated failure updating {configs[0].name}")

    monkeypatch.setattr(update_mod, "update_service", failing_update_service)

    _local("update")

    assert len(attempted) >= 2, (
        f"every collection must be attempted despite a failure, got {attempted!r}"
    )


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e9_mcp_has_no_response_caching() -> None:
    """E9: the MCP server must not serve stale results — the ~1h
    ``ResponseCachingMiddleware`` (with no re-index invalidation) must be gone."""
    from fastmcp.server.middleware.caching import ResponseCachingMiddleware

    import indexed.mcp.server as server

    assert not any(
        isinstance(mw, ResponseCachingMiddleware) for mw in server.mcp.middleware
    ), "ResponseCachingMiddleware must not be registered on the MCP server"


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e10_mcp_surfaces_per_collection_failure() -> None:
    """E10: a per-collection search failure must be surfaced to the LLM, not
    ``continue``d past (an agent sees "0 matches" instead of "index failed"
    today)."""
    from indexed.mcp.formatting import format_search_results_for_llm

    out = format_search_results_for_llm(
        {
            "broken": {"error": "index failed"},
            "good": {"collectionName": "good", "results": []},
        },
        "q",
    )

    assert "broken" in json.dumps(out), (
        "a failed collection must be reported in the LLM envelope, not swallowed"
    )


@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e11_missing_collection_not_reported_healthy(local_workspace) -> None:
    """E11: a nonexistent collection must not be reported as a zero-filled healthy
    status (the placeholder returned by ``InspectService.status`` makes MCP show a
    missing collection as an empty-but-healthy record today)."""
    from core.v1.engine.services.inspect_service import InspectService

    statuses = InspectService(
        collections_path=str(local_workspace.collections_dir)
    ).status(["missing-xyz"])

    assert statuses == [], (
        "a missing collection must be omitted, not returned as a healthy zero "
        f"record (got {statuses!r})"
    )


@needs_model
@pytest.mark.xfail(strict=True, reason=FIX_E)
def test_bug_e12_cli_search_honors_config_max_docs(local_workspace) -> None:
    """E12: the CLI ``search`` must honor ``[core.v1.search] max_docs`` so CLI and
    MCP agree (the CLI ignores the section entirely today, using only ``--limit``)."""
    ws = local_workspace
    corpus = ws.root / "docs"
    corpus.mkdir()
    for i in range(8):
        (corpus / f"d{i}.txt").write_text(
            f"database connection pooling and query optimization strategy {i} "
            "for postgres performance tuning.\n"
        )
    _create_files_collection("e12", corpus)

    set_result = _local("config", "set", "core.v1.search.max_docs", "3")
    assert set_result.exit_code == 0, set_result.stdout

    search = _local(
        "--simple-output",
        "search",
        "database connection pooling query optimization postgres",
        "--collection",
        "e12",
    )
    payload = json.loads(search.stdout)
    distinct_docs = {r["document_id"] for r in payload["results"]}

    assert len(distinct_docs) <= 3, (
        "CLI search must respect the configured max_docs=3, "
        f"got {len(distinct_docs)} distinct documents"
    )


# ===========================================================================
# Group F — Reporting → foundation/6
# ===========================================================================


@needs_model
@pytest.mark.xfail(strict=True, reason=FIX_F)
def test_bug_f1_index_size_is_bytes_not_vector_count(local_workspace) -> None:
    """F1: ``inspect`` must report a real index byte size, not the vector count
    formatted as bytes (``get_size()`` returns ``ntotal`` today → "100 B" for 100
    vectors)."""
    ws = local_workspace
    corpus = ws.root / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text(
        "Semantic search finds documents by meaning rather than keywords.\n"
    )
    (corpus / "b.txt").write_text(
        "Vector indexing and embeddings power modern document retrieval.\n"
    )
    _create_files_collection("f1", corpus)

    from core.v1.engine.services.inspect_service import InspectService

    info = InspectService(collections_path=str(ws.collections_dir)).inspect(
        ["f1"], include_index_size=True
    )[0]

    assert info.index_size_bytes > info.number_of_chunks, (
        "the index byte size must exceed the vector count "
        f"(got {info.index_size_bytes} bytes for {info.number_of_chunks} chunks)"
    )


@needs_model
@pytest.mark.xfail(strict=True, reason=FIX_F)
def test_bug_f2_created_time_is_populated(local_workspace) -> None:
    """F2: a freshly created collection must report a ``createdTime`` (the
    manifest writer never sets the key → ``created_time`` is always ``None``)."""
    ws = local_workspace
    corpus = ws.root / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text("Notes about deployment pipelines and manifests.\n")
    _create_files_collection("f2", corpus)

    from core.v1.engine.services.inspect_service import InspectService

    info = InspectService(collections_path=str(ws.collections_dir)).inspect(["f2"])[0]

    assert info.created_time is not None, (
        "a freshly created collection must record its creation time"
    )


@needs_model
@pytest.mark.xfail(strict=True, reason=FIX_F)
def test_bug_f3_avg_doc_size_excludes_index(local_workspace) -> None:
    """F3: ``avg_doc_size`` must be computed from document bytes only — today it is
    ``disk_size / n_docs``, which includes the FAISS index, so ``avg * n`` equals
    the whole on-disk size instead of being a strict fraction of it."""
    ws = local_workspace
    corpus = ws.root / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text(
        "Semantic search finds documents by meaning rather than keywords.\n"
    )
    (corpus / "b.txt").write_text(
        "Vector indexing and embeddings power modern document retrieval.\n"
    )
    _create_files_collection("f3", corpus)

    from core.v1.engine.services.inspect_service import InspectService

    info = InspectService(collections_path=str(ws.collections_dir)).inspect(
        ["f3"], include_index_size=True
    )[0]

    assert info.avg_doc_size_bytes is not None and info.disk_size_bytes is not None
    assert info.avg_doc_size_bytes * info.number_of_documents < info.disk_size_bytes, (
        "average document size must exclude the index bytes"
    )


@pytest.mark.xfail(strict=True, reason=FIX_F)
def test_bug_f4_config_set_reports_true_destination(
    tmp_path: Path, monkeypatch
) -> None:
    """F4: in global mode ``config set`` must name the real resolved target path,
    not the hardcoded ``.indexed/config.toml`` literal (which reads as the local
    CWD file while the write actually goes to ``~/.indexed/config.toml``)."""
    home = tmp_path / "home"
    global_config = home / ".indexed" / "config.toml"
    global_config.parent.mkdir(parents=True)
    global_config.touch()
    monkeypatch.setattr(Path, "home", lambda: home)
    work = tmp_path / "work"  # no ./.indexed → global mode
    work.mkdir()
    monkeypatch.chdir(work)

    result = runner.invoke(
        app,
        ["--log-level", "ERROR", "config", "set", "core.v1.indexing.chunk_size", "128"],
    )
    assert result.exit_code == 0, result.stdout
    assert "128" in global_config.read_text(), "value must be written to global config"

    assert str(global_config) in (result.stdout or ""), (
        "the success message must name the real resolved (global) destination"
    )


@pytest.mark.xfail(strict=True, reason=FIX_F)
def test_bug_f5_coerce_value_preserves_string_types() -> None:
    """F5: ``_coerce_value`` must not over-coerce string values — ``"001"`` and
    ``"nan"`` must survive as strings (they become ``1`` and ``float('nan')``
    today, mangling versions/identifiers and writing invalid TOML)."""
    from indexed.config.cli import _coerce_value

    assert _coerce_value("001") == "001"
    assert _coerce_value("nan") == "nan"
