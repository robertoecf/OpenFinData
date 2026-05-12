"""B3 COTAHIST + indexProxy tests.

COTAHIST is a fixed-width line format (245 cols, ISO-8859-1, integer
prices in cents). We synthesise valid 245-byte records to exercise the
parser without downloading the real 89-MB annual file.

Index portfolios are JSON behind a base64-encoded query string — we
intercept and assert the encoded payload.
"""

from __future__ import annotations

import base64
import io
import json
import re
import zipfile
from datetime import date

import httpx
import pytest
import respx

from findata.http_client import clear_cache
from findata.sources.b3.cotahist import (
    _LINE_WIDTH,
    _parse_line,
    get_cotahist_month,
    get_cotahist_year,
)
from findata.sources.b3.indices import (
    KNOWN_INDICES,
    _encode_monthly_evolution_query,
    _encode_query,
    get_index_monthly_evolution,
    get_index_portfolio,
    list_known_indices,
)


@pytest.fixture(autouse=True)
def _clean_caches() -> None:
    clear_cache()


# ── COTAHIST fixed-width parser ─────────────────────────────────────


def _make_cotahist_line(
    *,
    tipreg: str = "01",
    data: str = "20240326",
    cod_bdi: str = "02",
    codneg: str = "PETR4",
    tp_mercado: str = "010",
    nomres: str = "PETROBRAS",
    especi: str = "PN      N2",
    moeda: str = "R$",
    open_cents: int = 4019,  # R$ 40.19
    high_cents: int = 4099,
    low_cents: int = 3999,
    avg_cents: int = 4050,
    close_cents: int = 4090,
    bid_cents: int = 4089,
    ask_cents: int = 4090,
    n_trades: int = 12345,
    qty: int = 67_890_123,
    vol_cents: int = 274_456_789_012,  # R$ 2,744,567,890.12
    isin: str = "BRPETRACNPR6",
    fator: int = 1,
) -> str:
    """Build one valid 245-character COTAHIST line."""
    fields = [
        tipreg.ljust(2)[:2],
        data.ljust(8)[:8],
        cod_bdi.ljust(2)[:2],
        codneg.ljust(12)[:12],
        tp_mercado.rjust(3, "0")[:3],
        nomres.ljust(12)[:12],
        especi.ljust(10)[:10],
        "0".rjust(3, "0"),  # PRAZOT
        moeda.ljust(4)[:4],
        str(open_cents).rjust(13, "0")[:13],
        str(high_cents).rjust(13, "0")[:13],
        str(low_cents).rjust(13, "0")[:13],
        str(avg_cents).rjust(13, "0")[:13],
        str(close_cents).rjust(13, "0")[:13],
        str(bid_cents).rjust(13, "0")[:13],
        str(ask_cents).rjust(13, "0")[:13],
        str(n_trades).rjust(5, "0")[:5],
        str(qty).rjust(18, "0")[:18],
        str(vol_cents).rjust(18, "0")[:18],
        "0".rjust(13, "0"),  # PREEXE
        " ",  # INDOPC
        "00000000",  # DATVEN
        str(fator).rjust(7, "0")[:7],
        "0".rjust(13, "0"),  # PTOEXE
        isin.ljust(12)[:12],
        "000",  # DISMES
    ]
    line = "".join(fields)
    assert len(line) == _LINE_WIDTH, f"got {len(line)}, expected {_LINE_WIDTH}"
    return line


def test_parse_line_decodes_prices_in_cents() -> None:
    line = _make_cotahist_line()
    row = _parse_line(line)
    assert row is not None
    assert row.ticker == "PETR4"
    assert row.data == "2024-03-26"
    assert row.cod_bdi == "02"
    assert row.preco_abertura == 40.19
    assert row.preco_maximo == 40.99
    assert row.preco_minimo == 39.99
    assert row.preco_ultimo == 40.90
    assert row.qtd_titulos_negociados == 67_890_123
    # 274_456_789_012 cents → 2,744,567,890.12 reais
    assert row.volume_financeiro == 2_744_567_890.12
    assert row.isin == "BRPETRACNPR6"


def test_parse_line_applies_fator_cotacao_for_lot_quoted_funds() -> None:
    """Regression — Codex adversarial review surfaced that closed-end
    funds like FNAM11 quote prices for a lot of FATCOT shares (1000),
    so the unitary price needs FATCOT division."""
    line = _make_cotahist_line(
        codneg="FNAM11",
        nomres="FNAM",
        especi="UNT     ",
        open_cents=33,
        high_cents=34,
        low_cents=33,
        avg_cents=33,
        close_cents=34,
        bid_cents=33,
        ask_cents=34,
        qty=715_000,
        vol_cents=24_221,
        fator=1000,
        isin="BRFNAMCTF013",
    )
    row = _parse_line(line)
    assert row is not None
    assert row.fator_cotacao == 1000
    # raw=34 → cents=0.34 → per-share = 0.34 / 1000 = 0.00034
    assert row.preco_ultimo == 0.00034
    assert row.preco_abertura == 0.00033
    # Volume is total cash — NOT divided by FATCOT.
    assert row.volume_financeiro == 242.21


def test_parse_line_skips_header_record() -> None:
    line = "00COTAHIST.2024".ljust(_LINE_WIDTH)
    assert _parse_line(line) is None


def test_parse_line_skips_short_lines() -> None:
    # Trailer is "99..." but shorter than 245 chars in some files
    assert _parse_line("99COTAHIST FIM") is None


def _make_cotahist_zip(lines: list[str]) -> bytes:
    """Wrap lines in a COTAHIST_A####.TXT inside a zip (ISO-8859-1)."""
    txt = "\r\n".join(lines).encode("iso-8859-1")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("COTAHIST_A2024.TXT", txt)
    return buf.getvalue()


@respx.mock
async def test_cotahist_year_filters_by_ticker() -> None:
    lines = [
        "00COTAHIST.2024".ljust(_LINE_WIDTH),  # header
        _make_cotahist_line(codneg="PETR4", close_cents=4090),
        _make_cotahist_line(codneg="VALE3", close_cents=6712),
        _make_cotahist_line(codneg="PETR4", data="20240327", close_cents=4150),
        "99COTAHIST.2024".ljust(_LINE_WIDTH),  # trailer
    ]
    respx.get(re.compile(r"https://.*COTAHIST_A2024\.ZIP")).mock(
        return_value=httpx.Response(200, content=_make_cotahist_zip(lines))
    )
    rows = await get_cotahist_year(2024, ticker="PETR4")
    assert len(rows) == 2
    assert {r.data for r in rows} == {"2024-03-26", "2024-03-27"}
    assert rows[0].preco_ultimo == 40.90
    assert rows[1].preco_ultimo == 41.50


@respx.mock
async def test_cotahist_year_filters_by_market_code() -> None:
    lines = [
        _make_cotahist_line(codneg="PETR4", cod_bdi="02"),
        _make_cotahist_line(codneg="PETR4", cod_bdi="78"),  # option
        _make_cotahist_line(codneg="PETR4", cod_bdi="96"),  # fracionário
    ]
    respx.get(re.compile(r"https://.*COTAHIST_A2024\.ZIP")).mock(
        return_value=httpx.Response(200, content=_make_cotahist_zip(lines))
    )
    rows = await get_cotahist_year(2024, ticker="PETR4", market_codes=["02"])
    assert len(rows) == 1
    assert rows[0].cod_bdi == "02"


@respx.mock
async def test_cotahist_no_match_returns_empty() -> None:
    lines = [_make_cotahist_line(codneg="PETR4")]
    respx.get(re.compile(r"https://.*COTAHIST_A2024\.ZIP")).mock(
        return_value=httpx.Response(200, content=_make_cotahist_zip(lines))
    )
    rows = await get_cotahist_year(2024, ticker="UNKN3")
    assert rows == []


async def test_cotahist_year_rejects_unfiltered_call() -> None:
    """Regression — annual file is 2.6M records; require ticker or codes."""
    with pytest.raises(ValueError, match="ticker or market_codes"):
        await get_cotahist_year(2024)


@respx.mock
async def test_cotahist_month_allows_unfiltered_call() -> None:
    """Monthly files are small enough to scan unfiltered."""
    lines = [_make_cotahist_line(codneg="PETR4"), _make_cotahist_line(codneg="VALE3")]
    respx.get(re.compile(r"https://.*COTAHIST_M032024\.ZIP")).mock(
        return_value=httpx.Response(200, content=_make_cotahist_zip(lines))
    )
    rows = await get_cotahist_month(2024, 3)
    assert len(rows) == 2


# ── Index portfolio ─────────────────────────────────────────────────


def test_encode_query_is_round_trippable_base64_json() -> None:
    encoded = _encode_query("ibov")  # case-insensitive
    decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
    assert decoded["index"] == "IBOV"
    assert decoded["pageNumber"] == 1
    assert decoded["language"] == "pt-br"


_IBOV_PAYLOAD = {
    "page": {"pageNumber": 1, "pageSize": 200, "totalRecords": 3, "totalPages": 1},
    "header": {
        "date": "27/04/26",
        "text": "Quantidade Teórica Total",
        "part": "100,000",
        "partAcum": None,
        "textReductor": "Redutor",
        "reductor": "14.469.518,97844297",
        "theoricalQty": "91.261.531.350",
    },
    "results": [
        {
            "segment": None,
            "cod": "VALE3",
            "asset": "VALE",
            "type": "ON      NM",
            "part": "11,477",
            "partAcum": None,
            "theoricalQty": "3.688.870.616",
        },
        {
            "segment": None,
            "cod": "ITUB4",
            "asset": "ITAUUNIBANCO",
            "type": "PN      N1",
            "part": "8,083",
            "partAcum": None,
            "theoricalQty": "5.027.870.728",
        },
        {
            "segment": None,
            "cod": "PETR4",
            "asset": "PETROBRAS",
            "type": "PN  ERJ N2",
            "part": "7,537",
            "partAcum": None,
            "theoricalQty": "4.410.960.450",
        },
    ],
}


@respx.mock
async def test_get_index_portfolio_decodes_brazilian_decimals() -> None:
    respx.get(re.compile(r"https://.*indexProxy/indexCall/GetPortfolioDay/.+")).mock(
        return_value=httpx.Response(200, json=_IBOV_PAYLOAD)
    )
    p = await get_index_portfolio("IBOV")
    assert p.indice == "IBOV"
    assert p.nome == "Ibovespa"
    assert p.data == "27/04/26"
    assert p.qtd_teorica_total == 91_261_531_350
    assert p.redutor is not None
    assert abs(p.redutor - 14469518.97844297) < 1e-6
    assert len(p.componentes) == 3

    vale = next(c for c in p.componentes if c.ticker == "VALE3")
    assert vale.peso_pct == 11.477
    assert vale.qtd_teorica == 3_688_870_616
    assert vale.classe == "ON      NM"
    assert vale.indice == "IBOV"


async def test_list_known_indices_includes_canonical_set() -> None:
    indices = await list_known_indices()
    for symbol in ("IBOV", "IBXX", "SMLL", "IDIV", "IFIX"):
        assert symbol in indices
    assert indices["IBOV"] == "Ibovespa"
    assert KNOWN_INDICES is not indices  # defensive: returned a copy


@respx.mock
async def test_get_index_portfolio_handles_pagination() -> None:
    """Regression — ITAG has 222 components; we used to drop the last 22.

    Codex adversarial review caught this: page 1 returned 200, page 2
    contained the remaining 22, but the code only fetched page 1.
    """
    page1 = {
        "page": {"pageNumber": 1, "pageSize": 200, "totalRecords": 3, "totalPages": 2},
        "header": {
            "date": "27/04/26",
            "theoricalQty": "100.000.000",
            "reductor": "1,000",
        },
        "results": [
            {"cod": "AAAA3", "asset": "A", "type": "ON", "part": "1,0", "theoricalQty": "100"},
            {"cod": "BBBB3", "asset": "B", "type": "ON", "part": "1,0", "theoricalQty": "100"},
        ],
    }
    page2 = {
        "page": {"pageNumber": 2, "pageSize": 200, "totalRecords": 3, "totalPages": 2},
        "header": page1["header"],
        "results": [
            {"cod": "CCCC3", "asset": "C", "type": "ON", "part": "1,0", "theoricalQty": "100"},
        ],
    }

    call_count = {"n": 0}

    def _route(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        # The encoded query carries pageNumber — page 1 first, then page 2.
        return httpx.Response(200, json=page1 if call_count["n"] == 1 else page2)

    respx.get(re.compile(r"https://.*indexProxy/indexCall/GetPortfolioDay/.+")).mock(
        side_effect=_route,
    )
    p = await get_index_portfolio("ITAG")
    assert call_count["n"] == 2
    assert {c.ticker for c in p.componentes} == {"AAAA3", "BBBB3", "CCCC3"}


def test_encode_monthly_evolution_query_is_round_trippable_base64_json() -> None:
    encoded = _encode_monthly_evolution_query("ibov", date(2026, 1, 1), date(2026, 5, 11))
    decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
    assert decoded == {
        "language": "pt-br",
        "index": "IBOV",
        "dateInitial": "2026-01-01",
        "dateFinal": "2026-05-11",
    }


@respx.mock
async def test_get_index_monthly_evolution_normalizes_b3_rows() -> None:
    respx.get(re.compile(r"https://.*indexStatisticsProxy/IndexCall/GetMonthlyEvolution/.+")).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"month": 1, "year": 2026, "indexClosingRate": 181363.9},
                {"month": 5, "year": 2026, "indexClosingRate": "181.908,87"},
            ],
        )
    )

    rows = await get_index_monthly_evolution(
        "ibov",
        start=date(2026, 1, 1),
        end=date(2026, 5, 11),
    )

    assert [row.period for row in rows] == ["2026-01", "2026-05"]
    assert rows[0].date == "2026-01-31"
    assert rows[0].close == 181363.9
    assert rows[0].partial_month is False
    assert rows[1].date == "2026-05-11"
    assert rows[1].close == 181908.87
    assert rows[1].partial_month is True
    assert rows[1].indice == "IBOV"
