"""WorkspaceProfile + WorkspaceScope (workspace-profile/1, R2/R4/R7).

Replaces the deleted ``WorkspaceManager`` storage-mode tests. Covers the
profile reader/writer, the immutable per-invocation scope, the deep-merge
overlay (env still wins), and fail-closed resolution.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from indexed.config.discovery import CANONICAL_NAME, LEGACY_RELPATH
from indexed.config.errors import SchemaVersionError, WorkspaceResolutionError
from indexed.config.workspace import (
    WorkspaceProfile,
    WorkspaceScope,
    clear_scope_cache,
    resolve_scope,
)

PROFILE = """\
[_meta]
schema_version = "2"

[workspace.collections.docs]
name = "Backend Docs"

[workspace.collections.api]
name = "API Spec"
[workspace.collections.api.overrides.core.v1.search]
max_docs = 5

[workspace.overrides.core.v1.search]
max_docs = 3
"""


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A sandbox ``$HOME`` bounding the upward walk inside tmp_path."""
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: h))
    clear_scope_cache()
    yield h
    clear_scope_cache()


@pytest.fixture
def workspace(home: Path) -> Path:
    ws = home / "code" / "app"
    ws.mkdir(parents=True)
    (ws / CANONICAL_NAME).write_text(PROFILE)
    return ws


# ── WorkspaceProfile ────────────────────────────────────────────────────────


def test_profile_reads_collection_filter_and_labels(workspace: Path) -> None:
    """workspace-profile/1 R2: ids are the filter, name is a display label."""
    profile = WorkspaceProfile(workspace / CANONICAL_NAME)

    assert sorted(profile.collection_ids()) == ["api", "docs"]
    assert profile.collection_name("docs") == "Backend Docs"
    assert profile.collection_name("missing") is None


def test_profile_reads_workspace_and_per_collection_overrides(workspace: Path) -> None:
    """workspace-profile/1 R4: two override scopes, read separately."""
    profile = WorkspaceProfile(workspace / CANONICAL_NAME)

    assert profile.overrides() == {"core": {"v1": {"search": {"max_docs": 3}}}}
    assert profile.collection_overrides("api") == {
        "core": {"v1": {"search": {"max_docs": 5}}}
    }
    assert profile.collection_overrides("docs") == {}


def test_add_collection_appends_and_survives_a_reread(workspace: Path) -> None:
    """workspace-profile/1 R2: create appends an entry, atomically."""
    path = workspace / CANONICAL_NAME
    WorkspaceProfile(path).add_collection("notes", "Team Notes")

    reread = WorkspaceProfile(path)
    assert sorted(reread.collection_ids()) == ["api", "docs", "notes"]
    assert reread.collection_name("notes") == "Team Notes"
    # Untouched entries keep their labels and overrides.
    assert reread.collection_name("docs") == "Backend Docs"
    assert reread.overrides() == {"core": {"v1": {"search": {"max_docs": 3}}}}


def test_drop_collection_removes_the_entry_and_reports_whether_it_did(
    workspace: Path,
) -> None:
    """workspace-profile/1 R2: remove drops the entry; absent id is a no-op."""
    path = workspace / CANONICAL_NAME
    profile = WorkspaceProfile(path)

    assert profile.drop_collection("api") is True
    assert profile.drop_collection("api") is False
    assert WorkspaceProfile(path).collection_ids() == ["docs"]


def test_scaffold_writes_a_loadable_skeleton_and_refuses_to_clobber(
    home: Path,
) -> None:
    """workspace-profile/1 R2: scaffold creates the canonical file only once."""
    ws = home / "fresh"
    ws.mkdir()

    path = WorkspaceProfile.scaffold(ws)
    assert path == ws / CANONICAL_NAME
    assert WorkspaceProfile(path).collection_ids() == []

    with pytest.raises(FileExistsError):
        WorkspaceProfile.scaffold(ws)

    WorkspaceProfile(path).add_collection("docs")
    assert WorkspaceProfile.scaffold(ws, force=True) == path
    assert WorkspaceProfile(path).collection_ids() == []


def test_unparseable_profile_raises_naming_the_file(home: Path) -> None:
    """workspace-profile/1 R2: fail closed, never silently unfiltered."""
    ws = home / "broken"
    ws.mkdir()
    path = ws / CANONICAL_NAME
    path.write_text("this is not = = toml\n")

    with pytest.raises(WorkspaceResolutionError) as exc:
        WorkspaceProfile(path).collection_ids()
    assert str(path) in str(exc.value)


def test_profile_carrying_a_removed_storage_key_is_rejected(home: Path) -> None:
    """workspace-profile/1 R7: storage modes are gone — say so by name."""
    ws = home / "old"
    ws.mkdir()
    path = ws / CANONICAL_NAME
    path.write_text('[_meta]\nschema_version = "1"\n\n[workspace]\nmode = "local"\n')

    with pytest.raises(SchemaVersionError) as exc:
        WorkspaceProfile(path).collection_ids()
    assert "[workspace].mode" in str(exc.value)


# ── WorkspaceScope ──────────────────────────────────────────────────────────


def test_resolve_scope_from_a_subdirectory_applies_the_repo_profile(
    workspace: Path,
) -> None:
    """workspace-profile/1 R2: discovery runs from the given workspace dir."""
    sub = workspace / "src" / "api"
    sub.mkdir(parents=True)

    scope = resolve_scope(sub)

    assert scope.profile_path == workspace / CANONICAL_NAME
    assert sorted(scope.collection_ids or []) == ["api", "docs"]
    assert scope.source == "argument"
    assert scope.warnings == []


def test_resolve_scope_without_a_profile_is_unfiltered_and_says_so(
    home: Path,
) -> None:
    """workspace-profile/1 R2: unscoped is stated, not implied."""
    ws = home / "plain"
    ws.mkdir()

    scope = resolve_scope(ws)

    assert scope.collection_ids is None
    assert scope.profile_path is None
    assert scope.source == "none"
    assert scope.overrides == {}


def test_resolve_scope_defaults_to_the_process_cwd(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """workspace-profile/1 R2: no argument → cwd, reported as source cwd."""
    monkeypatch.chdir(workspace)

    scope = resolve_scope(None)

    assert scope.profile_path == workspace / CANONICAL_NAME
    assert scope.source == "cwd"


def test_resolve_scope_reports_the_caller_supplied_source(workspace: Path) -> None:
    """workspace-profile/1 R2: MCP reports which chain step won."""
    assert resolve_scope(workspace, source="roots").source == "roots"


def test_legacy_profile_resolves_with_a_deprecation_notice(home: Path) -> None:
    """workspace-profile/1 R2: legacy works, and names the canonical path."""
    ws = home / "legacy"
    (ws / ".indexed").mkdir(parents=True)
    (ws / LEGACY_RELPATH).write_text('[workspace.collections.docs]\nname = "Docs"\n')

    scope = resolve_scope(ws)

    assert scope.collection_ids == ["docs"]
    assert len(scope.warnings) == 1
    assert CANONICAL_NAME in scope.warnings[0]
    assert str(ws / LEGACY_RELPATH) in scope.warnings[0]


def test_canonical_and_legacy_together_warn_about_the_ignored_file(
    home: Path,
) -> None:
    """workspace-profile/1 R2: canonical wins, the ignored legacy is named."""
    ws = home / "both"
    (ws / ".indexed").mkdir(parents=True)
    (ws / CANONICAL_NAME).write_text('[workspace.collections.docs]\nname = "Docs"\n')
    (ws / LEGACY_RELPATH).write_text('[workspace.collections.old]\nname = "Old"\n')

    scope = resolve_scope(ws)

    assert scope.collection_ids == ["docs"]
    assert len(scope.warnings) == 1
    assert str(ws / LEGACY_RELPATH) in scope.warnings[0]


def test_an_explicit_workspace_that_does_not_exist_fails_closed(home: Path) -> None:
    """workspace-profile/1 R2: never degrade to an unfiltered global view."""
    with pytest.raises(WorkspaceResolutionError) as exc:
        resolve_scope(home / "no" / "such" / "dir")
    assert "no/such/dir" in str(exc.value)


def test_an_explicit_workspace_that_is_a_file_fails_closed(home: Path) -> None:
    """workspace-profile/1 R2: a workspace must be a directory."""
    f = home / "a-file"
    f.write_text("")

    with pytest.raises(WorkspaceResolutionError):
        resolve_scope(f)


def test_scope_is_cached_and_reresolves_when_the_profile_changes(
    workspace: Path,
) -> None:
    """workspace-profile/1 R2: mtime-keyed cache, not a stale snapshot."""
    first = resolve_scope(workspace)
    assert resolve_scope(workspace) is first

    path = workspace / CANONICAL_NAME
    WorkspaceProfile(path).add_collection("notes")

    second = resolve_scope(workspace)
    assert second is not first
    assert sorted(second.collection_ids or []) == ["api", "docs", "notes"]


# ── WorkspaceScope.apply ────────────────────────────────────────────────────


def test_apply_deep_merges_overrides_and_preserves_siblings(workspace: Path) -> None:
    """workspace-profile/1 R4: workspace-wide override wins over the global base."""
    scope = resolve_scope(workspace)
    base = {
        "core": {"v1": {"search": {"max_docs": 10, "max_chunks": 25}}},
        "mcp": {"port": 8000},
    }

    merged = scope.apply(base)

    assert merged["core"]["v1"]["search"]["max_docs"] == 3
    assert merged["core"]["v1"]["search"]["max_chunks"] == 25
    assert merged["mcp"] == {"port": 8000}


def test_apply_is_pure_and_leaves_its_input_untouched(workspace: Path) -> None:
    """workspace-profile/1 R4: no shared mutable state — MCP serves many workspaces."""
    scope = resolve_scope(workspace)
    base = {"core": {"v1": {"search": {"max_docs": 10}}}}

    merged = scope.apply(base)

    assert base == {"core": {"v1": {"search": {"max_docs": 10}}}}
    assert merged is not base
    assert scope.overrides == {"core": {"v1": {"search": {"max_docs": 3}}}}


def test_env_var_still_wins_over_the_profile_override(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """workspace-profile/1 R4: profile sits BELOW INDEXED__* in the cascade."""
    monkeypatch.setenv("INDEXED__core__v1__search__max_docs", "7")
    scope = resolve_scope(workspace)

    merged = scope.apply({"core": {"v1": {"search": {"max_docs": 10}}}})

    assert merged["core"]["v1"]["search"]["max_docs"] == "7"


def test_apply_without_a_profile_is_an_identity_copy(home: Path) -> None:
    """workspace-profile/1 R4: no profile → nothing overridden."""
    ws = home / "plain"
    ws.mkdir()
    base = {"core": {"v1": {"search": {"max_docs": 10}}}}

    assert resolve_scope(ws).apply(base) == base


def test_scope_is_frozen(workspace: Path) -> None:
    """workspace-profile/1 R2: an immutable per-invocation value object."""
    scope = resolve_scope(workspace)

    with pytest.raises(Exception):
        scope.source = "header"  # ty: ignore[invalid-assignment]

    assert isinstance(scope, WorkspaceScope)
