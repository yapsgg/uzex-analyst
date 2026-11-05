import pytest

from core.sql_guard import (
    UnsafeQueryError,
    cancelled_deals_warning,
    partial_year_warning,
    valid_view_error,
    validate,
)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT sum(amount_uzs) FROM v_deals WHERE is_valid AND deal_year = 2026",
        "SELECT * FROM market.v_products",
        "WITH t AS (SELECT product, sum(volume) v FROM v_deals GROUP BY 1) SELECT * FROM t",
        "SELECT name FROM v_companies WHERE name ILIKE '%trade%'",
        "SELECT g FROM generate_series(1, 3) AS g",
        "SELECT 1 FROM v_deals UNION ALL SELECT 2 FROM v_brokers",
    ],
)
def test_allows_reads_over_views(query):
    validate(query)


@pytest.mark.parametrize(
    "query",
    [
        "DROP TABLE market.deals",
        "DELETE FROM v_deals",
        "UPDATE market.deals SET amount = 0",
        "INSERT INTO market.deals VALUES (1)",
        "SELECT 1; DROP TABLE market.deals",
        "COMMIT; DELETE FROM market.deals",
        "SELECT * FROM market.deals",
        "SELECT * FROM deals",
        "SELECT * FROM pg_catalog.pg_roles",
        "SELECT * FROM auth.users",
        "SELECT * FROM information_schema.tables",
        "SELECT pg_sleep(100)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT current_setting('server_version')",
        "SELECT * INTO market.copy FROM v_deals",
        "SELECT * FROM v_deals FOR UPDATE",
        "WITH d AS (DELETE FROM market.deals RETURNING *) SELECT * FROM d",
        "WITH v_deals AS (SELECT 1) SELECT * FROM market.deals",
        "SET ROLE postgres",
        "not sql at all (",
    ],
)
def test_blocks_everything_else(query):
    with pytest.raises(UnsafeQueryError):
        validate(query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT deal_year, sum(amount_uzs) FROM v_all_deals GROUP BY 1",
        "SELECT sum(volume) FROM v_all_deals WHERE deal_year = 2025",
        "SELECT count(*) AS n, count(*) FILTER (WHERE NOT is_valid) AS c FROM v_all_deals",
        "SELECT sum(amount_uzs), count(*) FILTER (WHERE is_valid) FROM v_all_deals",
    ],
)
def test_warns_when_a_total_ignores_cancelled_deals(query):
    assert cancelled_deals_warning(query)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT sum(amount_uzs) FROM v_deals",
        "SELECT sum(amount_uzs) FROM v_all_deals WHERE is_valid",
        "SELECT sum(amount_uzs) FILTER (WHERE status = 'cancelled') FROM v_all_deals",
        "SELECT is_valid, count(*) FROM v_all_deals GROUP BY is_valid",
        "SELECT avg(uzs_per_usd) FROM v_fx_rates",
    ],
)
def test_no_warning_when_cancelled_deals_are_handled_or_irrelevant(query):
    assert cancelled_deals_warning(query) is None


def test_v_deals_cannot_be_asked_about_cancelled_deals():
    assert valid_view_error("SELECT count(*) FROM v_deals WHERE status = 'cancelled'")
    assert valid_view_error("SELECT count(*) FROM v_all_deals WHERE status = 'cancelled'") is None
    assert valid_view_error("SELECT count(*) FROM v_deals") is None


def test_warns_when_partial_2026_meets_a_whole_year():
    assert partial_year_warning(
        "SELECT sum(amount_uzs) FROM v_deals WHERE deal_year IN (2025, 2026)"
    )
    same_dates = (
        "SELECT sum(amount_uzs) FROM v_deals WHERE deal_date BETWEEN '2025-01-01' AND '2025-10-30' "
        "OR deal_date BETWEEN '2026-01-01' AND '2026-10-30'"
    )
    assert partial_year_warning(same_dates) is None
    assert (
        partial_year_warning("SELECT sum(amount_uzs) FROM v_deals WHERE deal_year = 2026") is None
    )
    assert (
        partial_year_warning("SELECT sum(amount_uzs) FROM v_deals WHERE deal_year IN (2024, 2025)")
        is None
    )
