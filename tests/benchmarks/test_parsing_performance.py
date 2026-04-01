"""Performance benchmarks for the parsing pipeline.

Measures throughput and latency of the indexing pipeline:
- Per-format parsing (markdown, code, plaintext, image)
- Batch directory indexing (full connector pipeline)
- Change tracking overhead
- V1 adapter conversion overhead
"""

from __future__ import annotations

from pathlib import Path

import pytest

from connectors.files.change_tracker import ChangeTracker
from connectors.files.connector import FileSystemConnector
from connectors.files.v1_adapter import V1FormatAdapter
from parsing import ParsingModule
from parsing.code_chunker import CodeChunker
from parsing.plaintext_parser import PlaintextParser
from parsing.router import FileRouter

# Root of the indexed project
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "docs"
SPEC_DIR = PROJECT_ROOT / ".spec"
LOGO_PNG = DOCS_DIR / "img" / "logo.png"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def parsing_module() -> ParsingModule:
    return ParsingModule(ocr=False, table_structure=False, max_tokens=512)


@pytest.fixture(scope="module")
def code_chunker() -> CodeChunker:
    return CodeChunker(max_tokens=512)


@pytest.fixture(scope="module")
def plaintext_parser() -> PlaintextParser:
    return PlaintextParser(max_tokens=512)


@pytest.fixture(scope="module")
def file_router() -> FileRouter:
    return FileRouter()


@pytest.fixture(scope="module")
def mixed_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a realistic mixed workspace with ~50 files for batch benchmarks."""
    base = tmp_path_factory.mktemp("bench_workspace")

    # Copy docs/ markdown files
    docs_sub = base / "docs"
    docs_sub.mkdir()
    for md in DOCS_DIR.glob("*.md"):
        (docs_sub / md.name).write_text(md.read_text())

    # Copy .spec/ markdown files
    spec_sub = base / "spec"
    spec_sub.mkdir()
    for md in SPEC_DIR.glob("*.md"):
        (spec_sub / md.name).write_text(md.read_text())

    # Generate Python files
    code_sub = base / "src"
    code_sub.mkdir()
    for i in range(10):
        (code_sub / f"module_{i}.py").write_text(
            f'"""Module {i}."""\n\n'
            f"class Service{i}:\n"
            f"    def process(self, data: str) -> str:\n"
            f"        return data.upper()\n\n"
            f"    def validate(self, value: int) -> bool:\n"
            f"        return value > 0\n\n"
            f"def helper_{i}(x: int) -> int:\n"
            f"    return x * 2\n"
        )

    # Generate JSON config files
    config_sub = base / "config"
    config_sub.mkdir()
    for i in range(5):
        (config_sub / f"config_{i}.json").write_text(
            f'{{"service": "svc-{i}", "port": {8000 + i}, "debug": false}}'
        )

    # Generate plain text files
    for i in range(5):
        (base / f"notes_{i}.txt").write_text(
            f"Meeting notes {i}\n\n"
            + "\n\n".join(f"Item {j}: Discussion about topic {j}." for j in range(20))
        )

    # Copy logo image
    img_sub = base / "images"
    img_sub.mkdir()
    if LOGO_PNG.exists():
        (img_sub / "logo.png").write_bytes(LOGO_PNG.read_bytes())

    return base


# ---------------------------------------------------------------------------
# Per-format parsing benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(min_rounds=3, max_time=2.0)
def test_parse_markdown_docs(benchmark, parsing_module: ParsingModule):
    """Benchmark: parse a real docs/ markdown file."""
    target = DOCS_DIR / "architecture-internals.md"
    assert target.exists()

    def parse_md():
        doc = parsing_module.parse(target)
        assert len(doc.chunks) > 0

    benchmark(parse_md)


@pytest.mark.benchmark(min_rounds=3, max_time=2.0)
def test_parse_large_markdown(benchmark, parsing_module: ParsingModule):
    """Benchmark: parse the largest .spec/ markdown file (~24KB)."""
    target = SPEC_DIR / "tech.md"
    assert target.exists()

    def parse_large_md():
        doc = parsing_module.parse(target)
        assert len(doc.chunks) > 0

    benchmark(parse_large_md)


@pytest.mark.benchmark(min_rounds=3, max_time=2.0)
def test_parse_python_source(benchmark, code_chunker: CodeChunker):
    """Benchmark: AST-chunking a real Python source file."""
    target = (
        PROJECT_ROOT
        / "packages"
        / "indexed-parsing"
        / "src"
        / "parsing"
        / "code_chunker.py"
    )
    assert target.exists()

    def chunk_python():
        chunks = code_chunker.chunk_file(target)
        assert len(chunks) > 0
        assert all(ch.source_type == "code" for ch in chunks)

    benchmark(chunk_python)


@pytest.mark.benchmark(min_rounds=5, max_time=2.0)
def test_parse_json_plaintext(
    benchmark, plaintext_parser: PlaintextParser, tmp_path: Path
):
    """Benchmark: parse a JSON config file as plaintext."""
    f = tmp_path / "bench.json"
    f.write_text('{"key": "value", "items": [1, 2, 3], "nested": {"a": "b"}}')

    def parse_json():
        doc = plaintext_parser.parse(f)
        assert len(doc.chunks) > 0

    benchmark(parse_json)


@pytest.mark.benchmark(min_rounds=3, max_time=5.0)
def test_parse_png_image(benchmark, parsing_module: ParsingModule):
    """Benchmark: parse a PNG image (Docling route, OCR disabled)."""
    if not LOGO_PNG.exists():
        pytest.skip("docs/img/logo.png not found")

    def parse_png():
        doc = parsing_module.parse(LOGO_PNG)
        assert doc.metadata["format"] == ".png"

    benchmark(parse_png)


@pytest.mark.benchmark(min_rounds=5, max_time=2.0)
def test_file_router_throughput(benchmark, file_router: FileRouter):
    """Benchmark: FileRouter routing 10,000 paths."""
    extensions = [".pdf", ".py", ".md", ".json", ".png", ".csv", ".ts", ".xyz"]
    paths = [Path(f"file_{i}{ext}") for i in range(1250) for ext in extensions]

    def route_all():
        for p in paths:
            file_router.route(p)

    benchmark(route_all)


# ---------------------------------------------------------------------------
# Batch indexing benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(min_rounds=3, max_time=10.0)
def test_batch_parse_docs_directory(benchmark, parsing_module: ParsingModule):
    """Benchmark: parse all markdown files in docs/ directory."""
    md_files = list(DOCS_DIR.glob("*.md"))
    assert len(md_files) > 0

    def parse_all_docs():
        total_chunks = 0
        for f in md_files:
            doc = parsing_module.parse(f)
            total_chunks += len(doc.chunks)
        assert total_chunks > 0

    benchmark(parse_all_docs)


@pytest.mark.benchmark(min_rounds=3, max_time=15.0)
def test_full_connector_pipeline_docs(benchmark):
    """Benchmark: full FileSystemConnector pipeline on docs/ directory."""
    assert DOCS_DIR.is_dir()

    def full_pipeline():
        connector = FileSystemConnector(
            path=str(DOCS_DIR),
            include_patterns=[r".*\.md$"],
            ocr_enabled=False,
            table_structure=False,
        )
        docs = list(connector.reader.read_all_documents())
        converted = []
        for doc in docs:
            converted.extend(connector.converter.convert(doc))
        assert len(converted) > 0
        total_chunks = sum(len(d["chunks"]) for d in converted)
        assert total_chunks > 0

    benchmark(full_pipeline)


@pytest.mark.benchmark(min_rounds=3, max_time=20.0)
def test_full_connector_pipeline_mixed(benchmark, mixed_workspace: Path):
    """Benchmark: full pipeline on mixed workspace (~50 files of various types)."""

    def full_mixed():
        connector = FileSystemConnector(
            path=str(mixed_workspace),
            ocr_enabled=False,
            table_structure=False,
        )
        parsed = list(connector.reader.read_all_parsed())
        assert len(parsed) > 20  # should find most files
        total_chunks = sum(len(d.chunks) for d in parsed)
        assert total_chunks > 0

    benchmark(full_mixed)


# ---------------------------------------------------------------------------
# V1 adapter benchmarks
# ---------------------------------------------------------------------------


@pytest.mark.benchmark(min_rounds=5, max_time=2.0)
def test_v1_adapter_conversion(benchmark, parsing_module: ParsingModule):
    """Benchmark: V1FormatAdapter conversion on multiple parsed documents."""
    md_files = list(SPEC_DIR.glob("*.md")) + list(DOCS_DIR.glob("*.md"))
    assert len(md_files) > 0

    # Pre-parse all documents (setup, not measured)
    parsed_docs = [(parsing_module.parse(f), str(f.parent)) for f in md_files]

    def convert_all_v1():
        for parsed, base in parsed_docs:
            reader_out = V1FormatAdapter.reader_output(parsed, base)
            conv_out = V1FormatAdapter.converter_output(parsed, base)
            assert len(reader_out["content"]) > 0
            assert len(conv_out) == 1

    benchmark(convert_all_v1)


# ---------------------------------------------------------------------------
# Change tracking benchmarks
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def large_workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a workspace with 500 files of ~2KB each for change tracking."""
    base = tmp_path_factory.mktemp("large_workspace")
    for i in range(500):
        subdir = base / f"dir_{i // 50}"
        subdir.mkdir(exist_ok=True)
        (subdir / f"file_{i}.txt").write_text(f"Content block {i}\n" * 100)
    return base


@pytest.mark.benchmark(min_rounds=5, max_time=2.0)
def test_change_tracking_content_hash(benchmark, large_workspace: Path):
    """Benchmark: content-hash change detection on 500 files."""
    tracker = ChangeTracker(str(large_workspace), strategy="content_hash")
    file_paths = [str(p) for p in large_workspace.rglob("*") if p.is_file()]

    # Build initial state
    state = tracker.build_state(file_paths)

    def detect_no_changes():
        changes = tracker.detect_changes(file_paths, state)
        assert len(changes) == 0

    benchmark(detect_no_changes)


@pytest.mark.benchmark(min_rounds=5, max_time=2.0)
def test_change_tracking_build_state(benchmark, large_workspace: Path):
    """Benchmark: building state snapshot (hashing 500 files)."""
    tracker = ChangeTracker(str(large_workspace), strategy="content_hash")
    file_paths = [str(p) for p in large_workspace.rglob("*") if p.is_file()]

    def build():
        state = tracker.build_state(file_paths)
        assert state.indexed_file_count > 0

    benchmark(build)
