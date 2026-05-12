"""B3 index compositions — IBOV, IBrX-50, IBrX-100, SMLL, IDIV, IFIX…

The B3 ``indexProxy`` JSON endpoint returns the *current* theoretical
portfolio (composição) of any official B3 index: each constituent's
ticker, asset name, share class, theoretical quantity, and weight (%).
Weights are recalibrated quarterly; tickers can join/leave per the
index's rule book.

The endpoint takes a base64-encoded JSON query string. We build it for
the caller — they only pass the index symbol.

Example URL:
``https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay/<base64>``

Each constituent comes back as::

    {
        "cod": "PETR4",
        "asset": "PETROBRAS",
        "type": "PN  ERJ N2",
        "part": "7,537",  # weight, percent (Brazilian decimal)
        "theoricalQty": "4.410.960.450",  # shares × 1
    }

Source: ``https://sistemaswebb3-listados.b3.com.br``
"""

from __future__ import annotations

import base64
import json
from calendar import monthrange
from datetime import date
from typing import Any

from pydantic import BaseModel

from findata.http_client import get_json

INDEX_PROXY = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay"
INDEX_STATISTICS_PROXY = (
    "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetMonthlyEvolution"
)

# Indices known to ship via this endpoint. The list is open — B3 publishes
# many more; we curate the ones investors actually trade against.
KNOWN_INDICES = {
    "IBOV": "Ibovespa",
    "IBXX": "IBrX-100",
    "IBXL": "IBrX-50",
    "SMLL": "Small Cap Index",
    "IDIV": "Índice Dividendos",
    "IFIX": "Índice Fundos Imobiliários",
    "MLCX": "MidLarge Cap",
    "IBRA": "Índice Brasil Amplo",
    "ICON": "Consumo",
    "IFNC": "Financeiro",
    "IMAT": "Materiais Básicos",
    "INDX": "Industrial",
    "UTIL": "Utilidade Pública",
    "IEEX": "Energia Elétrica",
    "IMOB": "Imobiliário",
    "IGNM": "Governança Corporativa Novo Mercado",
    "ITAG": "Tag Along",
    "IGCT": "Governança Trade",
    "ISEE": "Sustentabilidade Empresarial",
    "ICO2": "Carbono Eficiente",
}


def _f_pct(s: str | None) -> float | None:
    """Parse Brazilian-decimal percentage (``"7,537"`` → ``7.537``)."""
    if s is None or not s.strip():
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _i_qty(s: str | None) -> int | None:
    """Parse Brazilian thousand-separated integer (``"4.410.960.450"`` → ``4410960450``)."""
    if s is None or not s.strip():
        return None
    try:
        return int(s.replace(".", ""))
    except ValueError:
        return None


class IndexConstituent(BaseModel):
    """One constituent of a B3 index portfolio."""

    ticker: str
    nome_ativo: str
    classe: str  # e.g. "ON", "PN", "UNT", with optional segment / ED / EJ flags
    peso_pct: float | None  # weight in the index, percent
    qtd_teorica: int | None  # theoretical quantity (shares × 1)
    indice: str  # the index symbol this constituent belongs to


class IndexPortfolio(BaseModel):
    """Snapshot of an index's theoretical portfolio."""

    indice: str
    nome: str
    data: str | None  # the date the portfolio was published (DD/MM/YY from B3)
    qtd_teorica_total: int | None
    redutor: float | None
    componentes: list[IndexConstituent]


class IndexMonthlyPoint(BaseModel):
    """Monthly closing level for a B3 index."""

    date: str  # period-end date, clipped to requested end for partial current month
    period: str  # YYYY-MM
    year: int
    month: int
    close: float
    indice: str
    provider_index: str
    partial_month: bool = False


_DEFAULT_PAGE_SIZE = 200
_MAX_PAGES = 10  # safety cap: largest index has ~250 issues
_MONTHS_IN_YEAR = 12


def _encode_query(index: str, page_size: int = _DEFAULT_PAGE_SIZE, page_number: int = 1) -> str:
    payload = {
        "language": "pt-br",
        "pageNumber": page_number,
        "pageSize": page_size,
        "index": index.upper(),
        "segment": "1",
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _encode_monthly_evolution_query(index: str, start: date, end: date) -> str:
    payload = {
        "language": "pt-br",
        "index": index.upper(),
        "dateInitial": start.isoformat(),
        "dateFinal": end.isoformat(),
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def _coerce_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _month_window_start(end: date, months: int) -> date:
    if months < 1:
        raise ValueError("months must be >= 1")
    month_index = end.year * 12 + (end.month - 1) - (months - 1)
    return date(month_index // 12, month_index % 12 + 1, 1)


def _period_end(year: int, month: int, requested_end: date) -> tuple[date, bool]:
    last = date(year, month, monthrange(year, month)[1])
    partial = year == requested_end.year and month == requested_end.month and requested_end < last
    return (requested_end, True) if partial else (last, False)


def _f_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return float(value.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _row_to_monthly_point(
    row: dict[str, Any], sym: str, requested_end: date
) -> IndexMonthlyPoint | None:
    year = row.get("year")
    month = row.get("month")
    close = _f_number(row.get("indexClosingRate"))
    if not isinstance(year, int) or not isinstance(month, int) or close is None:
        return None
    if month not in range(1, _MONTHS_IN_YEAR + 1):
        return None
    period_end, partial = _period_end(year, month, requested_end)
    return IndexMonthlyPoint(
        date=period_end.isoformat(),
        period=f"{year:04d}-{month:02d}",
        year=year,
        month=month,
        close=close,
        indice=sym,
        provider_index=sym,
        partial_month=partial,
    )


def _f_redutor(s: str | None) -> float | None:
    """Parse B3's redutor (Brazilian decimal with thousand separators)."""
    if s is None or not s.strip():
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _row_to_constituent(row: dict[str, str], sym: str) -> IndexConstituent:
    return IndexConstituent(
        ticker=(row.get("cod") or "").strip(),
        nome_ativo=(row.get("asset") or "").strip(),
        classe=(row.get("type") or "").strip(),
        peso_pct=_f_pct(row.get("part")),
        qtd_teorica=_i_qty(row.get("theoricalQty")),
        indice=sym,
    )


async def get_index_portfolio(index: str) -> IndexPortfolio:
    """Fetch the current theoretical portfolio for a B3 index.

    Args:
        index: 4-character B3 index symbol (e.g. ``"IBOV"``, ``"IBXL"``,
            ``"SMLL"``, ``"IDIV"``, ``"IFIX"``, ``"ITAG"``). Case-insensitive.
            See :data:`KNOWN_INDICES` for a curated list.

    The returned :class:`IndexPortfolio` carries every constituent with
    weight, share class, and theoretical quantity. Pagination is handled
    transparently — broad indices like ITAG (~220) and IBRA (~180) come
    back complete on a single call.
    """
    sym = index.upper()
    first = await get_json(f"{INDEX_PROXY}/{_encode_query(sym, page_number=1)}", cache_ttl=3600)
    page_meta = first.get("page") or {}
    total_pages = int(page_meta.get("totalPages") or 1)
    header = first.get("header") or {}
    results: list[dict[str, str]] = list(first.get("results") or [])

    # B3 caps page sizes server-side; iterate remaining pages if needed.
    for page in range(2, min(total_pages, _MAX_PAGES) + 1):
        nxt = await get_json(
            f"{INDEX_PROXY}/{_encode_query(sym, page_number=page)}",
            cache_ttl=3600,
        )
        results.extend(nxt.get("results") or [])

    components = [_row_to_constituent(r, sym) for r in results]
    return IndexPortfolio(
        indice=sym,
        nome=KNOWN_INDICES.get(sym, sym),
        data=header.get("date"),
        qtd_teorica_total=_i_qty(header.get("theoricalQty")),
        redutor=_f_redutor(header.get("reductor")),
        componentes=components,
    )


async def get_index_monthly_evolution(
    index: str,
    start: date | str | None = None,
    end: date | str | None = None,
    months: int = 120,
) -> list[IndexMonthlyPoint]:
    """Fetch monthly closing levels from B3's IndexStatisticsProxy endpoint.

    Args:
        index: B3 index symbol accepted by the statistics endpoint, for example
            ``"IBOV"``/``"IBOVESPA"``, ``"SMLL"``, ``"IFIX"`` or ``"IBXX"``.
        start: Optional initial date. If omitted, the last ``months`` calendar
            buckets ending at ``end`` are requested.
        end: Optional final date. Defaults to today. If the final month is
            partial, the returned point date is clipped to this value.
        months: Number of monthly buckets to request when ``start`` is omitted.
    """
    sym = index.strip().upper()
    if not sym:
        raise ValueError("index symbol is required")

    end_date = _coerce_date(end) or date.today()
    start_date = _coerce_date(start) or _month_window_start(end_date, months)
    if start_date > end_date:
        raise ValueError("start date must be on or before end date")

    encoded = _encode_monthly_evolution_query(sym, start_date, end_date)
    payload = await get_json(f"{INDEX_STATISTICS_PROXY}/{encoded}", cache_ttl=3600)
    if not isinstance(payload, list):
        raise ValueError("B3 monthly evolution response was not a list")

    points = [
        point
        for row in payload
        if isinstance(row, dict)
        for point in [_row_to_monthly_point(row, sym, end_date)]
        if point is not None
    ]
    return sorted(points, key=lambda point: (point.year, point.month))


async def list_known_indices() -> dict[str, str]:
    """Return ``symbol → friendly name`` map of indices we know how to fetch."""
    return dict(KNOWN_INDICES)
