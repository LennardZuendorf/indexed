"""Unit tests for the committed workspace definition ``indexed.toml`` (#344).

No collections are indexed here: these pin the contract of the file — discovery
bounded by ``$HOME``, a versioned parse, resolution against the global store, and
the fail-closed rules that stop a typo from silently widening or emptying the
scope.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from indexed.config.collections_registry import CollectionRegistry
from indexed.config.workspace_selection import (
    SELECTION_FILENAME,
    SelectedCollection,
    WorkspaceSelection,
    WorkspaceSelectionError,
    add_collection,
    find_definition,
    find_git_root,
    load_selection,
    read_definition,
    remove_collection,
    render_definition,
)


@pytest.fixture
def global_root(tmp_path: Path) -> Path:
    return tmp_path / "global"


@pytest.fixture
def store(global_root: Path) -> Path:
    """The global collections root, with two readable collections in it."""
    root = global_root / "data" / "collections"
    for name in ("indexed-docs", "indexed-code"):
        (root / name).mkdir(parents=True)
        (root / name / "manifest.json").write_text(json.dumps({"name": name}))
    return root


@pytest.fixture
def registry(global_root: Path, store: Path) -> CollectionRegistry:
    reg = CollectionRegistry(global_root=global_root)
    for name in ("indexed-docs", "indexed-code"):
        reg.add(name=name, engine="v2", path=name, workspace=str(store))
    return reg


def write_definition(root: Path, body: str) -> Path:
    path = root / SELECTION_FILENAME
    path.write_text(body, encoding="utf-8")
    return path


def record_id(registry: CollectionRegistry, name: str) -> str:
    record = registry.find(name)
    assert record is not None, name
    return record.id


VALID = """\
version = 1

[collections]
use = ["indexed-docs"]
"""


# --- discovery ---------------------------------------------------------------


def test_find_definition_walks_up_from_a_subdirectory(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / ".git").mkdir()
    write_definition(root, VALID)

    assert find_definition(root / "src" / "pkg") == root / SELECTION_FILENAME


def test_find_definition_stops_before_home(tmp_path: Path):
    home = tmp_path / "home"
    (home / "repo" / "src").mkdir(parents=True)
    write_definition(home, VALID)  # a definition in $HOME must not be picked up

    assert find_definition(home / "repo" / "src", home=home) is None


def test_find_definition_absent_is_none(tmp_path: Path):
    (tmp_path / "repo").mkdir()

    assert find_definition(tmp_path / "repo") is None


def test_find_git_root_accepts_a_worktree_git_file(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / ".git").write_text("gitdir: /elsewhere/.git/worktrees/repo\n")

    assert find_git_root(root / "src") == root


# --- parsing -----------------------------------------------------------------


def test_read_definition_returns_entries_in_order(tmp_path: Path):
    path = write_definition(
        tmp_path,
        'version = 1\n\n[collections]\nuse = ["indexed-code", "indexed-docs"]\n',
    )

    assert read_definition(path) == ("indexed-code", "indexed-docs")


@pytest.mark.parametrize(
    ("body", "fragment"),
    [
        ('[collections]\nuse = ["indexed-docs"]\n', "version"),
        ('version = 2\n\n[collections]\nuse = ["indexed-docs"]\n', "version 2"),
        ("version = 1\n", "collections].use"),
        ("version = 1\n\n[collections]\nuse = []\n", "collections].use"),
        ('version = 1\n\n[collections]\nuse = "indexed-docs"\n', "collections].use"),
        ('version = 1\n\n[collections]\nuse = [""]\n', "collections].use"),
        ("version = = 1\n", "TOML"),
    ],
)
def test_read_definition_is_loud(tmp_path: Path, body: str, fragment: str):
    path = write_definition(tmp_path, body)

    with pytest.raises(WorkspaceSelectionError) as excinfo:
        read_definition(path)

    message = str(excinfo.value)
    assert str(path) in message
    assert fragment in message


# --- resolution --------------------------------------------------------------


def test_load_selection_resolves_names_against_the_store(
    tmp_path: Path, registry: CollectionRegistry, store: Path
):
    write_definition(tmp_path, VALID)

    selection = load_selection(
        tmp_path, registry=registry, collections_path=store, home=tmp_path.parent
    )

    assert isinstance(selection, WorkspaceSelection)
    assert selection.path == tmp_path / SELECTION_FILENAME
    assert selection.names == ("indexed-docs",)
    assert selection.collections == (
        SelectedCollection(name="indexed-docs", id=record_id(registry, "indexed-docs")),
    )


def test_load_selection_resolves_stable_ids(
    tmp_path: Path, registry: CollectionRegistry, store: Path
):
    collection_id = record_id(registry, "indexed-code")
    write_definition(
        tmp_path, f'version = 1\n\n[collections]\nuse = ["{collection_id}"]\n'
    )

    selection = load_selection(
        tmp_path, registry=registry, collections_path=store, home=tmp_path.parent
    )

    assert selection is not None
    assert selection.names == ("indexed-code",)


def test_two_clones_resolve_the_same_selection(
    tmp_path: Path, registry: CollectionRegistry, store: Path
):
    """R1: the definition is portable — a second clone resolves identically."""
    collection_id = record_id(registry, "indexed-docs")
    original = tmp_path / "clone-a"
    (original / ".git").mkdir(parents=True)
    write_definition(
        original, f'version = 1\n\n[collections]\nuse = ["{collection_id}"]\n'
    )

    clone = tmp_path / "clone-b"
    (clone / ".git").mkdir(parents=True)
    shutil.copy(original / SELECTION_FILENAME, clone / SELECTION_FILENAME)

    first = load_selection(
        original, registry=registry, collections_path=store, home=tmp_path.parent
    )
    second = load_selection(
        clone, registry=registry, collections_path=store, home=tmp_path.parent
    )

    assert first is not None and second is not None
    assert first.names == second.names == ("indexed-docs",)
    assert first.collections == second.collections
    # Nothing machine-specific travels with the committed file.
    assert str(tmp_path) not in (clone / SELECTION_FILENAME).read_text(encoding="utf-8")


def test_unknown_name_names_the_file_and_entry(
    tmp_path: Path, registry: CollectionRegistry, store: Path
):
    write_definition(tmp_path, 'version = 1\n\n[collections]\nuse = ["nope"]\n')

    with pytest.raises(WorkspaceSelectionError) as excinfo:
        load_selection(
            tmp_path, registry=registry, collections_path=store, home=tmp_path.parent
        )

    message = str(excinfo.value)
    assert "nope" in message
    assert str(tmp_path / SELECTION_FILENAME) in message
    assert "indexed collection list" in message


def test_unknown_stable_id_is_loud(
    tmp_path: Path, registry: CollectionRegistry, store: Path
):
    unknown = "0" * 32
    write_definition(tmp_path, f'version = 1\n\n[collections]\nuse = ["{unknown}"]\n')

    with pytest.raises(WorkspaceSelectionError) as excinfo:
        load_selection(
            tmp_path, registry=registry, collections_path=store, home=tmp_path.parent
        )

    assert "0" * 32 in str(excinfo.value)


def test_registered_but_missing_data_is_loud(
    tmp_path: Path, registry: CollectionRegistry, store: Path
):
    write_definition(tmp_path, 'version = 1\n\n[collections]\nuse = ["indexed-docs"]\n')
    (store / "indexed-docs" / "manifest.json").unlink()
    (store / "indexed-docs").rmdir()

    with pytest.raises(WorkspaceSelectionError) as excinfo:
        load_selection(
            tmp_path, registry=registry, collections_path=store, home=tmp_path.parent
        )

    assert "indexed-docs" in str(excinfo.value)


def test_duplicate_entry_is_loud(
    tmp_path: Path, registry: CollectionRegistry, store: Path
):
    collection_id = registry.find("indexed-docs").id
    write_definition(
        tmp_path,
        f'version = 1\n\n[collections]\nuse = ["indexed-docs", "{collection_id}"]\n',
    )

    with pytest.raises(WorkspaceSelectionError) as excinfo:
        load_selection(
            tmp_path, registry=registry, collections_path=store, home=tmp_path.parent
        )

    assert "indexed-docs" in str(excinfo.value)


def test_no_definition_returns_none(
    tmp_path: Path, registry: CollectionRegistry, store: Path
):
    (tmp_path / "repo").mkdir()

    assert (
        load_selection(
            tmp_path / "repo", registry=registry, collections_path=store, home=tmp_path
        )
        is None
    )


def test_definition_writes_nothing_into_the_workspace(
    tmp_path: Path, registry: CollectionRegistry, store: Path
):
    repo = tmp_path / "repo"
    repo.mkdir()
    write_definition(repo, VALID)

    load_selection(repo, registry=registry, collections_path=store, home=tmp_path)

    assert sorted(p.name for p in repo.iterdir()) == [SELECTION_FILENAME]


# --- writing (migration + rollback) -----------------------------------------


def test_render_definition_round_trips(tmp_path: Path):
    body = render_definition(["abc"])

    path = write_definition(tmp_path, body)
    assert read_definition(path) == ("abc",)
    assert "indexed.toml" in body


def test_add_collection_creates_then_appends(tmp_path: Path):
    path = add_collection(tmp_path, "aaa")
    assert read_definition(path) == ("aaa",)

    add_collection(tmp_path, "bbb")
    assert read_definition(path) == ("aaa", "bbb")

    add_collection(tmp_path, "bbb")  # idempotent
    assert read_definition(path) == ("aaa", "bbb")


def test_remove_collection_drops_the_entry_then_the_file(tmp_path: Path):
    add_collection(tmp_path, "aaa")
    add_collection(tmp_path, "bbb")

    assert remove_collection(tmp_path, "aaa") is True
    assert read_definition(tmp_path / SELECTION_FILENAME) == ("bbb",)

    assert remove_collection(tmp_path, "bbb") is True
    assert not (tmp_path / SELECTION_FILENAME).exists()
    assert remove_collection(tmp_path, "bbb") is False
