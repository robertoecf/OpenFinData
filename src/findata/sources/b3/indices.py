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

from pydantic import BaseModel

from findata.http_client import get_json

INDEX_PROXY = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall/GetPortfolioDay"

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


_DEFAULT_PAGE_SIZE = 200
_MAX_PAGES = 10  # safety cap: largest index has ~250 issues


def _encode_query(index: str, page_size: int = _DEFAULT_PAGE_SIZE, page_number: int = 1) -> str:
    payload = {
        "language": "pt-br",
        "pageNumber": page_number,
        "pageSize": page_size,
        "index": index.upper(),
        "segment": "1",
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


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


async def list_known_indices() -> dict[str, str]:
    """Return ``symbol → friendly name`` map of indices we know how to fetch."""
    return dict(KNOWN_INDICES)
