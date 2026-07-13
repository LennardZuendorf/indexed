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


# --- incremental_query: ORDER BY inside a quoted literal -----------------------


def test_incremental_query_order_by_inside_quoted_literal_is_not_a_split_point() -> (
    None
):
    """An ``ORDER BY`` occurring inside a quoted string value is not the sort
    clause boundary — the whole base query is WHERE, with no real trailing sort."""
    base = 'text ~ "please order by date"'
    assert (
        incremental_query(base, _CUTOFF, updated_field="updated")
        == f"{base} AND {_JIRA_FILTER}"
    )


def test_incremental_query_order_by_inside_quotes_then_real_order_by() -> None:
    """A quoted ``order by`` earlier in the query must not be mistaken for the
    trailing sort clause — only the real, unquoted, trailing ORDER BY splits."""
    base = 'text ~ "please order by date" ORDER BY created DESC'
    assert (
        incremental_query(base, _CUTOFF, updated_field="updated")
        == f'text ~ "please order by date" AND {_JIRA_FILTER} ORDER BY created DESC'
    )


def test_incremental_query_order_by_inside_single_quoted_literal() -> None:
    """Single-quoted literals are also honored, not just double-quoted ones."""
    base = "text ~ 'please order by date'"
    assert (
        incremental_query(base, _CUTOFF, updated_field="lastModified")
        == f"{base} AND {_CONF_FILTER}"
    )


# --- incremental_query: ambiguous/odd quoting must degrade safely --------------


def test_incremental_query_unpaired_apostrophes_do_not_swallow_order_by() -> None:
    """An unpaired apostrophe (e.g. an English contraction like "don't") must
    never cause a real trailing ORDER BY to be mis-paired away as "inside a
    quoted span". Naively pairing ANY two same-char quotes treats
    `don't ... reallyz's` as one quoted span covering the real ORDER BY,
    which would splice the filter AFTER ORDER BY (invalid JQL/CQL). The
    filter must always land in the WHERE portion, before ORDER BY."""
    base = "text ~ don't ORDER BY reallyz's stuff"
    result = incremental_query(base, _CUTOFF, updated_field="updated")

    order_by_pos = result.upper().index("ORDER BY")
    filter_pos = result.index(_JIRA_FILTER)
    assert filter_pos < order_by_pos, (
        f"filter must be injected before ORDER BY, got: {result!r}"
    )
    assert result == f"text ~ don't AND {_JIRA_FILTER} ORDER BY reallyz's stuff"


def test_incremental_query_unmatched_trailing_quote_treats_tail_as_unquoted() -> None:
    """An opening quote with no matching close (odd/unmatched quoting) must
    not swallow a later real trailing ORDER BY into an unterminated span —
    the tail after the dangling quote is treated as unquoted, so the real
    trailing ORDER BY is still found and the filter lands before it."""
    base = 'text ~ "unterminated ORDER BY x'
    result = incremental_query(base, _CUTOFF, updated_field="updated")

    order_by_pos = result.upper().index("ORDER BY")
    filter_pos = result.index(_JIRA_FILTER)
    assert filter_pos < order_by_pos, (
        f"filter must be injected before ORDER BY, got: {result!r}"
    )
