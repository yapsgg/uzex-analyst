"""Runs against a loaded database. Skipped when AGENT_DATABASE_URL is not set."""

import os

import pytest
from fastapi.testclient import TestClient

from main import app
from routers.market import company_search_key

client = TestClient(app)
needs_db = pytest.mark.skipif(not os.environ.get("AGENT_DATABASE_URL"), reason="no database")


def sql(query: str) -> dict:
    return client.post("/tools/sql", json={"query": query}).json()


def test_search_key_matches_the_pipeline():
    assert company_search_key('"ВАБЎК ТРАДЕ" МЧЖ') == "vabok trade"
    assert (
        company_search_key("QOJO‘LIT LOGISTIK MAS’ULIYATI CHEKLANGAN JAMIYATI")
        == "qojolit logistik"
    )


def test_guard_error_goes_back_to_the_model():
    body = sql("DROP TABLE market.deals")
    assert body["error"] and body["rows"] == []


@needs_db
def test_read_query_with_percent_pattern():
    body = sql("SELECT count(*) AS n FROM v_products WHERE product ILIKE '%масло%'")
    assert body["error"] is None and body["rows"] == [[2]]


@needs_db
def test_row_cap():
    body = sql("SELECT deal_no FROM v_deals")
    assert body["truncated"] is True and body["row_count"] == 200


@needs_db
def test_sql_error_is_returned_not_raised():
    assert "does_not_exist" in sql("SELECT does_not_exist FROM v_products")["error"]


@needs_db
@pytest.mark.parametrize(
    ("query", "product"),
    [("хлопковое масло", "Масло хлопковое"), ("urea", "Карбамид"), ("Bug‘doy", "Пшеница"),
     ("мочевина", "Карбамид"), ("diesel", "Дизельное топливо"), ("пшеница", "Пшеница")],
)  # fmt: skip
def test_find_product_across_languages(query, product):
    body = client.post("/tools/find-product", json={"query": query}).json()
    assert body["matches"][0]["product"] == product


@needs_db
def test_find_broker_by_code():
    body = client.post("/tools/find-company", json={"query": "bk001"}).json()
    assert body["matches"][0]["kind"] == "broker" and body["ambiguous"] is False


@needs_db
def test_find_company_across_scripts():
    body = client.post("/tools/find-company", json={"query": "кеКУХО брокер"}).json()
    assert any(match["broker_code"] == "BK001" for match in body["matches"])


@needs_db
def test_v_deals_holds_valid_deals_only():
    valid = sql("SELECT count(*) FROM v_deals")["rows"][0][0]
    total = sql("SELECT count(*) FROM v_all_deals")["rows"][0][0]
    cancelled = sql("SELECT count(*) FROM v_all_deals WHERE NOT is_valid")["rows"][0][0]
    assert total == 500_000 and cancelled > 0 and valid + cancelled == total
    assert "is_valid" in sql("SELECT is_valid FROM v_deals")["error"]


@needs_db
def test_totals_and_differences_come_with_the_result():
    body = sql(
        "SELECT deal_year, sum(amount_uzs) AS t, count(*) AS n FROM v_deals "
        "WHERE deal_year IN (2024, 2025) GROUP BY 1 ORDER BY 1"
    )
    (year_a, t_a, n_a), (year_b, t_b, n_b) = body["rows"]
    assert body["column_totals"]["n"] == n_a + n_b
    assert body["column_totals"]["t"] == pytest.approx(t_a + t_b)
    assert body["last_minus_first"]["t"] == pytest.approx(t_b - t_a)
    assert "deal_year" not in body["column_totals"]


@needs_db
def test_no_totals_for_one_row_or_cut_off_results():
    assert sql("SELECT count(*) AS n FROM v_deals")["column_totals"] is None
    assert sql("SELECT amount_uzs FROM v_deals")["column_totals"] is None
