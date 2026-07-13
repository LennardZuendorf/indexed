"""Tests for parsing.plaintext_parser — PlaintextParser."""

import base64
import os
from pathlib import Path

import pytest

import indexed.parsing.plaintext_parser as pp_module
from indexed.parsing._model_window import count_tokens
from indexed.parsing.plaintext_parser import PlaintextParser

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


@pytest.fixture
def parser() -> PlaintextParser:
    return PlaintextParser(max_tokens=512)


class TestPlaintextParser:
    def test_parse_json(self, parser: PlaintextParser):
        doc = parser.parse(FIXTURES / "sample.json")
        assert len(doc.chunks) > 0
        assert doc.metadata["format"] == ".json"

    def test_parse_empty_file(self, parser: PlaintextParser):
        doc = parser.parse(FIXTURES / "empty.txt")
        assert doc.chunks == []

    def test_parse_generic_text(self, parser: PlaintextParser, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("Hello world\n\nSecond paragraph.")
        doc = parser.parse(f)
        assert len(doc.chunks) >= 1
        assert doc.metadata["format"] == ".txt"
        assert doc.chunks[0].source_type == "plaintext"

    def test_long_text_splits(self, parser: PlaintextParser, tmp_path: Path):
        f = tmp_path / "long.txt"
        # Make text that exceeds max_chars (512 * 4 = 2048)
        paragraphs = ["This is a paragraph. " * 50 for _ in range(10)]
        f.write_text("\n\n".join(paragraphs))
        doc = parser.parse(f)
        assert len(doc.chunks) > 1

    def test_contextualized_text_includes_path(
        self, parser: PlaintextParser, tmp_path: Path
    ):
        f = tmp_path / "ctx.txt"
        f.write_text("Content here.")
        doc = parser.parse(f)
        assert str(f) in doc.chunks[0].contextualized_text

    def test_nonexistent_file(self, parser: PlaintextParser):
        doc = parser.parse(Path("/nonexistent/file.txt"))
        assert doc.chunks == []
        assert doc.metadata.get("error") is True

    def test_parse_rst_does_not_invoke_docling(
        self, parser: PlaintextParser, tmp_path: Path, monkeypatch
    ):
        """Regression: .rst must NOT be routed through docling.

        See docs/plans/2026-04-25-001-refactor-cli-logging-pipeline-plan.md U7.
        Docling has no InputFormat for .rst and emits an ERROR per file when
        fed one. The fix routes .rst straight to the generic plaintext path.
        """
        import docling.document_converter as dc_module

        called = {"count": 0}
        original = dc_module.DocumentConverter

        def counting(*args, **kwargs):
            called["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(dc_module, "DocumentConverter", counting)

        f = tmp_path / "README.rst"
        f.write_text(
            "Title\n=====\n\nFirst paragraph.\n\nSecond paragraph with text.\n"
        )

        doc = parser.parse(f)

        # Even via the catch-and-fall-back path, docling must not be reached.
        assert called["count"] == 0, (
            "DocumentConverter was instantiated for a .rst file — the routing "
            "fix in PlaintextParser._parse_markdown is missing or regressed."
        )
        assert len(doc.chunks) >= 1
        assert doc.metadata["format"] == ".rst"
        assert doc.chunks[0].source_type == "plaintext"

    def test_embedded_unsplittable_blob_stays_within_window(
        self, parser: PlaintextParser, tmp_path: Path
    ):
        """An oversized word (base64 blob/URL/hash/JWT) embedded inside an
        otherwise multi-word structured line must still be hard-sliced to fit
        the token window — not appended to ``buf`` unbounded and flushed as
        one oversize chunk. Regression for the finding in ``_bound_to_window``'s
        word-packing loop: the whole-unit char-slice fallback only fired when
        the ENTIRE unit had no spaces, so a single unsplittable run sitting
        inside a multi-word JSON/log line sailed through unbounded.
        """
        blob = base64.b64encode(os.urandom(1600)).decode()
        lines = [
            '{"id": %d, "msg": "log line filler text here", "blob": "%s"}' % (i, blob)
            for i in range(30)
        ]
        f = tmp_path / "structured.json"
        f.write_text("\n".join(lines))

        doc = parser.parse(f)

        assert len(doc.chunks) > 1
        token_counts = [count_tokens(c.text) for c in doc.chunks]
        assert max(token_counts) <= parser._max_tokens, (
            f"every chunk must tokenize to at most {parser._max_tokens} "
            f"tokens; got a chunk of {max(token_counts)} tokens"
        )

    def test_parse_md_still_attempts_docling(
        self, parser: PlaintextParser, tmp_path: Path, monkeypatch
    ):
        """.md should still go to docling first (intentional)."""
        import docling.document_converter as dc_module

        called = {"count": 0}
        original = dc_module.DocumentConverter

        def counting(*args, **kwargs):
            called["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(dc_module, "DocumentConverter", counting)

        f = tmp_path / "doc.md"
        f.write_text("# Heading\n\nMarkdown body.\n")

        parser.parse(f)
        assert called["count"] == 1


class TestPlaintextParserSeparatorTokens:
    """R12.4: `sep.join(buf)`/`" ".join(buf)` packing sums per-piece
    `count_tokens` but never counts the separator's own token cost, so a
    packed group can tokenize over ``self._max_tokens`` once actually
    joined.

    These tests substitute ``count_tokens`` with a plain character-count
    function — still a real, deterministic function of the text, just not
    the ML tokenizer — so the separator's contribution is nonzero and the
    bug is reproducible without depending on a specific tokenizer's
    whitespace handling (the default MiniLM tokenizer collapses "\n\n"/" "
    to zero tokens for plain prose, which would mask the bug entirely).
    """

    def test_paragraph_packing_counts_separator_tokens(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(pp_module, "count_tokens", len)
        parser = pp_module.PlaintextParser(max_tokens=30)
        paragraphs = ["A" * 9 for _ in range(8)]
        f = tmp_path / "dense.txt"
        f.write_text("\n\n".join(paragraphs))

        doc = parser.parse(f)

        assert len(doc.chunks) > 1
        for ch in doc.chunks:
            assert len(ch.text) <= parser._max_tokens, (
                f"chunk of {len(ch.text)} chars exceeds the "
                f"{parser._max_tokens}-token budget once separator tokens "
                "are counted"
            )

    def test_bound_to_window_counts_separator_tokens(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(pp_module, "count_tokens", len)
        parser = pp_module.PlaintextParser(max_tokens=20)
        words = [f"w{str(i) * 4}" for i in range(10)]
        unit = " ".join(words)

        pieces = parser._bound_to_window(unit)

        assert len(pieces) > 1
        for piece in pieces:
            assert len(piece) <= parser._max_tokens, (
                f"piece of {len(piece)} chars exceeds the "
                f"{parser._max_tokens}-token budget once separator tokens "
                "are counted"
            )
