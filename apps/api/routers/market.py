"""Data tools for the agent. Each endpoint is wrapped by a tool file in `agent/tools/`."""

import difflib
import re
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.config import database_url
from core.sql_guard import (
    UnsafeQueryError,
    cancelled_deals_warning,
    partial_year_warning,
    valid_view_error,
    validate,
)

router = APIRouter(prefix="/tools", tags=["tools"])

MAX_ROWS = 200
TIMEOUT_MS = 15_000


def connect() -> psycopg.Connection:
    # prepare_threshold=None: Supabase's transaction pooler has no prepared statements.
    return psycopg.connect(database_url(), prepare_threshold=None, connect_timeout=10)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime | time):
        return value.isoformat()
    return value


class SqlRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8_000)


class SqlResponse(BaseModel):
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False
    error: str | None = None
    warning: str | None = None
    column_totals: dict[str, float] | None = Field(
        default=None,
        description="Sum of each numeric column across all rows. Absent if rows were cut off.",
    )
    last_minus_first: dict[str, float] | None = Field(
        default=None, description="Last row minus first row per numeric column, for two rows."
    )


# Columns that label a row. Adding these up means nothing.
_LABEL_COLUMN = re.compile(r"(^|_)(year|month|quarter|day|week|no|inn|code|id|rank|rn)$")


def _is_measure(value: Any) -> bool:
    return isinstance(value, int | float | Decimal) and not isinstance(value, bool)


def _derived(
    columns: list[str], rows: list[tuple], truncated: bool
) -> tuple[dict[str, float] | None, dict[str, float] | None]:
    """Totals and differences computed here, so the model has no reason to do the math itself."""
    if truncated or len(rows) < 2:
        return None, None
    measures = [
        index
        for index, name in enumerate(columns)
        if not _LABEL_COLUMN.search(name.lower())
        and all(row[index] is None or _is_measure(row[index]) for row in rows)
        and any(row[index] is not None for row in rows)
    ]
    totals = {
        columns[i]: float(sum(row[i] for row in rows if row[i] is not None)) for i in measures
    }
    differences = None
    if len(rows) == 2:
        differences = {
            columns[i]: float(rows[1][i] - rows[0][i])
            for i in measures
            if rows[0][i] is not None and rows[1][i] is not None
        }
    return totals or None, differences or None


@router.post("/sql", response_model=SqlResponse)
def run_sql(body: SqlRequest) -> SqlResponse:
    """Runs one validated SELECT in a read-only transaction that is always rolled back."""
    try:
        validate(body.query)
    except UnsafeQueryError as error:
        return SqlResponse(error=str(error))
    if problem := valid_view_error(body.query):
        return SqlResponse(error=problem)
    try:
        with connect() as connection, connection.cursor() as cursor:
            connection.read_only = True
            cursor.execute(f"SET LOCAL statement_timeout = {TIMEOUT_MS}")
            cursor.execute("SET LOCAL search_path = market, pg_catalog")
            # A raw string, so `%` in LIKE patterns is not read as a parameter.
            cursor.execute(body.query.encode())
            columns = [column.name for column in cursor.description or []]
            fetched = cursor.fetchmany(MAX_ROWS + 1)
            connection.rollback()
    except psycopg.Error as error:
        return SqlResponse(error=str(error).strip()[:800])
    truncated = len(fetched) > MAX_ROWS
    totals, differences = _derived(columns, fetched, truncated)
    warnings = [cancelled_deals_warning(body.query), partial_year_warning(body.query)]
    return SqlResponse(
        columns=columns,
        rows=[[_json_value(value) for value in row] for row in fetched[:MAX_ROWS]],
        row_count=min(len(fetched), MAX_ROWS),
        truncated=truncated,
        warning=" ".join(text for text in warnings if text) or None,
        column_totals=totals,
        last_minus_first=differences,
    )


class ProductRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class ProductMatch(BaseModel):
    product: str
    product_en: str
    product_uz: str
    category: str
    units: list[str]
    grades: list[str]
    classes: list[str]
    brands: list[str]
    sizes: list[str]
    product_types: list[str]
    currencies: list[str]


class ProductResponse(BaseModel):
    matches: list[ProductMatch]


def _fold(text: str) -> str:
    return re.sub(r"[‘’'`ʻʼ]", "", text.casefold())


def _rank(
    query: str, documents: dict[str, str], names: dict[str, list[str]], limit: int
) -> list[str]:
    """Keys containing every query word, exact names first, then the closest fuzzy matches."""
    words = _fold(query).split()
    folded = " ".join(words)
    exact = [key for key, text in documents.items() if all(word in text for word in words)]
    exact.sort(
        key=lambda key: (
            folded not in names[key],
            not any(name.startswith(folded) for name in names[key]),
            len(documents[key]),
            key,
        )
    )
    if exact:
        return exact[:limit]
    scored = []
    for key, text in documents.items():
        tokens = text.split()
        score = sum(
            max((difflib.SequenceMatcher(None, word, token).ratio() for token in tokens), default=0)
            for word in words
        ) / max(len(words), 1)
        if score >= 0.72:
            scored.append((score, key))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [key for _, key in scored[:limit]]


@router.post("/find-product", response_model=ProductResponse)
def find_product(body: ProductRequest) -> ProductResponse:
    """Finds canonical products from any spelling in Russian, Uzbek, or English."""
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT product, product_en, product_uz, category, aliases FROM market.products"
        )
        rows = {row[0]: row for row in cursor.fetchall()}
        documents = {key: _fold(" ".join(row[:5])) for key, row in rows.items()}
        names = {key: [_fold(name) for name in row[:3]] for key, row in rows.items()}
        matches = []
        for key in _rank(body.query, documents, names, limit=5):
            cursor.execute(
                """
                SELECT array_agg(DISTINCT unit), array_remove(array_agg(DISTINCT grade), NULL),
                       array_remove(array_agg(DISTINCT class), NULL),
                       array_remove(array_agg(DISTINCT brand), NULL),
                       array_remove(array_agg(DISTINCT size), NULL),
                       array_remove(array_agg(DISTINCT product_type), NULL),
                       array_agg(DISTINCT currency)
                FROM market.v_contracts WHERE product = %s
                """,
                (key,),
            )
            units, grades, classes, brands, sizes, types, currencies = cursor.fetchone()
            row = rows[key]
            matches.append(
                ProductMatch(
                    product=row[0], product_en=row[1], product_uz=row[2], category=row[3],
                    units=units, grades=grades, classes=classes, brands=brands, sizes=sizes,
                    product_types=types, currencies=currencies,
                )
            )  # fmt: skip
    return ProductResponse(matches=matches)


_CYRILLIC = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z",
        "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
        "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh",
        "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o", "қ": "q",
        "ғ": "g", "ҳ": "h",
    }
)  # fmt: skip
_LEGAL = re.compile(
    r"\b(mas\W?uliyati cheklangan jamiyati|mchj|xk|ok|aj|qk|mas\W?uliyati|cheklangan|jamiyati)\b"
)


def company_search_key(name: str) -> str:
    """Must match `pipeline/normalize.py`, which writes the stored keys."""
    text = re.sub(r"[‘’'`ʻʼ]", "", name.casefold().translate(_CYRILLIC))
    text = re.sub(r"[^0-9a-z]+", " ", text)
    return re.sub(r"\s+", " ", _LEGAL.sub(" ", text)).strip()


class CompanyRequest(BaseModel):
    query: str = Field(
        min_length=1, max_length=200, description="Name in any script, INN, or BK code."
    )


class CompanyMatch(BaseModel):
    kind: str
    inn: str
    name: str
    region_uz: str
    role: str | None = None
    activity: str | None = None
    broker_code: str | None = None


class CompanyResponse(BaseModel):
    matches: list[CompanyMatch]
    ambiguous: bool


_COMPANY_SQL = "SELECT inn, name, region_uz, role, activity FROM market.companies"
_BROKER_SQL = "SELECT inn, name, region_uz, broker_code FROM market.brokers"


def _company(row: tuple) -> CompanyMatch:
    return CompanyMatch(
        kind="company", inn=row[0], name=row[1], region_uz=row[2], role=row[3], activity=row[4]
    )


def _broker(row: tuple) -> CompanyMatch:
    return CompanyMatch(
        kind="broker", inn=row[0], name=row[1], region_uz=row[2], broker_code=row[3]
    )


@router.post("/find-company", response_model=CompanyResponse)
def find_company(body: CompanyRequest) -> CompanyResponse:
    """Finds companies and brokers. Names are not unique, so INN is the only safe identifier."""
    query = body.query.strip()
    matches: list[CompanyMatch] = []
    with connect() as connection, connection.cursor() as cursor:
        if re.fullmatch(r"\d{9}", query):
            cursor.execute(_COMPANY_SQL + " WHERE inn = %s", (query,))
            matches = [_company(row) for row in cursor.fetchall()]
            cursor.execute(_BROKER_SQL + " WHERE inn = %s", (query,))
            matches += [_broker(row) for row in cursor.fetchall()]
        elif re.fullmatch(r"(?i)bk\d{3}", query):
            cursor.execute(_BROKER_SQL + " WHERE broker_code = %s", (query.upper(),))
            matches = [_broker(row) for row in cursor.fetchall()]
        else:
            key = company_search_key(query)
            words = key.split() or [query.casefold()]
            like = " AND ".join(["search_key LIKE %s"] * len(words))
            params = [f"%{word}%" for word in words]
            cursor.execute(
                f"{_COMPANY_SQL} WHERE {like} ORDER BY length(search_key), inn LIMIT 8", params
            )
            matches = [_company(row) for row in cursor.fetchall()]
            cursor.execute(
                f"{_BROKER_SQL} WHERE {like} ORDER BY length(search_key), inn LIMIT 4", params
            )
            matches += [_broker(row) for row in cursor.fetchall()]
            if not matches:
                cursor.execute("SELECT inn, search_key FROM market.companies")
                keys = dict(cursor.fetchall())
                by_key: dict[str, list[str]] = {}
                for inn, stored in keys.items():
                    by_key.setdefault(stored, []).append(inn)
                close = difflib.get_close_matches(key, by_key, n=5, cutoff=0.7)
                inns = [inn for stored in close for inn in by_key[stored]]
                if inns:
                    cursor.execute(_COMPANY_SQL + " WHERE inn = ANY(%s)", (inns,))
                    matches = [_company(row) for row in cursor.fetchall()]
    return CompanyResponse(matches=matches, ambiguous=len(matches) > 1)
