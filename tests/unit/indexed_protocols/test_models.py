"""Tests for shared protocol DTOs."""

from protocols import ProgressUpdate, SourceConfig


def test_progress_update_dataclass() -> None:
    update = ProgressUpdate(stage="indexing", current=2, total=10, message="ok")
    assert update.stage == "indexing"
    assert update.total == 10


def test_source_config_reader_opts_default() -> None:
    cfg = SourceConfig(
        name="c", type="outline", base_url_or_path="https://x.example.com"
    )
    assert cfg.reader_opts == {}
    assert cfg.query is None
