"""Static checks on model-written SQL. The read-only database role is the second line of defense."""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

ALLOWED_VIEWS = frozenset(
    {
        "v_deals",
        "v_all_deals",
        "v_contracts",
        "v_companies",
        "v_brokers",
        "v_products",
        "v_fx_rates",
        "v_regions",
    }
)
_BLOCKED_FUNCTION_PREFIXES = ("pg_", "dblink", "lo_", "query_to_", "table_to_", "database_to_")
_BLOCKED_FUNCTIONS = frozenset({"current_setting", "set_config", "version", "txid_current"})


class UnsafeQueryError(ValueError):
    """The query is not a single read-only SELECT over the allowed views."""


def validate(query: str) -> None:
    try:
        statements = [s for s in sqlglot.parse(query, dialect="postgres") if s is not None]
    except SqlglotError as error:
        raise UnsafeQueryError(f"Could not parse the SQL: {error}") from error
    if len(statements) != 1:
        raise UnsafeQueryError("Send exactly one statement.")
    root = statements[0]
    if not isinstance(root, exp.Query):
        raise UnsafeQueryError("Only SELECT queries are allowed.")

    blocked = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
               exp.TruncateTable, exp.Command, exp.Into, exp.Lock, exp.Set, exp.Copy)  # fmt: skip
    for node in root.walk():
        if isinstance(node, blocked):
            raise UnsafeQueryError("Only read-only SELECT queries are allowed.")

    cte_names = {cte.alias.lower() for cte in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        name = table.name.lower()
        if not name:
            # Set-returning function in FROM, such as generate_series. Its name is checked below.
            continue
        if name in cte_names and not table.db:
            continue
        if (
            name not in ALLOWED_VIEWS
            or (table.db and table.db.lower() != "market")
            or table.catalog
        ):
            raise UnsafeQueryError(
                f"Table {table.sql(dialect='postgres')} is not available. "
                f"Use only: {', '.join(sorted(ALLOWED_VIEWS))}."
            )

    for function in root.find_all(exp.Func):
        name = (
            function.name.lower()
            if isinstance(function, exp.Anonymous)
            else function.sql_name().lower()
        )
        if name.startswith(_BLOCKED_FUNCTION_PREFIXES) or name in _BLOCKED_FUNCTIONS:
            raise UnsafeQueryError(f"Function {name} is not allowed.")


def _mentions_cancellation(node: exp.Expression) -> bool:
    return any(
        column.name.lower() in {"is_valid", "status"} for column in node.find_all(exp.Column)
    )


def cancelled_deals_warning(query: str) -> str | None:
    """Flags totals over v_all_deals that say nothing about cancelled deals.

    v_deals needs no check: it holds valid deals only.
    """
    root = sqlglot.parse_one(query, dialect="postgres")
    for select in root.find_all(exp.Select):
        sources = {table.name.lower() for table in select.find_all(exp.Table)}
        if "v_all_deals" not in sources:
            continue
        where, group = select.args.get("where"), select.args.get("group")
        if (where and _mentions_cancellation(where)) or (group and _mentions_cancellation(group)):
            continue
        for aggregate in select.find_all(exp.AggFunc):
            parent = aggregate.parent
            if isinstance(parent, exp.Filter) and _mentions_cancellation(parent):
                continue
            return (
                "This total from v_all_deals includes cancelled deals, which did not take place. "
                "It is correct only if the person asked for registered or gross totals. "
                "Otherwise use v_deals."
            )
    return None


def valid_view_error(query: str) -> str | None:
    """v_deals never contains cancelled deals, so asking it about them can only return nothing."""
    root = sqlglot.parse_one(query, dialect="postgres")
    if not any(table.name.lower() == "v_deals" for table in root.find_all(exp.Table)):
        return None
    if any("cancelled" in literal.name.lower() for literal in root.find_all(exp.Literal)):
        return "v_deals excludes cancelled deals. Query v_all_deals for them."
    return None


def partial_year_warning(query: str) -> str | None:
    """2026 ends on October 30, so comparing it with a whole year misleads."""
    root = sqlglot.parse_one(query, dialect="postgres")
    literals = [literal.name for literal in root.find_all(exp.Literal)]
    years = {text[:4] for text in literals if text[:4].isdigit() and text[:2] == "20"}
    if "2026" not in years or len(years) < 2:
        return None
    if any("-10-30" in text or "-10-31" in text for text in literals):
        return None
    return (
        "This compares 2026 with another year, but 2026 data ends on October 30. "
        "Unless asked for full years, rerun with deal_date from January 1 through October 30 "
        "in each year. Don't describe the periods as equal if they aren't."
    )
