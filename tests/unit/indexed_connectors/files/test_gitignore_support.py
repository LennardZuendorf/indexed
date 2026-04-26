"""Tests for .gitignore support and default directory exclusion in FilesDocumentReader."""

import os
from pathlib import Path

from connectors.files.files_document_reader import FilesDocumentReader


def _rel(paths: list[str], base: Path) -> list[str]:
    """Convert absolute paths to relative paths from base."""
    return [os.path.relpath(p, str(base)) for p in paths]


class TestDefaultDirExclusion:
    def test_git_dir_always_excluded(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main")
        (tmp_path / "README.md").write_text("docs")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        found = list(reader._iter_file_paths())

        assert not any(".git" in p for p in found)
        assert any("README.md" in p for p in found)

    def test_node_modules_excluded(self, tmp_path):
        nm = tmp_path / "node_modules" / "some-pkg"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {}")
        (tmp_path / "app.js").write_text("const x = 1")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        found = _rel(list(reader._iter_file_paths()), tmp_path)

        assert not any(p.startswith("node_modules") for p in found)
        assert "app.js" in found

    def test_venv_excluded(self, tmp_path):
        venv = tmp_path / ".venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "site.py").write_text("# venv")
        (tmp_path / "main.py").write_text("print('hello')")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        found = list(reader._iter_file_paths())

        assert not any(".venv" in p for p in found)
        assert any("main.py" in p for p in found)

    def test_pycache_excluded(self, tmp_path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "module.cpython-311.pyc").write_bytes(b"\x00")
        (tmp_path / "module.py").write_text("x = 1")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        found = list(reader._iter_file_paths())

        assert not any("__pycache__" in p for p in found)
        assert any("module.py" in p for p in found)

    def test_default_excludes_with_respect_gitignore_false(self, tmp_path):
        # Default dir exclusion applies even when respect_gitignore=False
        nm = tmp_path / "node_modules"
        nm.mkdir()
        (nm / "pkg.js").write_text("x")
        (tmp_path / "src.py").write_text("y")

        reader = FilesDocumentReader(
            base_path=str(tmp_path), respect_gitignore=False
        )
        found = list(reader._iter_file_paths())

        assert not any("node_modules" in p for p in found)
        assert any("src.py" in p for p in found)


class TestGitignoreRespect:
    def test_gitignore_excludes_log_files(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\n")
        (tmp_path / "app.log").write_text("log data")
        (tmp_path / "main.py").write_text("code")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        found = list(reader._iter_file_paths())

        assert not any("app.log" in p for p in found)
        assert any("main.py" in p for p in found)

    def test_gitignore_excludes_build_dir(self, tmp_path):
        (tmp_path / ".gitignore").write_text("build/\n")
        build = tmp_path / "build"
        build.mkdir()
        (build / "output.js").write_text("compiled")
        (tmp_path / "src.py").write_text("source")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        found = _rel(list(reader._iter_file_paths()), tmp_path)

        assert not any(p.startswith("build") for p in found)
        assert "src.py" in found

    def test_nested_gitignore_scoped_to_subdir(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\n")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / ".gitignore").write_text("tmp.txt\n")
        (sub / "tmp.txt").write_text("temp")
        (sub / "keep.txt").write_text("keep")
        (tmp_path / "app.log").write_text("log")
        (tmp_path / "main.py").write_text("code")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        found = list(reader._iter_file_paths())

        # top-level .gitignore: *.log excluded
        assert not any("app.log" in p for p in found)
        # sub/.gitignore: tmp.txt excluded inside sub/
        assert not any("tmp.txt" in p for p in found)
        # sub/.gitignore: keep.txt NOT excluded
        assert any("keep.txt" in p for p in found)
        assert any("main.py" in p for p in found)

    def test_nested_gitignore_does_not_affect_sibling(self, tmp_path):
        sub_a = tmp_path / "a"
        sub_b = tmp_path / "b"
        sub_a.mkdir()
        sub_b.mkdir()
        (sub_a / ".gitignore").write_text("secret.txt\n")
        (sub_a / "secret.txt").write_text("secret in a")
        (sub_b / "secret.txt").write_text("not secret in b")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        found = list(reader._iter_file_paths())

        # a/secret.txt excluded by a/.gitignore
        assert not any(str(Path("a") / "secret.txt") in p for p in found)
        # b/secret.txt NOT excluded (different dir scope)
        assert any(str(Path("b") / "secret.txt") in p for p in found)

    def test_gitignore_negation_keeps_file(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\n!keep.log\n")
        (tmp_path / "discard.log").write_text("gone")
        (tmp_path / "keep.log").write_text("kept")

        reader = FilesDocumentReader(base_path=str(tmp_path))
        found = list(reader._iter_file_paths())

        assert not any("discard.log" in p for p in found)
        assert any("keep.log" in p for p in found)

    def test_respect_gitignore_false_ignores_gitignore(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.py\n")
        (tmp_path / "main.py").write_text("code")
        (tmp_path / "readme.txt").write_text("docs")

        reader = FilesDocumentReader(
            base_path=str(tmp_path), respect_gitignore=False
        )
        found = list(reader._iter_file_paths())

        # .gitignore ignored — .py files present
        assert any("main.py" in p for p in found)
        assert any("readme.txt" in p for p in found)

    def test_gitignore_and_user_exclude_both_apply(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\n")
        (tmp_path / "app.log").write_text("log")
        (tmp_path / "skip.txt").write_text("skip")
        (tmp_path / "keep.txt").write_text("keep")

        reader = FilesDocumentReader(
            base_path=str(tmp_path),
            exclude_patterns=[r".*skip.*"],
        )
        found = list(reader._iter_file_paths())

        assert not any("app.log" in p for p in found)
        assert not any("skip.txt" in p for p in found)
        assert any("keep.txt" in p for p in found)

    def test_get_reader_details_includes_flag(self, tmp_path):
        reader = FilesDocumentReader(
            base_path=str(tmp_path), respect_gitignore=False
        )
        details = reader.get_reader_details()
        assert details["respectGitignore"] is False

    def test_get_reader_details_default_true(self, tmp_path):
        reader = FilesDocumentReader(base_path=str(tmp_path))
        assert reader.get_reader_details()["respectGitignore"] is True
