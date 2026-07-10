"""Unit tests for the shared incremental-query builder (connectors/_incremental).

Pins the cutoff math and the ``incremental_query`` join logic in isolation:
the empty-base guard (R6.5), the no-ORDER-BY join, and the ORDER-BY splice that
keeps the generated JQL/CQL valid (a boolean clause cannot follow ``ORDER BY``).
Covers both ``updated_field`` values — ``updated`` (Jira) and ``lastModified``
(Confluence) — asserting the exact resulting strings.
"""

import pytest

from indexed.connectors._incremental import cutoff_date, incremental_query

_CUTOFF = "2026-07-04"
_JIRA_FILTER = f'(created >= "{_CUTOFF}" OR updated >= "{_CUTOFF}")'
_CONF_FILTER = f'(created >= "{_CUTOFF}" OR lastModified >= "{_CUTOFF}")'


# --- cutoff_date ---------------------------------------------------------------


def test_cutoff_date_subtracts_one_day_from_datetime() -> None:
    assert cutoff_date("2026-07-05T09:15:00+00:00") == "2026-07-04"


def test_cutoff_date_subtracts_one_day_from_date_only() -> None:
    assert cutoff_date("2026-07-05") == "2026-07-04"


# --- incremental_query: empty base (R6.5) --------------------------------------


@pytest.mark.parametrize("base", ["", "   ", None])
def test_incremental_query_empty_base_returns_bare_filter(base) -> None:
    result = incremental_query(base, _CUTOFF, updated_field="updated")
    assert result == _JIRA_FILTER
    assert not result.lstrip().startswith("AND")


# --- incremental_query: no ORDER BY --------------------------------------------


def test_incremental_query_no_order_by_jira() -> None:
    assert (
        incremental_query("project = FOO", _CUTOFF, updated_field="updated")
        == f"project = FOO AND {_JIRA_FILTER}"
    )


def test_incremental_query_no_order_by_confluence() -> None:
    assert (
        incremental_query("space = DOCS", _CUTOFF, updated_field="lastModified")
        == f"space = DOCS AND {_CONF_FILTER}"
    )


# --- incremental_query: WHERE + ORDER BY ---------------------------------------


def test_incremental_query_where_and_order_by_jira() -> None:
    assert (
        incremental_query(
            "project = FOO ORDER BY updated", _CUTOFF, updated_field="updated"
        )
        == f"project = FOO AND {_JIRA_FILTER} ORDER BY updated"
    )


def test_incremental_query_where_and_order_by_confluence() -> None:
    assert (
        incremental_query(
            "space = DOCS ORDER BY created", _CUTOFF, updated_field="lastModified"
        )
        == f"space = DOCS AND {_CONF_FILTER} ORDER BY created"
    )


# --- incremental_query: ORDER BY only (no WHERE) -------------------------------


def test_incremental_query_order_by_only_jira() -> None:
    assert (
        incremental_query("ORDER BY updated", _CUTOFF, updated_field="updated")
        == f"{_JIRA_FILTER} ORDER BY updated"
    )


def test_incremental_query_order_by_only_confluence() -> None:
    assert (
        incremental_query("ORDER BY created", _CUTOFF, updated_field="lastModified")
        == f"{_CONF_FILTER} ORDER BY created"
    )


def test_incremental_query_order_by_case_insensitive_preserves_original() -> None:
    """Match is case-insensitive but the stored sort clause is re-appended verbatim."""
    assert (
        incremental_query(
            "project = FOO order by updated DESC", _CUTOFF, updated_field="updated"
        )
        == f"project = FOO AND {_JIRA_FILTER} order by updated DESC"
    )
