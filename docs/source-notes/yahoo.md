# Yahoo Finance source note

Status: experimental, unofficial, best-effort.

## Use case

Yahoo Finance is useful for quick market-price retrieval by agents when the
project does not yet expose an official B3/CVM/Bacen equivalent for the exact
instrument or frequency.

Supported first in Dados Financeiros Abertos through the public chart endpoint:

```text
https://query1.finance.yahoo.com/v8/finance/chart/{symbol}
```

Examples:

```text
PETR4.SA
BOVA11.SA
^BVSP
BTC-USD
```

## Guardrails

- Do not treat Yahoo Finance as a canonical public-data source.
- Do not add API keys or RapidAPI dependencies for Yahoo.
- Prefer direct `findata.http_client.get_json` calls over `yfinance` for this
  adapter.
- Unit tests must use mocked HTTP responses.
- The `v7/finance/quote` endpoint is not part of the supported surface because
  it returned `Unauthorized` in the 2026-04-30 agent check.
- Intraday ranges have server-side limits. For example, older `1h` requests may
  fail when outside Yahoo's retention window.

## Current implementation

```bash
findata yahoo chart PETR4.SA --range 1mo --interval 1d
```

Python:

```python
from findata.sources.yahoo import get_chart

chart = await get_chart("PETR4.SA", range_="1mo", interval="1d")
```
