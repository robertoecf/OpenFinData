"""ANBIMA — Brazilian financial markets association data.

Public file downloads from `www.anbima.com.br/informacoes/*`. No auth, no
API key. The same canonical numbers ANBIMA's commercial Sensedia API
returns, just shipped as daily static files anyone can fetch.

Public endpoints:
    - IMA family (IMA-B, IMA-S, IRF-M, ...)         — full history XLS
    - ETTJ (Estrutura a Termo, curva zero)          — daily CSV per reference date
    - Debêntures (mercado secundário)               — daily TXT per reference date

The `client.py` and `credentials.py` modules in this package were part of
the earlier authenticated-API pivot and are no longer used by these public
endpoints. They stay so the `findata.auth` framework underneath remains
reusable for sources that genuinely require auth (SUSEP, BNDES, ...).
"""

from findata.sources.anbima.indices import (
    DebentureQuote,
    ETTJDataPoint,
    IMADataPoint,
    IMAFamily,
    TPFQuote,
    get_debentures,
    get_ettj,
    get_ima,
    get_ima_history,
    get_tpf,
)

__all__ = [
    "DebentureQuote",
    "ETTJDataPoint",
    "IMADataPoint",
    "IMAFamily",
    "TPFQuote",
    "get_debentures",
    "get_ettj",
    "get_ima",
    "get_ima_history",
    "get_tpf",
]
