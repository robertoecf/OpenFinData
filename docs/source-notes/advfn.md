# ADVFN source note

Status: investigated only; not implemented as a source adapter.

## What was investigated

A 2015 gist at <https://gist.github.com/madsailor/955c77e70345bdda9ec2>
contains an old ADVFN financials scraper. It targeted pages such as:

```text
http://www.advfn.com/stock-market/NASDAQ/AAPL/financials
```

The gist is not suitable for direct reuse:

- no clear license in the gist;
- stale 2015 page parser;
- depends on an external `smf` module;
- maps only US exchanges in the sample code;
- current ADVFN markup no longer matches the `td class="s"` / `td class="sb"`
  assumptions;
- HTTPS may trigger Cloudflare-style blocking for simple agents.

## Live accessibility notes

On 2026-04-30, simple agent checks showed:

- `https://www.advfn.com/...` returned a Cloudflare-style `403` page;
- `http://www.advfn.com/...` returned an AAPL financials HTML page;
- `http://br.advfn.com/bolsa-de-valores/bovespa/petrobras-petr4/balanco`
  returned a Brazilian PETR4 financials page;
- the Brazilian page used current classes such as `label-field` and
  `number-field`.

## Recommendation

Do not add `src/findata/sources/advfn/` yet. Keep ADVFN as a possible
non-canonical comparison source only after official CVM/B3 coverage gaps are
exhausted.

Prefer, in order:

1. CVM official financial statements and fund files;
2. B3 official COTAHIST/index endpoints and derived helpers;
3. Tesouro/BCB/IPEA/ANBIMA official or public-file endpoints;
4. Yahoo Finance experimental chart data for market prices;
5. ADVFN only as an unofficial HTML fallback if a future user request requires
   it explicitly.
