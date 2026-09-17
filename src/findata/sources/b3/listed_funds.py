"""B3 listed-funds catalog — official ``fundsListedProxy`` JSON.

The public Angular app at
``https://sistemaswebb3-listados.b3.com.br/fundsListedPage/{type}`` loads
rows from ``fundsListedProxy/Search/GetListFunds/<base64-json>``. Same
family as :mod:`findata.sources.b3.indices` (``indexProxy``): a JSON API
behind a base64 query string, not an HTML scrape.

``typeFund`` is the string published in the app's ``assets/funds.json``
(``ETF``, ``ETF-RF``, ``FII``, ``FI-INFRA``, …), not a numeric ``typeCEM``.
B3 rejects ``pageSize`` above 100 (200 returns an empty page).

Example URL::

    https://sistemaswebb3-listados.b3.com.br/fundsListedProxy/Search/GetListFunds/<base64>

Each row comes back as::

    {
        "id": 16037,
        "typeName": null,
        "acronym": "SPXR",
        "fundName": "IT NOW S&P 500 FUTURES QUANTO BRL FUNDO DE ÍNDICE …",
        "tradingName": "IT NOW SP BR",
    }

The listed share ticker is the 4-letter acronym plus ``11`` (``SPXR11``).
"""

from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel

from findata.http_client import get_json

FUNDS_LISTED_PROXY = "https://sistemaswebb3-listados.b3.com.br/fundsListedProxy/Search/GetListFunds"

# Official ``fundType`` values from fundsListedPage/assets/funds.json, minus
# securitizer issuer pages (CRI/CRA/SEC/OTS) that are not listed funds.
FUND_TYPES: dict[str, str] = {
    "ETF": "ETFs de Renda Variável",
    "ETF-RF": "ETFs de Renda Fixa",
    "ETF-INT-RF": "ETFs de Renda Fixa Internacional",
    "ETF-FII": "ETFs de FII",
    "ETF-CRIPTO": "ETFs de Criptos",
    "ETF-MOEDA": "ETFs de Moedas",
    "FII": "Fundos de Investimento Imobiliário",
    "FI-INFRA": "Fundo Incentivado de Investimento em Infraestrutura",
    "FIAGRO": "Fundo de Investimento em Cadeias Agroindústrias",
    "FIAGRO-FII": "FIAGRO Imobiliário",
    "FIAGRO-FIDC": "FIAGRO Direitos Creditórios",
    "FIAGRO-FIP": "FIAGRO Participações",
    "FIP": "Fundos de Investimento em Participações",
    "FIDC": "Fundos de Investimento em Direitos Creditórios",
    "FIA": "Fundo de Investimentos em Ações",
    "FI-RF": "Fundo de Investimento Renda Fixa",
    "FI-MOEDA": "Fundo de Investimento de Moeda",
    "SETORIAL": "Fundo de Investimento Setoriais",
    "FIM-INFRA": "Fundo de Investimento Multimercado em Infraestrutura",
    "FIM-RF-C-REND": "Fundo de Investimento Multimercado em Renda Fixa",
    "FIM-RF-S-REND": "Fundo de Investimento Multimercado em Renda Fixa",
    "FIM-RV-C-REND": "Fundo de Investimento Multimercado",
    "FIM-RV-S-REND": "Fundo de Investimento Multimercado",
}

# Lookup walks this order so an ETF is not first claimed as FII.
LOOKUP_TYPES: tuple[str, ...] = (
    "ETF",
    "ETF-RF",
    "ETF-INT-RF",
    "ETF-FII",
    "ETF-CRIPTO",
    "ETF-MOEDA",
    "FI-INFRA",
    "FII",
    "FIAGRO",
    "FIAGRO-FII",
    "FIAGRO-FIDC",
    "FIAGRO-FIP",
    "FIP",
    "FIDC",
    "FIA",
    "FI-RF",
    "FI-MOEDA",
    "SETORIAL",
    "FIM-INFRA",
    "FIM-RF-C-REND",
    "FIM-RF-S-REND",
    "FIM-RV-C-REND",
    "FIM-RV-S-REND",
)

_DEFAULT_PAGE_SIZE = 100
_LOOKUP_PAGE_SIZE = 20
_MAX_PAGES = 15
_LISTED_SHARE_SUFFIX = "11"
_STANDARD_ACRONYM_LEN = 4
_CACHE_TTL = 3600


class ListedFund(BaseModel):
    """One fund on the official B3 listed-funds catalog."""

    ticker: str
    acronym: str
    fund_name: str
    trading_name: str
    type_fund: str
    type_name: str | None = None
    b3_id: int | None = None
    description: str | None = None


def acronym_from_ticker(ticker: str) -> str:
    """Strip the trailing digit suffix (``SPXR11`` → ``SPXR``)."""
    folded = ticker.strip().upper()
    stripped = folded.rstrip("0123456789")
    return stripped or folded


def listed_share_ticker(acronym: str) -> str:
    """B3 listed-fund share code: 4-letter acronym plus ``11``."""
    if len(acronym) == _STANDARD_ACRONYM_LEN:
        return f"{acronym}{_LISTED_SHARE_SUFFIX}"
    return acronym


def _canonical_type(type_fund: str) -> str:
    key = type_fund.strip().upper()
    if key not in FUND_TYPES:
        known = ", ".join(sorted(FUND_TYPES))
        raise ValueError(f"unknown B3 listed-fund type {type_fund!r}; expected one of: {known}")
    return key


def _encode_query(
    type_fund: str,
    *,
    page_number: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    keyword: str = "",
) -> str:
    payload = {
        "language": "pt-br",
        "pageNumber": page_number,
        "pageSize": page_size,
        "typeFund": type_fund,
        "keyword": keyword,
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _row_to_fund(row: dict[str, Any], type_fund: str) -> ListedFund | None:
    acronym = (row.get("acronym") or "").strip().upper()
    if not acronym:
        return None
    return ListedFund(
        ticker=listed_share_ticker(acronym),
        acronym=acronym,
        fund_name=(row.get("fundName") or "").strip(),
        trading_name=(row.get("tradingName") or "").strip(),
        type_fund=type_fund,
        type_name=(row.get("typeName") or None),
        b3_id=_as_int(row.get("id")),
        description=FUND_TYPES[type_fund],
    )


async def _fetch_page(
    type_fund: str,
    *,
    page_number: int,
    page_size: int,
    keyword: str,
) -> dict[str, Any]:
    encoded = _encode_query(
        type_fund, page_number=page_number, page_size=page_size, keyword=keyword
    )
    payload = await get_json(f"{FUNDS_LISTED_PROXY}/{encoded}", cache_ttl=_CACHE_TTL)
    if not isinstance(payload, dict):
        raise ValueError("B3 listed-funds response was not an object")
    return payload


def _results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("results") or []
    return [row for row in rows if isinstance(row, dict)]


async def get_listed_funds(type_fund: str) -> list[ListedFund]:
    """Fetch every fund B3 lists under one official ``typeFund``."""
    kind = _canonical_type(type_fund)
    first = await _fetch_page(kind, page_number=1, page_size=_DEFAULT_PAGE_SIZE, keyword="")
    page_meta = first.get("page") or {}
    total_pages = int(page_meta.get("totalPages") or 1)
    collected = list(_results(first))
    for page in range(2, min(total_pages, _MAX_PAGES) + 1):
        nxt = await _fetch_page(kind, page_number=page, page_size=_DEFAULT_PAGE_SIZE, keyword="")
        collected.extend(_results(nxt))
    return [fund for row in collected if (fund := _row_to_fund(row, kind)) is not None]


async def lookup_listed_fund(ticker: str, type_fund: str | None = None) -> ListedFund | None:
    """Resolve a ticker (``SPXR11`` or ``SPXR``) against the official catalog.

    Uses B3's own keyword filter (one request per type) and requires an exact
    acronym match. Types are tried in :data:`LOOKUP_TYPES` unless ``type_fund``
    is given.
    """
    acronym = acronym_from_ticker(ticker)
    if not acronym:
        return None
    kinds = (_canonical_type(type_fund),) if type_fund else LOOKUP_TYPES
    for kind in kinds:
        payload = await _fetch_page(
            kind, page_number=1, page_size=_LOOKUP_PAGE_SIZE, keyword=acronym
        )
        for row in _results(payload):
            fund = _row_to_fund(row, kind)
            if fund is not None and fund.acronym == acronym:
                return fund
    return None


async def list_fund_types() -> dict[str, str]:
    """Return ``typeFund → official description`` for types this adapter lists."""
    return dict(FUND_TYPES)
