from unittest.mock import MagicMock, patch

import pytest

from indexed.connectors.github.github_document_converter import GitHubDocumentConverter

pytestmark = pytest.mark.unit


def _document(**overrides) -> dict:
    base = {
        "id": "octo/hello#7",
        "url": "https://github.com/octo/hello/issues/7",
        "modifiedTime": "2026-06-20T10:00:00Z",
        "title": "Flaky retry logic",
        "body": "The retry loop sometimes doubles up.",
        "state": "OPEN",
        "labels": ["bug"],
        "author": "octocat",
        "kind": "issue",
        "comments": [
            {
                "id": "IC_kwDO_1",
                "url": "https://github.com/octo/hello/issues/7#issuecomment-1",
                "author": "reviewer",
                "body": "Can repro.",
            }
        ],
        "project_fields": {},
    }
    base.update(overrides)
    return base


def _fake_parsed_chunk(text: str, metadata: dict | None = None) -> MagicMock:
    chunk = MagicMock()
    chunk.contextualized_text = text
    chunk.metadata = metadata or {}
    return chunk


def test_yields_one_document_with_header_and_body_chunks():
    converter = GitHubDocumentConverter()
    fake_parsed = MagicMock()
    fake_parsed.chunks = [_fake_parsed_chunk("The retry loop sometimes doubles up.")]

    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(parse_bytes=MagicMock(return_value=fake_parsed))
        ),
    ):
        (result,) = list(converter.convert(_document()))

    assert result["id"] == "octo/hello#7"
    assert result["url"] == "https://github.com/octo/hello/issues/7"
    assert result["modifiedTime"] == "2026-06-20T10:00:00Z"
    assert len(result["chunks"]) == 3  # header + body + 1 comment
    assert "Flaky retry logic" in result["chunks"][0]["indexedData"]
    assert result["chunks"][1]["indexedData"] == "The retry loop sometimes doubles up."


def test_comment_chunks_include_author():
    converter = GitHubDocumentConverter()
    fake_parsed = MagicMock()
    fake_parsed.chunks = [_fake_parsed_chunk("body text")]

    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(parse_bytes=MagicMock(return_value=fake_parsed))
        ),
    ):
        (result,) = list(converter.convert(_document()))

    comment_chunk = result["chunks"][-1]
    # The comment's text is chunked like any other body, so the first chunk is
    # bounded by the parser — but the author and the comment's own address stay
    # on its metadata, which is what a citation needs (#340 R1).
    assert comment_chunk["metadata"]["commentAuthor"] == "reviewer"
    assert comment_chunk["metadata"]["commentUrl"].endswith("#issuecomment-1")
    assert "body text" in comment_chunk["indexedData"]


def test_project_fields_attached_to_metadata():
    converter = GitHubDocumentConverter()
    fake_parsed = MagicMock()
    fake_parsed.chunks = [_fake_parsed_chunk("body text")]

    doc = _document(project_fields={"Status": "In Progress"})
    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(parse_bytes=MagicMock(return_value=fake_parsed))
        ),
    ):
        (result,) = list(converter.convert(doc))

    assert result["chunks"][0]["metadata"]["projectFields"] == {"Status": "In Progress"}


def test_parse_failure_falls_back_to_raw_body():
    converter = GitHubDocumentConverter()

    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(
                parse_bytes=MagicMock(side_effect=RuntimeError("boom"))
            )
        ),
    ):
        (result,) = list(converter.convert(_document()))

    assert any("doubles up" in c["indexedData"] for c in result["chunks"])


def test_empty_body_yields_no_body_chunk():
    converter = GitHubDocumentConverter()
    doc = _document(body="", comments=[])
    (result,) = list(converter.convert(doc))
    assert len(result["chunks"]) == 1  # header only


#: One comment long enough that the parser must split it, and long enough that
#: an unbounded fallback would make a single hit larger than any payload budget.
UNBOUNDED_COMMENT = (
    "We rotate the signing key by publishing the new key in JWKS first, then "
    "swapping the signer, then retiring the old public key after one cache TTL. "
) * 300

LONG_COMMENT_ID = "IC_kwDO_long"
LONG_COMMENT_URL = "https://github.com/octo/hello/issues/7#issuecomment-2"


def _long_comment_document() -> dict:
    return _document(
        comments=[
            {
                "id": LONG_COMMENT_ID,
                "url": LONG_COMMENT_URL,
                "author": "reviewer",
                "body": UNBOUNDED_COMMENT,
            }
        ]
    )


def _comment_chunks(chunks: list[dict]) -> list[dict]:
    return [c for c in chunks if c["metadata"].get("commentId") == LONG_COMMENT_ID]


def _assert_bounded_fallback(chunks: list[dict]) -> None:
    """A fallback must still respect the chunk budget (card #340 R5)."""
    comment_chunks = _comment_chunks(chunks)
    assert len(comment_chunks) > 1, "one long comment is never one hit"
    assert max(len(c["indexedData"]) for c in comment_chunks) < 3000
    # Splitting only drops boundary newlines; no comment text disappears.
    assert sum(len(c["indexedData"]) for c in comment_chunks) >= len(UNBOUNDED_COMMENT)


def _run_with_parser(parser) -> dict:
    converter = GitHubDocumentConverter()
    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(lambda self: parser),
    ):
        (result,) = list(converter.convert(_long_comment_document()))
    return result


def test_comment_parse_exception_fallback_is_bounded() -> None:
    """A parser that raises must not turn the comment into one huge hit."""
    result = _run_with_parser(
        MagicMock(parse_bytes=MagicMock(side_effect=RuntimeError("boom")))
    )

    _assert_bounded_fallback(result["chunks"])
    # Every fallback chunk still cites the comment it came from.
    for chunk in _comment_chunks(result["chunks"]):
        assert chunk["metadata"]["commentUrl"] == LONG_COMMENT_URL


def test_comment_empty_result_fallback_is_bounded() -> None:
    """A parser that returns no chunks must not hand back the raw comment."""
    result = _run_with_parser(
        MagicMock(parse_bytes=MagicMock(return_value=MagicMock(chunks=[])))
    )

    _assert_bounded_fallback(result["chunks"])


def test_empty_result_fallback_does_not_drop_the_body() -> None:
    """No parsed chunks is a parser failure, not an empty document."""
    result = _run_with_parser(
        MagicMock(parse_bytes=MagicMock(return_value=MagicMock(chunks=[])))
    )

    body_chunks = [c for c in result["chunks"] if "commentId" not in c["metadata"]]
    # Header plus at least one body chunk; an empty result used to drop the body.
    assert len(body_chunks) > 1
    assert any("doubles up" in c["indexedData"] for c in body_chunks)


def test_bounded_fallback_payload_stays_within_the_schema_budget() -> None:
    """The fallback path is measured like the normal one: payload, not prose."""
    import json

    from indexed.mcp.formatting import build_search_payload

    result = _run_with_parser(
        MagicMock(parse_bytes=MagicMock(side_effect=RuntimeError("boom")))
    )
    chunks = _comment_chunks(result["chunks"])
    payload = build_search_payload(
        {
            "gh-issues": {
                "collectionName": "gh-issues",
                "sourceType": "github",
                "results": [
                    {
                        "id": "octo/hello#7",
                        "url": "https://github.com/octo/hello/issues/7",
                        "matchedChunks": [
                            {
                                "chunkNumber": index,
                                "score": 0.5,
                                "content": {
                                    "indexedData": chunk["indexedData"],
                                    "metadata": chunk["metadata"],
                                },
                            }
                            for index, chunk in enumerate(chunks, start=1)
                        ],
                    }
                ],
            }
        },
        "rotate the signing key",
    )

    assert max(len(hit["text"]) for hit in payload["documents"][0]["hits"]) < 3000
    # The whole payload is the 42 kB comment plus bounded per-hit metadata
    # overhead — the text dominates, so no hit can bloat it.
    assert len(json.dumps(payload)) < 50_000


def test_draft_item_without_url_still_converts():
    converter = GitHubDocumentConverter()
    fake_parsed = MagicMock()
    fake_parsed.chunks = [_fake_parsed_chunk("draft body")]

    doc = _document(
        id="project:PVTI_2", url="", kind="draft", state="DRAFT", comments=[]
    )
    with patch.object(
        GitHubDocumentConverter,
        "_parser",
        new_callable=lambda: property(
            lambda self: MagicMock(parse_bytes=MagicMock(return_value=fake_parsed))
        ),
    ):
        (result,) = list(converter.convert(doc))

    assert result["url"] == ""
    assert result["id"] == "project:PVTI_2"
