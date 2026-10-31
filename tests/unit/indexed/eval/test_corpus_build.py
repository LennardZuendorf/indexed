"""Exercise corpus generation against isolated Git history and local captures."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.integration


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture
def builder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Load the builder against an isolated committed repository and tiny corpus."""
    script = Path(__file__).resolve().parents[4] / "scripts/build_eval_corpus.py"
    spec = importlib.util.spec_from_file_location("eval_corpus_builder", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    git(tmp_path, "init", "-q")
    (tmp_path / "guide.md").write_bytes(b"Pinned guide.\n")
    git(tmp_path, "add", "guide.md")
    git(
        tmp_path,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "fixture",
    )
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "CORPUS_DIR", tmp_path / "eval/corpus")
    monkeypatch.setattr(module, "MANIFEST", tmp_path / "eval/corpus.json")
    monkeypatch.setattr(module, "SOURCES", {"guide.md": "guide.md"})
    monkeypatch.setattr(module, "LOCAL_SNAPSHOTS", {}, raising=False)
    return module


def test_write_pins_committed_bytes_and_check_writes_nothing(builder: ModuleType):
    (builder.REPO_ROOT / "guide.md").write_bytes(b"Uncommitted edits.\n")
    assert builder.main([]) == 0
    pinned = builder.CORPUS_DIR / "guide.md"
    assert pinned.read_bytes() == b"Pinned guide.\n"
    before = builder.MANIFEST.read_bytes()
    assert builder.main(["--check"]) == 0
    assert builder.MANIFEST.read_bytes() == before
    entry = json.loads(before)["files"][0]
    assert entry["source_kind"] == "git"


@pytest.mark.parametrize("rename", [False, True], ids=["deleted", "renamed"])
def test_check_allows_later_source_movement(builder: ModuleType, capsys, rename: bool):
    """Keep pinned verification valid after source movement without allowing a rebuild."""
    assert builder.main([]) == 0
    if rename:
        git(builder.REPO_ROOT, "mv", "guide.md", "renamed.md")
    else:
        git(builder.REPO_ROOT, "rm", "guide.md")
    git(
        builder.REPO_ROOT,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "move source",
    )
    before = builder.MANIFEST.read_bytes()
    assert builder.main(["--check"]) == 0
    assert "note:" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="cannot read guide.md"):
        builder.main([])
    assert builder.MANIFEST.read_bytes() == before


def test_check_rejects_invalid_revision_before_source_movement(builder: ModuleType):
    assert builder.main([]) == 0
    with pytest.raises(SystemExit, match="invalid git revision"):
        builder.main(["--check", "--rev", "not-a-revision"])


@pytest.mark.parametrize("change", ["bytes", "extra", "directory", "symlink", "tree"])
def test_check_refuses_unverifiable_pinned_content(builder: ModuleType, change: str):
    """Reject byte, filesystem and manifest tampering during read-only verification."""
    assert builder.main([]) == 0
    if change == "bytes":
        (builder.CORPUS_DIR / "guide.md").write_bytes(b"Changed.\n")
    elif change == "extra":
        (builder.CORPUS_DIR / "extra.md").write_bytes(b"Unpinned.\n")
    elif change == "directory":
        (builder.CORPUS_DIR / "nested").mkdir()
    elif change == "symlink":
        (builder.CORPUS_DIR / "guide.md").unlink()
        (builder.CORPUS_DIR / "guide.md").symlink_to(builder.REPO_ROOT / "guide.md")
    else:
        manifest = json.loads(builder.MANIFEST.read_text())
        manifest["tree_sha256"] = "0" * 64
        builder.MANIFEST.write_text(json.dumps(manifest))
    assert builder.main(["--check"]) == 1


def add_snapshot(builder: ModuleType, *, digest: str | None = None) -> None:
    """Add authored capture bytes with complete provenance and an optional bad digest."""
    source = builder.REPO_ROOT / "eval/sources/issue.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"Sanitized uncommitted issue.\n")
    metadata = {
        "upstream_url": "https://github.com/example/project/issues/1",
        "captured_revision": "2026-10-29T10:00:00Z",
        "captured_at": "2026-10-30T10:00:00Z",
        "sanitization_notes": "Removed account names and external links.",
        "input_sha256": digest or hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    (source.parent / "provenance.json").write_text(json.dumps({"issue.md": metadata}))
    setattr(builder, "LOCAL_SNAPSHOTS", {"eval/sources/issue.md": "issue.md"})


def test_write_copies_local_snapshot_bytes_with_separate_provenance(
    builder: ModuleType,
):
    add_snapshot(builder)
    assert builder.main([]) == 0
    assert (
        builder.CORPUS_DIR / "issue.md"
    ).read_bytes() == b"Sanitized uncommitted issue.\n"
    entry = json.loads(builder.MANIFEST.read_text())["files"][1]
    assert entry["source_kind"] == "local_snapshot"
    assert entry["source_path"] == "eval/sources/issue.md"
    assert entry["captured_revision"] == "2026-10-29T10:00:00Z"
    assert entry["upstream_url"] == "https://github.com/example/project/issues/1"
    assert entry["input_sha256"] == entry["sha256"]
    assert builder.main(["--check"]) == 0


def test_write_refuses_snapshot_hash_mismatch_before_writing(builder: ModuleType):
    add_snapshot(builder, digest="0" * 64)
    with pytest.raises(SystemExit, match="input_sha256"):
        builder.main([])
    assert not builder.MANIFEST.exists()
    assert not builder.CORPUS_DIR.exists()


@pytest.mark.parametrize(
    "field", ["upstream_url", "captured_revision", "captured_at", "sanitization_notes"]
)
def test_write_refuses_missing_snapshot_provenance(builder: ModuleType, field: str):
    add_snapshot(builder)
    provenance = builder.REPO_ROOT / "eval/sources/provenance.json"
    metadata = json.loads(provenance.read_text())
    metadata["issue.md"].pop(field)
    provenance.write_text(json.dumps(metadata))
    with pytest.raises(SystemExit, match=field):
        builder.main([])
    assert not builder.MANIFEST.exists()


def test_check_treats_missing_local_source_as_informational(
    builder: ModuleType, capsys
):
    add_snapshot(builder)
    assert builder.main([]) == 0
    (builder.REPO_ROOT / "eval/sources/issue.md").unlink()
    assert builder.main(["--check"]) == 0
    assert "note:" in capsys.readouterr().out


def test_explicit_model_cache_fixture_is_offline(request: pytest.FixtureRequest):
    import os

    cache = request.getfixturevalue("eval_model_cache")
    assert isinstance(cache, Path)
    assert os.environ["HF_HUB_CACHE"] == str(cache)
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
