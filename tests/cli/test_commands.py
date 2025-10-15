"""Direct command module tests using Typer's CliRunner.

Covers:
- src/commands/create.py (create_app)
- src/commands/delete.py (register)
- src/commands/legacy.py (legacy_app)
- src/commands/search.py (register)
- src/commands/update.py (register)
"""
from typer.testing import CliRunner
import typer

from commands.create import create_app
from commands.delete import register as register_delete
from commands.legacy import legacy_app
from commands.search import register as register_search
from commands.update import register as register_update
from main.services import CollectionStatus


runner = CliRunner()


def test_create_jira_module(monkeypatch):
    calls = {}

    def fake_create(configs, *, use_cache=True, force=False):
        calls["configs"] = configs
        calls["use_cache"] = use_cache
        calls["force"] = force

    monkeypatch.setattr("cli.app.svc_create", fake_create)

    result = runner.invoke(
        create_app,
        [
            "jira",
            "--collection",
            "my-jira",
            "--url",
            "https://acme.atlassian.net",
            "--jql",
            "project = XYZ",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls["force"] is False
    assert calls["use_cache"] is True
    cfg = calls["configs"][0]
    assert cfg.name == "my-jira"
    assert cfg.type == "jiraCloud"


def test_delete_module_all_yes(monkeypatch):
    cleared = {}

    def fake_status(names, include_index_size=False):  # pylint: disable=unused-argument
        return [
            CollectionStatus("a", 0, 0, "", "", ["i"], None),
            CollectionStatus("b", 0, 0, "", "", ["i"], None),
        ]

    def fake_clear(names):
        cleared["names"] = names

    monkeypatch.setattr("cli.app.svc_status", fake_status)
    monkeypatch.setattr("cli.app.svc_clear", fake_clear)

    app = typer.Typer()
    register_delete(app)

    result = runner.invoke(app, ["--yes"])
    assert result.exit_code == 0, result.output
    assert cleared["names"] == ["a", "b"]


def test_legacy_module_invokes_runpy(monkeypatch):
    captured = {}

    def fake_run_module(module_name, run_name=None):  # pylint: disable=unused-argument
        captured["module_name"] = module_name

    monkeypatch.setattr("runpy.run_module", fake_run_module)

    result = runner.invoke(legacy_app, ["collection-search", "--foo", "bar"])
    assert result.exit_code == 0, result.output
    assert captured["module_name"] == "main.legacy.collection_search_cmd_adapter"


def test_search_module_register(monkeypatch):
    captured = {}

    def fake_search(query, *, configs=None, max_chunks=None, max_docs=None, include_full_text=False, include_all_chunks=False, include_matched_chunks=False):  # pylint: disable=too-many-arguments,unused-argument
        captured["query"] = query
        return {"hits": []}

    monkeypatch.setattr("cli.app.svc_search", fake_search)

    app = typer.Typer()
    register_search(app)

    result = runner.invoke(app, ["hello", "--json"])
    assert result.exit_code == 0, result.output
    assert "\"hits\": []" in result.output
    assert captured["query"] == "hello"


def test_update_module_register(monkeypatch):
    status_calls = {}
    update_calls = {}

    def fake_status(names, include_index_size=False):  # pylint: disable=unused-argument
        status_calls["names"] = names
        return [CollectionStatus("x", 0, 0, "", "", ["i"], None)]

    def fake_update(configs):
        update_calls["configs"] = configs

    monkeypatch.setattr("cli.app.svc_status", fake_status)
    monkeypatch.setattr("cli.app.svc_update", fake_update)

    app = typer.Typer()
    register_update(app)

    result = runner.invoke(app, [])  # update all
    assert result.exit_code == 0, result.output
    assert status_calls["names"] is None
    cfgs = update_calls["configs"]
    assert [c.name for c in cfgs] == ["x"]
