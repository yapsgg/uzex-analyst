"""Clean the registry CSVs, check every data rule, and load them into Postgres.

    uv run --project pipeline python pipeline/build.py --raw .. [--dry-run]

Reads DATABASE_URL (an owner connection; on Supabase use the session pooler or direct connection,
port 5432). Rebuilds only the `market` schema, inside one transaction, so a failed run leaves the
previous data in place. Set AGENT_DB_PASSWORD to create or update the read-only `uzex_agent` role.
"""

import argparse
import csv
import glob
import io
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql

import normalize as n

HERE = Path(__file__).parent
EXPECTED_DEALS = {2022: 84_299, 2023: 93_985, 2024: 106_647, 2025: 115_763, 2026: 99_306}
EXPORT_DATE = pd.Timestamp("2026-10-30")


class DataRuleError(RuntimeError):
    pass


def check(failures: list[str], ok: object, message: str) -> None:
    if not bool(ok):
        failures.append(message)


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def num(column: pd.Series) -> pd.Series:
    return column.map(n.parse_number)


def date(column: pd.Series) -> pd.Series:
    return pd.to_datetime(column.replace("", None), format="%d.%m.%Y", errors="raise")


def strict_map(column: pd.Series, mapping: dict[str, str], label: str) -> pd.Series:
    unknown = set(column.unique()) - set(mapping)
    if unknown:
        raise DataRuleError(f"Unknown {label}: {sorted(unknown)}")
    return column.map(mapping)


def attribute(field: pd.Series, parsed: pd.Series, normalizer) -> pd.Series:
    """The card's field when filled, otherwise what was written inside the product name."""
    return field.map(normalizer).where(field != "", parsed)


def clean(raw: Path) -> dict[str, pd.DataFrame]:
    failures: list[str] = []
    ru_to_uz = {ru: uz for uz, (ru, _) in n.REGIONS.items()}
    regions = pd.DataFrame(
        [(uz, ru, en) for uz, (ru, en) in n.REGIONS.items()],
        columns=["region_uz", "region_ru", "region_en"],
    )

    p = read(raw / "participants.csv")
    companies = pd.DataFrame(
        {
            "inn": p["ИНН"],
            "name": p["Наименование"],
            "search_key": p["Наименование"].map(n.company_search_key),
            "region_uz": p["Регион"],
            "activity": p["Вид деятельности"],
            "role": strict_map(p["Роль"], {"Продавец": "seller", "Покупатель": "buyer"}, "role"),
            "vat_payer": strict_map(p["Плательщик НДС"], {"Да": True, "Нет": False}, "VAT flag"),
        }
    )
    b = read(raw / "brokers.csv")
    brokers = pd.DataFrame(
        {
            "broker_code": b["Код брокера"],
            "name": b["Наименование"],
            "search_key": b["Наименование"].map(n.company_search_key),
            "inn": b["ИНН"],
            "region_uz": b["Регион"],
        }
    )
    f = read(raw / "usd_rates.csv")
    fx = pd.DataFrame({"rate_date": date(f["Дата"]), "uzs_per_usd": num(f["Курс"])})

    c = read(raw / "contracts.csv")
    names = c["Наименование продукта"]
    canonical = [
        n.product_for(hs, name) for hs, name in zip(c["Код ТН ВЭД"], names, strict=True)
    ]
    parsed = pd.DataFrame([n.extract_attributes(name) for name in names], index=c.index)
    contracts = pd.DataFrame(
        {
            "contract_no": c["Номер контракта"].astype(int),
            "product": [item[0] for item in canonical],
            "raw_name": names,
            "grade": attribute(c["Сорт товара"], parsed["grade"], n.normalize_grade),
            "class": attribute(c["Класс товара"], parsed["class"], n.normalize_class),
            "brand": attribute(c["Марка товара"], parsed["brand"], n.normalize_brand),
            "product_type": attribute(c["Тип товара"], parsed["type"], n.normalize_type),
            "size": attribute(c["Размер товара"], parsed["size"], n.normalize_size),
            "hs_code": c["Код ТН ВЭД"],
            "goods_group": c["Группа товара"],
            "unit": c["Единица измерения"],
            "lot_size": num(c["Лот"]).astype(int),
            "currency": strict_map(c["Валюта"], n.CURRENCIES, "currency"),
            "base_price": num(c["Базисная цена"]),
            "deposit_pct": c["Сумма залога"].str.rstrip(" %").astype(int),
            "delivery_basis": c["Базис поставки"],
            "region_uz": strict_map(c["Регион"], ru_to_uz, "contract region"),
            "warehouse_address": c["Адрес склада"],
            "auction_type": strict_map(c["Тип торгов"], n.AUCTIONS, "auction type"),
            "contract_type": strict_map(c["Тип контракта"], n.CONTRACT_TYPES, "contract type"),
            "contract_form": strict_map(c["Форма контракта"], n.FORMS, "contract form"),
            "payment_term_days": num(c["Срок оплаты"]).astype(int),
            "delivery_term_days": num(c["Срок поставки"]).astype(int),
            "packaging": c["Упаковка"],
            "seller_inn": c["ИНН продавца"],
            "registered_on": date(c["Дата регистрации"]),
            "valid_until": date(c["Действует до"]),
        }
    )
    product_rows = {}
    for item, hs, category, industry in zip(
        canonical, c["Код ТН ВЭД"], c["Категория товара"], c["Отрасль промышленности"], strict=True
    ):
        row = (item[0], item[1], item[2], item[3] or item[0], hs, category, industry)
        known = product_rows.setdefault(item[0], row)
        check(failures, known == row, f"Product {item[0]} has inconsistent classification")
    products = pd.DataFrame(
        list(product_rows.values()),
        columns=["product", "product_en", "product_uz", "aliases", "hs_code", "category", "industry"],
    )

    # A name that states an attribute must agree with the field, and no raw spelling may survive.
    for key, column in [("grade", "grade"), ("class", "class"), ("brand", "brand"), ("size", "size")]:
        both = parsed[key].notna() & contracts[column].notna()
        check(
            failures,
            (parsed.loc[both, key] == contracts.loc[both, column]).all(),
            f"{key}: name disagrees with field on {int((parsed.loc[both, key] != contracts.loc[both, column]).sum())} contracts",
        )
    stated_grade = names.str.contains("сорт", case=False)
    check(failures, contracts.loc[stated_grade, "grade"].notna().all(), "A name states a grade we did not parse")
    stated_class = names.str.contains("класс", case=False)
    check(failures, contracts.loc[stated_class, "class"].notna().all(), "A name states a class we did not parse")
    grades = set(contracts["grade"].dropna())
    check(failures, grades <= {"1", "2", "3", "высший"}, f"Unexpected grades: {grades}")

    frames = []
    for path in sorted(glob.glob(str(raw / "deals_*.csv"))):
        frame = read(Path(path))
        year = int(Path(path).stem.split("_")[1])
        check(failures, len(frame) == EXPECTED_DEALS.get(year), f"{path}: {len(frame)} rows")
        check(failures, (date(frame["Дата сделки"]).dt.year == year).all(), f"{path}: wrong year")
        frames.append(frame)
    d = pd.concat(frames, ignore_index=True)
    deals = pd.DataFrame(
        {
            "deal_no": d["Номер сделки"].astype(int),
            "deal_date": date(d["Дата сделки"]),
            "deal_time": d["Время сделки"],
            "contract_no": d["Номер контракта"].astype(int),
            "buyer_inn": d["ИНН покупателя"],
            "seller_broker": d["Брокер продавца"],
            "buyer_broker": d["Брокер покупателя"],
            "quantity_lots": num(d["Количество"]).astype("int64"),
            "amount": num(d["Сумма сделки"]),
            "start_price": num(d["Стартовая цена"]),
            "status": strict_map(d["Состояние сделки"], n.STATUSES, "status"),
            "payment_date": date(d["Дата оплаты"]),
            "delivery_date": date(d["Дата поставки"]),
            "delivered_lots": num(d["Поставлено"]).astype("Int64"),
        }
    )

    # Rules from the README. Any violation stops the load.
    check(failures, deals["deal_no"].is_unique, "Duplicate deal numbers")
    check(failures, contracts["contract_no"].is_unique, "Duplicate contract numbers")
    check(failures, companies["inn"].is_unique, "Duplicate company INNs")
    check(failures, set(companies["region_uz"]) <= set(regions["region_uz"]), "Unknown company region")
    check(failures, set(brokers["region_uz"]) <= set(regions["region_uz"]), "Unknown broker region")
    check(failures, companies["inn"].str.fullmatch(r"\d{9}").all(), "Company INN is not 9 digits")
    check(failures, deals["amount"].gt(0).all(), "Non-positive deal amount")
    check(failures, deals["quantity_lots"].gt(0).all(), "Non-positive quantity")

    m = deals.join(contracts.set_index("contract_no"), on="contract_no")
    check(failures, m["product"].notna().all(), "Deal points at a missing contract")
    pairs = [
        ("Единица измерения", "unit", None),
        ("ИНН продавца", "seller_inn", None),
        ("Форма контракта", "contract_form", n.FORMS),
        ("Тип контракта", "contract_type", n.CONTRACT_TYPES),
        ("Тип торгов", "auction_type", n.AUCTIONS),
        ("Регион", "region_uz", None),
    ]
    for raw_col, col, mapping in pairs:
        left = d[raw_col].map(mapping) if mapping else d[raw_col]
        check(failures, (left.values == m[col].values).all(), f"Deal {raw_col} differs from its contract")
    check(failures, (num(d["Лот"]).values == m["lot_size"].values).all(), "Deal lot differs from contract")
    check(failures, ((m["currency"] == "USD") == (m["contract_type"] == "export")).all(), "Export is not exactly USD")
    check(failures, m["deal_date"].between(m["registered_on"], m["valid_until"]).all(), "Deal outside contract validity")
    check(failures, m["deal_date"].isin(fx["rate_date"]).all(), "Deal date has no FX rate")

    paid = m["status"].isin(["paid", "executed", "partially_executed"])
    delivered = m["status"].isin(["executed", "partially_executed"])
    check(failures, (m["payment_date"].notna() == paid).all(), "Payment date disagrees with status")
    check(failures, (m["delivery_date"].notna() == delivered).all(), "Delivery date disagrees with status")
    check(failures, (m["delivered_lots"].notna() == delivered).all(), "Delivered lots disagree with status")
    executed = m["status"] == "executed"
    check(failures, (m.loc[executed, "delivered_lots"] == m.loc[executed, "quantity_lots"]).all(), "Executed deal not fully delivered")
    partial = m["status"] == "partially_executed"
    check(failures, (m.loc[partial, "delivered_lots"] < m.loc[partial, "quantity_lots"]).all(), "Partial deal fully delivered")
    check(failures, ((m["status"] == "new") == (m["deal_date"] == EXPORT_DATE)).all(), "'new' is not exactly the export day")
    check(failures, (m["payment_date"].dropna() >= m.loc[paid, "deal_date"]).all(), "Payment before deal")
    check(failures, (m["delivery_date"].dropna() >= m.loc[delivered, "payment_date"]).all(), "Delivery before payment")
    check(failures, m[["payment_date", "delivery_date"]].max().max() <= EXPORT_DATE, "Dates after export day")

    ratio = m["amount"] / (m["quantity_lots"] * m["lot_size"]) / m["start_price"]
    check(failures, ratio.between(0.5, 2).all(), "Unit price is more than twice away from the start price")
    english = m["auction_type"] == "english"
    check(failures, ratio[english].round(6).ge(1).all(), "English auction closed below start price")
    reverse = m["auction_type"] == "reverse"
    check(failures, ratio[reverse].round(6).le(1).all(), "Reverse auction closed above start price")

    if failures:
        raise DataRuleError("Data rules failed:\n- " + "\n- ".join(failures))

    return {
        "regions": regions,
        "products": products,
        "companies": companies,
        "brokers": brokers,
        "contracts": contracts,
        "fx_rates": fx,
        "deals": deals,
    }


def copy_frame(cursor: psycopg.Cursor, table: str, frame: pd.DataFrame) -> None:
    buffer = io.StringIO()
    frame.to_csv(buffer, index=False, header=False, na_rep="", quoting=csv.QUOTE_MINIMAL)
    buffer.seek(0)
    columns = sql.SQL(", ").join(sql.Identifier(name) for name in frame.columns)
    statement = sql.SQL("COPY market.{} ({}) FROM STDIN WITH (FORMAT csv)").format(
        sql.Identifier(table), columns
    )
    with cursor.copy(statement) as copy:
        while chunk := buffer.read(1 << 20):
            copy.write(chunk)


def create_valid_deals_view(cursor: psycopg.Cursor) -> None:
    """v_deals drops is_valid, so a query that tries to reason about cancelled deals there fails
    loudly instead of quietly returning zero."""
    cursor.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'market' AND table_name = 'v_all_deals' AND column_name <> 'is_valid'
        ORDER BY ordinal_position
        """
    )
    columns = sql.SQL(", ").join(sql.Identifier(row[0]) for row in cursor.fetchall())
    cursor.execute(
        sql.SQL("CREATE VIEW market.v_deals AS SELECT {} FROM market.v_all_deals WHERE is_valid").format(
            columns
        )
    )


def grant_agent_role(cursor: psycopg.Cursor, password: str) -> None:
    """A login that can read the v_ views and lookup tables and nothing else."""
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'uzex_agent'")
    verb = "ALTER" if cursor.fetchone() else "CREATE"
    cursor.execute(
        sql.SQL(verb + " ROLE uzex_agent LOGIN PASSWORD {}").format(sql.Literal(password))
    )
    cursor.execute("ALTER ROLE uzex_agent SET default_transaction_read_only = on")
    cursor.execute("ALTER ROLE uzex_agent SET statement_timeout = '20s'")
    cursor.execute("GRANT USAGE ON SCHEMA market TO uzex_agent")
    for view in ("v_deals", "v_all_deals", "v_contracts", "v_companies", "v_brokers", "v_products", "v_fx_rates", "v_regions"):
        cursor.execute(sql.SQL("GRANT SELECT ON market.{} TO uzex_agent").format(sql.Identifier(view)))
    # Name and product search also needs the hidden search keys and aliases.
    cursor.execute("GRANT SELECT ON market.companies, market.brokers, market.products TO uzex_agent")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", default="..", type=Path, help="Folder with the CSV files")
    parser.add_argument("--dry-run", action="store_true", help="Clean and check, load nothing")
    args = parser.parse_args()

    tables = clean(args.raw)
    for name, frame in tables.items():
        print(f"{name:10} {len(frame):>8,} rows")
    print("All data rules passed.")
    if args.dry_run:
        return 0

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    with psycopg.connect(url, prepare_threshold=None) as connection, connection.cursor() as cursor:
        # Under a C locale, ILIKE can't fold Cyrillic, and text filters would silently match nothing.
        cursor.execute("SELECT 'Масло' ILIKE 'масло'")
        if not cursor.fetchone()[0]:
            raise DataRuleError("This database's locale can't case-fold Cyrillic; use en_US.UTF-8.")
        cursor.execute((HERE / "schema.sql").read_text())
        create_valid_deals_view(cursor)
        for name, frame in tables.items():
            copy_frame(cursor, name, frame)
            print(f"loaded {name}")
        cursor.execute("ANALYZE market.deals")
        cursor.execute("ANALYZE market.contracts")
        if password := os.environ.get("AGENT_DB_PASSWORD"):
            grant_agent_role(cursor, password)
            print("granted uzex_agent")
        cursor.execute("SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid))) FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace WHERE s.nspname = 'market' AND c.relkind = 'r'")
        print("market schema size:", cursor.fetchone()[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
