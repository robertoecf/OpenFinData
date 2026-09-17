# B3 listed-funds catalog

Status: official JSON adapter. Not an HTML scrape.

## Use case

The B3 listed-funds pages (`fundsListedPage/ETF`, `ETF-RF`, `FII`, `FI-INFRA`,
…) are the official split between equity ETFs, fixed-income ETFs, FIIs and
FI-Infra. A ticker ending in `11` does not encode that split — `SPXR11` and
`HGLG11` share a suffix. The resolver's offline core still guesses FII for an
unknown `*11`; REST, MCP and `findata resolve` then consult this catalog.
A catalog miss does not keep the FII suffix guess (`Indefinido`).

## Endpoint

The Angular app calls:

```text
https://sistemaswebb3-listados.b3.com.br/fundsListedProxy/Search/GetListFunds/<base64>
```

The query is UTF-8 JSON, same pattern as `indexProxy`:

```json
{
  "language": "pt-br",
  "pageNumber": 1,
  "pageSize": 100,
  "typeFund": "ETF",
  "keyword": ""
}
```

`typeFund` is the string from `fundsListedPage/assets/funds.json` (`ETF`,
`ETF-RF`, `FII`, `FI-INFRA`, …), not a numeric `typeCEM`. `pageSize` 100 is the
largest size that still returns rows; 200 comes back empty.

Checked live on 2026-09-16: `SPBZ` and `SPXR` are `ETF` (renda variável);
`LFTS` is `ETF-RF`; `IFRA` is `FI-INFRA`, not `ETF-RF`.

## Guardrails

- Use `findata.http_client.get_json`. Do not parse `fundsListedPage` HTML.
- Do not treat ETF1 or other commercial classifiers as a source.
- Unit tests must mock HTTP with `respx`.
- The catalog type does not set S&P-500 geography by itself. The provider may
  infer `exposure=Internacional` from the official `fundName` (`S&P`, `IE`,
  `QUANTO`, …). Underlying (Tesouro vs debênture) stays on the curated seed.

## Surfaces

```bash
findata b3 listed --type ETF
findata b3 listed SPXR11
findata resolve SPBZ11
```

```text
GET /b3/listed-funds
GET /b3/listed-funds?type=ETF-RF
GET /b3/listed-funds?ticker=SPXR11
GET /resolver/resolve?ticker=SPBZ11
```
