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
from core.v1.engine.services.models import CollectionStatus
from indexed.knowledge.commands.remove import remove
from indexed.knowledge.commands.search import search
from indexed.knowledge.commands.update import update


runner = CliRunner()


def test_create_jira_module(monkeypatch):
    calls = {}

    def fake_create(configs, *, use_cache=True, force=False):
        calls["configs"] = configs
        calls["use_cache"] = use_cache
        calls["force"] = force

    monkeypatch.setattr("indexed.app.svc_create", fake_create)

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

    monkeypatch.setattr("indexed.app.svc_status", fake_status)
    monkeypatch.setattr("indexed.app.svc_clear", fake_clear)

    app = typer.Typer()
    app.command("remove")(remove)

    result = runner.invoke(app, ["remove", "--yes"])
    assert result.exit_code == 0, result.output
    assert cleared["names"] == ["a", "b"]


def test_search_module_register(monkeypatch):
    captured = {}

    def fake_search(
        query,
        *,
        configs=None,
        max_chunks=None,
        max_docs=None,
        include_full_text=False,
        include_all_chunks=False,
        include_matched_chunks=False,
    ):  # pylint: disable=too-many-arguments,unused-argument
        captured["query"] = query
        return {"hits": []}

    monkeypatch.setattr("indexed.app.svc_search", fake_search)

    app = typer.Typer()
    app.command("search")(search)

    result = runner.invoke(app, ["search", "hello", "--json"])
    assert result.exit_code == 0, result.output
    assert '"hits": []' in result.output
    assert captured["query"] == "hello"


def test_update_module_register(monkeypatch):
    status_calls = {}
    update_calls = {}

    def fake_status(names, include_index_size=False):  # pylint: disable=unused-argument
        status_calls["names"] = names
        return [CollectionStatus("x", 0, 0, "", "", ["i"], None)]

    def fake_update(configs):
        update_calls["configs"] = configs

    monkeypatch.setattr("indexed.app.svc_status", fake_status)
    monkeypatch.setattr("indexed.app.svc_update", fake_update)

    app = typer.Typer()
    app.command("update")(update)

    result = runner.invoke(app, ["update"])  # update all
    assert result.exit_code == 0, result.output
    assert status_calls["names"] is None
    cfgs = update_calls["configs"]
    assert [c.name for c in cfgs] == ["x"]
