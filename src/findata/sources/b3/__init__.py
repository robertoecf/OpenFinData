"""B3 — Brasil, Bolsa, Balcão (stock exchange data).

| Module        | Source                                  | Cadence              |
|---------------|-----------------------------------------|----------------------|
| `quotes.py`   | Yahoo Finance (via yfinance)            | live + intraday      |
| `cotahist.py` | B3 SerHist fixed-width archive (1986+)  | annual / month / day |
| `indices.py`  | B3 indexProxy/indexStatisticsProxy JSON | portfolios + monthly |

The optional ``[b3]`` extra installs ``yfinance`` for live quotes.
``cotahist`` and ``indices`` use only stdlib + httpx (already in core).
"""

from findata.sources.b3.cotahist import (
    CotahistTrade,
    get_cotahist_day,
    get_cotahist_month,
    get_cotahist_year,
)
from findata.sources.b3.indices import (
    KNOWN_INDICES,
    IndexConstituent,
    IndexMonthlyPoint,
    IndexPortfolio,
    get_index_monthly_evolution,
    get_index_portfolio,
    list_known_indices,
)
from findata.sources.b3.quotes import (
    StockHistoryPoint,
    StockQuote,
    get_history,
    get_multiple_quotes,
    get_quote,
)

__all__ = [
    "KNOWN_INDICES",
    "CotahistTrade",
    "IndexConstituent",
    "IndexMonthlyPoint",
    "IndexPortfolio",
    "StockHistoryPoint",
    "StockQuote",
    "get_cotahist_day",
    "get_cotahist_month",
    "get_cotahist_year",
    "get_history",
    "get_index_monthly_evolution",
    "get_index_portfolio",
    "get_multiple_quotes",
    "get_quote",
    "list_known_indices",
]
