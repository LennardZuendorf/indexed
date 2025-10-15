"""CLI command delegation tests.

Ensures Typer CLI forwards to services with correct arguments.
"""

import json
from typer.testing import CliRunner

from indexed.app import app, DEFAULT_INDEXER
from core.v1.engine.services.models import CollectionStatus


runner = CliRunner()


def test_create_jira_calls_service(monkeypatch):
    calls = {}

    def fake_create(configs, *, use_cache=True, force=False):
        calls["configs"] = configs
        calls["use_cache"] = use_cache
        calls["force"] = force

    monkeypatch.setattr("indexed.app.svc_create", fake_create)

    result = runner.invoke(
        app,
        [
            "create",
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
    assert len(calls["configs"]) == 1
    cfg = calls["configs"][0]
    assert cfg.name == "my-jira"
    assert cfg.type == "jiraCloud"
    assert cfg.base_url_or_path == "https://acme.atlassian.net"
    assert cfg.query == "project = XYZ"
    assert cfg.indexer == DEFAULT_INDEXER
    assert cfg.reader_opts == {}


def test_create_confluence_server_calls_service(monkeypatch):
    calls = {}

    def fake_create(configs, *, use_cache=True, force=False):
        calls["configs"] = configs
        calls["use_cache"] = use_cache
        calls["force"] = force

    monkeypatch.setattr("indexed.app.svc_create", fake_create)

    result = runner.invoke(
        app,
        [
            "create",
            "confluence",
            "--collection",
            "wiki",
            "--url",
            "https://confluence.example.com",
            "--cql",
            "space = ENG",
            "--readOnlyFirstLevelComments",
        ],
    )
    assert result.exit_code == 0, result.output
    cfg = calls["configs"][0]
    assert cfg.name == "wiki"
    assert cfg.type == "confluence"
    assert cfg.base_url_or_path == "https://confluence.example.com"
    assert cfg.query == "space = ENG"
    assert cfg.reader_opts.get("readOnlyFirstLevelComments") is True


def test_create_files_calls_service(monkeypatch):
    calls = {}

    def fake_create(configs, *, use_cache=True, force=False):
        calls["configs"] = configs
        calls["use_cache"] = use_cache
        calls["force"] = force

    monkeypatch.setattr("indexed.app.svc_create", fake_create)

    result = runner.invoke(
        app,
        [
            "create",
            "files",
            "local",
            "--basePath",
            "./docs",
            "--includePatterns",
            "*.md",
            "--excludePatterns",
            "*.tmp",
            "--failFast",
            "--index-name",
            "custom_indexer",
            "--force",
            "--no-cache",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls["force"] is True
    assert calls["use_cache"] is False
    cfg = calls["configs"][0]
    assert cfg.type == "localFiles"
    assert cfg.base_url_or_path == "./docs"
    assert cfg.indexer == "custom_indexer"
    assert cfg.reader_opts["includePatterns"] == ["*.md"]
    assert cfg.reader_opts["excludePatterns"] == ["*.tmp"]
    assert cfg.reader_opts["failFast"] is True


def test_update_all_uses_status_and_update(monkeypatch):
    status_calls = {}
    update_calls = {}

    def fake_status(names, include_index_size=False):  # pylint: disable=unused-argument
        status_calls["names"] = names
        return [
            CollectionStatus("a", 0, 0, "", "", [], None),
            CollectionStatus("b", 0, 0, "", "", [], None),
        ]

    def fake_update(configs):
        update_calls["configs"] = configs

    monkeypatch.setattr("indexed.app.svc_status", fake_status)
    monkeypatch.setattr("indexed.app.svc_update", fake_update)

    result = runner.invoke(app, ["update"])
    assert result.exit_code == 0, result.output
    assert status_calls["names"] is None
    cfgs = update_calls["configs"]
    assert [c.name for c in cfgs] == ["a", "b"]


def test_update_one(monkeypatch):
    status_calls = {}
    update_calls = {}

    def fake_status(names, include_index_size=False):  # pylint: disable=unused-argument
        status_calls["names"] = names
        return [CollectionStatus("x", 0, 0, "", "", [], None)]

    def fake_update(configs):
        update_calls["configs"] = configs

    monkeypatch.setattr("indexed.app.svc_status", fake_status)
    monkeypatch.setattr("indexed.app.svc_update", fake_update)

    result = runner.invoke(app, ["update", "--collection", "x"])
    assert result.exit_code == 0, result.output
    cfgs = update_calls["configs"]
    assert len(cfgs) == 1 and cfgs[0].name == "x"


def test_delete_all_yes(monkeypatch):
    cleared = {}

    def fake_status(names, include_index_size=False):  # pylint: disable=unused-argument
        return [
            CollectionStatus("a", 0, 0, "", "", [], None),
            CollectionStatus("b", 0, 0, "", "", [], None),
        ]

    def fake_clear(names):
        cleared["names"] = names

    monkeypatch.setattr("indexed.app.svc_status", fake_status)
    monkeypatch.setattr("indexed.app.svc_clear", fake_clear)

    result = runner.invoke(app, ["delete", "--yes"])
    assert result.exit_code == 0, result.output
    assert cleared["names"] == ["a", "b"]


def test_search_all_json(monkeypatch):
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
        captured["args"] = {
            "query": query,
            "configs": configs,
            "max_chunks": max_chunks,
            "max_docs": max_docs,
            "include_full_text": include_full_text,
            "include_all_chunks": include_all_chunks,
            "include_matched_chunks": include_matched_chunks,
        }
        return {"a": {"hits": []}}

    monkeypatch.setattr("indexed.app.svc_search", fake_search)

    result = runner.invoke(
        app,
        [
            "search",
            "hello",
            "--json",
            "--includeFullText",
            "--maxNumberOfDocuments",
            "5",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["a"]["hits"] == []
    args = captured["args"]
    assert args["query"] == "hello"
    assert args["configs"] is None
    assert args["max_docs"] == 5
    assert args["include_full_text"] is True


def test_search_with_collection(monkeypatch):
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
        captured["configs"] = configs
        return {}

    monkeypatch.setattr("indexed.app.svc_search", fake_search)

    result = runner.invoke(
        app, ["search", "hello", "--collection", "x", "--index-name", "idx"]
    )
    assert result.exit_code == 0, result.output
    cfgs = captured["configs"]
    assert len(cfgs) == 1 and cfgs[0].name == "x" and cfgs[0].indexer == "idx"


def test_inspect_json(monkeypatch):
    def fake_status(names, include_index_size=False):  # pylint: disable=unused-argument
        return [CollectionStatus("a", 1, 2, "t1", "t2", ["i"], 123)]

    monkeypatch.setattr("indexed.app.svc_status", fake_status)

    result = runner.invoke(app, ["inspect", "--json", "--include-index-size"])
    assert result.exit_code == 0, result.output
    out = json.loads(result.stdout)
    assert out[0]["name"] == "a"


def test_list(monkeypatch):
    def fake_status(names, include_index_size=False):  # pylint: disable=unused-argument
        return [
            CollectionStatus(
                "a",
                1,
                2,
                "2025-01-01T00:00:00Z",
                "2025-01-01T00:00:00Z",
                ["i"],
                10,
                "jira",
                "./data/collections/a",
                1234,
            ),
            CollectionStatus(
                "b",
                3,
                4,
                "2025-01-02T00:00:00Z",
                "2025-01-02T00:00:00Z",
                ["i"],
                20,
                "localFiles",
                "./data/collections/b",
                5678,
            ),
        ]

    monkeypatch.setattr("indexed.app.svc_status", fake_status)

    result = runner.invoke(app, ["inspect"])
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line.strip()]

    # Header present - inspect shows "Name" and "Type" in the header
    assert "Name" in lines[1] and "Type" in lines[1]

    # Rows contain names
    body = "\n".join(lines)
    assert "a" in body and "b" in body

    # Check that it found 2 collections (message is at the top)
    assert "Found 2 collections" in result.stdout
