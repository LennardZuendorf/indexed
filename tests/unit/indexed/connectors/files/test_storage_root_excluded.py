"""A collection never indexes indexed's own storage root.

Regression for the git-aware-search follow-up (issue #279): creating a v2
collection over a repo that already had a populated ``.indexed/`` indexed
``.indexed/.gitignore`` as source content — so a two-file corpus produced three
documents, and ``--changed-since`` reported the storage file as changed (it is
untracked). The fix is two-layered: ``.indexed`` joins
``DEFAULT_EXCLUDED_DIRS`` (name-based, covers nested workspaces) and the reader
prunes the resolved storage roots by absolute path (covers an explicit
``excluded_dirs`` override).
"""

from __future__ import annotations

from pathlib import Path

import indexed.connectors.files.files_document_reader as reader_mod
from indexed.connectors.files.connector import FileSystemConnector
from indexed.connectors.files.files_document_reader import FilesDocumentReader
from indexed.connectors.files.schema import DEFAULT_EXCLUDED_DIRS


def _populate_repo(root: Path) -> Path:
    """Two source files plus a populated local storage root, as ``create`` leaves it."""
    (root / "search_utils.py").write_text("def search(): ...\n")
    (root / "render_utils.py").write_text("def render(): ...\n")
    storage = root / ".indexed"
    (storage / "data" / "collections" / "demo").mkdir(parents=True)
    (storage / ".gitignore").write_text(".env\n")
    (storage / "config.toml").write_text("")
    (storage / "data" / "collections" / "demo" / "index.faiss").write_bytes(b"faiss")
    return storage


def _relative_paths(reader: FilesDocumentReader) -> set[str]:
    base = Path(reader.base_path)
    return {
        Path(path).relative_to(base).as_posix() for path in reader._iter_file_paths()
    }


CORPUS = {"search_utils.py", "render_utils.py"}


class TestStorageRootExcluded:
    def test_local_storage_root_not_indexed(self, tmp_path):
        _populate_repo(tmp_path)
        connector = FileSystemConnector(path=str(tmp_path))

        assert _relative_paths(connector.reader) == CORPUS

    def test_excluded_without_gitignore_and_with_wildcard(self, tmp_path):
        _populate_repo(tmp_path)
        connector = FileSystemConnector(
            path=str(tmp_path),
            include_patterns=["*"],
            respect_gitignore=False,
        )

        assert _relative_paths(connector.reader) == CORPUS

    def test_excluded_even_when_excluded_dirs_overridden(self, tmp_path):
        """The path guard holds when the name list no longer mentions ``.indexed``."""
        _populate_repo(tmp_path)
        reader = FilesDocumentReader(
            base_path=str(tmp_path), excluded_dirs=["node_modules"]
        )

        assert _relative_paths(reader) == CORPUS

    def test_global_storage_root_inside_tree_pruned_by_path(
        self, tmp_path, monkeypatch
    ):
        """Any configured storage root inside the tree is pruned by absolute path."""
        global_root = tmp_path / "custom-global-root"
        (global_root / "data" / "collections").mkdir(parents=True)
        (global_root / "data" / "collections" / "c.json").write_text("{}")
        (tmp_path / "a.txt").write_text("a")
        monkeypatch.setattr(
            reader_mod,
            "default_storage_roots",
            lambda base: frozenset({Path(base) / ".indexed", global_root}),
        )

        reader = FilesDocumentReader(base_path=str(tmp_path))

        assert _relative_paths(reader) == {"a.txt"}

    def test_specific_files_inside_storage_root_skipped(self, tmp_path):
        """Incremental updates pass explicit paths; a stale state cannot re-add one."""
        storage = _populate_repo(tmp_path)
        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            specific_files=[
                str(storage / ".gitignore"),
                str(tmp_path / "search_utils.py"),
            ],
        )

        assert _relative_paths(reader) == {"search_utils.py"}

    def test_nested_dot_indexed_pruned_by_name(self, tmp_path):
        """``.indexed`` is in the default name list, so nested workspaces prune too."""
        nested = tmp_path / "sub" / ".indexed"
        nested.mkdir(parents=True)
        (nested / "notes.md").write_text("notes")
        (tmp_path / "visible.md").write_text("visible")

        reader = FilesDocumentReader(base_path=str(tmp_path))

        assert _relative_paths(reader) == {"visible.md"}

    def test_nested_dot_indexed_reachable_via_explicit_excluded_dirs(self, tmp_path):
        """Documented tradeoff: the *name* rule is overridable, the root guard is not."""
        nested = tmp_path / "sub" / ".indexed"
        nested.mkdir(parents=True)
        (nested / "notes.md").write_text("notes")
        (tmp_path / "visible.md").write_text("visible")

        reader = FilesDocumentReader(
            base_path=str(tmp_path), excluded_dirs=["node_modules"]
        )

        assert _relative_paths(reader) == {"sub/.indexed/notes.md", "visible.md"}


def test_dot_indexed_in_default_excluded_dirs():
    """The name list carries the storage convention, not just the path guard."""
    assert ".indexed" in DEFAULT_EXCLUDED_DIRS


def test_scan_root_inside_storage_root_keeps_working(tmp_path, monkeypatch):
    """Pointing a collection inside a storage root is explicit; the guard yields."""
    storage = tmp_path / ".indexed"
    (storage / "data").mkdir(parents=True)
    (storage / "data" / "notes.md").write_text("notes")
    monkeypatch.setattr(
        reader_mod,
        "default_storage_roots",
        lambda base: frozenset({storage}),
    )

    reader = FilesDocumentReader(base_path=str(storage))

    assert _relative_paths(reader) == {"data/notes.md"}
