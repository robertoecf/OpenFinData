"""ANBIMA public-file source — parsing + API smoke (respx-mocked)."""

from __future__ import annotations

import re
from datetime import date

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from findata.api.app import app
from findata.http_client import clear_cache
from findata.sources.anbima.indices import (
    DEBENTURES_URL,  # noqa: F401 — exported constant, helps type-checking
    ETTJ_URL,
    TPF_URL,  # noqa: F401 — exported constant, helps type-checking
    _date_to_iso,
    _f_br,
    _ima_cache,
    get_debentures,
    get_ettj,
    get_tpf,
)


@pytest.fixture(autouse=True)
def _clean_state() -> None:
    """Wipe HTTP and parsed-data caches between tests."""
    clear_cache()
    _ima_cache.invalidate()


# ── Parser unit tests ────────────────────────────────────────────


def test_f_br_parses_brazilian_decimals() -> None:
    assert _f_br("0,1294") == pytest.approx(0.1294)
    assert _f_br("1.234,56") == pytest.approx(1234.56)
    assert _f_br("--") is None
    assert _f_br("N/D") is None
    assert _f_br("") is None
    assert _f_br(None) is None
    assert _f_br("garbage") is None


def test_date_to_iso_normalises_formats() -> None:
    assert _date_to_iso("26/04/2026") == "2026-04-26"
    assert _date_to_iso("01/01/2026") == "2026-01-01"
    assert _date_to_iso("26/04/26") == "2026-04-26"
    assert _date_to_iso("2026-04-26") == "2026-04-26"


# ── ETTJ ──────────────────────────────────────────────────────────


_ETTJ_CSV = """24/04/2026;Beta 1;Beta 2;Beta 3;Beta 4;Lambda 1;Lambda 2
PREFIXADOS;0,12;0,01;-0,03;0,04;0,65;0,28
IPCA;0,06;0,03;-0,02;0,03;1,47;0,56

ETTJ Inflação Implicita (IPCA)
Vertices;ETTJ IPCA;ETTJ PREF;Inflação Implícita
126;8,6115;14,0861;5,0405
252;8,1460;13,8019;5,2298
1.260;7,6951;13,6947;5,5709
"""


@respx.mock
async def test_ettj_parses_csv_table() -> None:
    respx.get(ETTJ_URL).mock(
        return_value=httpx.Response(200, text=_ETTJ_CSV, headers={"Content-Type": "text/csv"})
    )
    pts = await get_ettj(date(2026, 4, 24))
    assert len(pts) == 3
    assert pts[0].vertice_du == 126
    assert pts[0].taxa_ipca_pct == pytest.approx(8.6115)
    assert pts[0].taxa_pre_pct == pytest.approx(14.0861)
    assert pts[0].inflacao_implicita_pct == pytest.approx(5.0405)
    # Thousands-sep handled
    assert pts[2].vertice_du == 1260


# ── Debêntures ────────────────────────────────────────────────────


_DEB_TXT = (
    "ANBIMA - Associação ...\n"
    "\n"
    "Código@Nome@Repac./  Venc.@Índice/ Correção@Taxa de Compra@Taxa de Venda@"
    "Taxa Indicativa@Desvio Padrão@Intervalo Indicativo Minimo@"
    "Intervalo Indicativo Máximo@PU@% PU Par / % VNE@Duration@% Reune@Referência NTN-B\n"
    "PETR12@PETROLEO BRASILEIRO S.A.@01/06/2030@DI + 1,5%@1,02@0,63@0,83@0,06@"
    "0,76@0,89@1027,08@101,84@607,92@5@\n"
    "VALE13@VALE S.A.@04/10/2027@DI + 2,0%@--@--@--@--@--@--@N/D@27,71@N/D@@\n"
)


@respx.mock
async def test_debentures_parses_at_separated_txt() -> None:
    respx.get(re.compile(r"https://.*db\d{6}\.txt")).mock(
        return_value=httpx.Response(200, text=_DEB_TXT, headers={"Content-Type": "text/plain"})
    )
    out = await get_debentures(date(2026, 4, 24))
    assert len(out) == 2
    assert out[0].codigo == "PETR12"
    assert out[0].emissor.startswith("PETROLEO")
    assert out[0].taxa_indicativa_pct == pytest.approx(0.83)
    assert out[0].pu == pytest.approx(1027.08)
    assert out[1].codigo == "VALE13"
    assert out[1].pu is None  # "N/D" parsed to None
    assert out[1].taxa_compra_pct is None  # "--"


# ── Títulos Públicos (TPF) ────────────────────────────────────────


_TPF_TXT = (
    "ANBIMA - Associação ...\n"
    "\n"
    "Titulo@Data Referencia@Codigo SELIC@Data Base/Emissao@Data Vencimento@"
    "Tx. Compra@Tx. Venda@Tx. Indicativas@PU@Desvio padrao@"
    "Interv. Ind. Inf. (D0)@Interv. Ind. Sup. (D0)@"
    "Interv. Ind. Inf. (D+1)@Interv. Ind. Sup. (D+1)@Criterio\n"
    "LTN@20260612@100000@20230106@20260701@14,3812@14,3519@14,3671@993,098676@"
    "0,00641938699644@14,2321@14,5625@14,222@14,5595@Calculado\n"
    "LFT@20260612@210100@20000701@20260901@0,0016@-0,0034@0,0006@19201,839214@"
    "0,00172517877914@-0,0453@0,032@-0,0468@0,0303@Calculado\n"
)


@respx.mock
async def test_tpf_parses_at_separated_txt() -> None:
    respx.get(re.compile(r"https://.*ms\d{6}\.txt")).mock(
        return_value=httpx.Response(200, text=_TPF_TXT, headers={"Content-Type": "text/plain"})
    )
    out = await get_tpf(date(2026, 6, 12))
    assert len(out) == 2
    assert out[0].titulo == "LTN"
    assert out[0].data_referencia == "2026-06-12"
    assert out[0].data_vencimento == "2026-07-01"  # compact YYYYMMDD → ISO
    assert out[0].taxa_indicativa_pct == pytest.approx(14.3671)
    assert out[0].pu == pytest.approx(993.098676)
    assert out[0].criterio == "Calculado"
    assert out[1].titulo == "LFT"
    assert out[1].taxa_venda_pct == pytest.approx(-0.0034)  # negative rate kept


# ── API smoke ────────────────────────────────────────────────────


@respx.mock
def test_anbima_ettj_endpoint() -> None:
    respx.get(ETTJ_URL).mock(
        return_value=httpx.Response(200, text=_ETTJ_CSV, headers={"Content-Type": "text/csv"})
    )
    client = TestClient(app)
    r = client.get("/anbima/ettj?data=2026-04-24")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 3
    assert body[0]["vertice_du"] == 126


@respx.mock
def test_anbima_debentures_endpoint() -> None:
    respx.get(re.compile(r"https://.*db\d{6}\.txt")).mock(
        return_value=httpx.Response(200, text=_DEB_TXT, headers={"Content-Type": "text/plain"})
    )
    client = TestClient(app)
    r = client.get("/anbima/debentures?data=2026-04-24")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2


@respx.mock
def test_anbima_debentures_filter_by_emissor() -> None:
    respx.get(re.compile(r"https://.*db\d{6}\.txt")).mock(
        return_value=httpx.Response(200, text=_DEB_TXT, headers={"Content-Type": "text/plain"})
    )
    client = TestClient(app)
    r = client.get("/anbima/debentures?data=2026-04-24&emissor=Vale")
    assert r.status_code == 200
    assert [d["codigo"] for d in r.json()] == ["VALE13"]


@respx.mock
def test_anbima_tpf_endpoint() -> None:
    respx.get(re.compile(r"https://.*ms\d{6}\.txt")).mock(
        return_value=httpx.Response(200, text=_TPF_TXT, headers={"Content-Type": "text/plain"})
    )
    client = TestClient(app)
    r = client.get("/anbima/tpf?data=2026-06-12")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["titulo"] == "LTN"


@respx.mock
def test_anbima_tpf_filter_by_titulo() -> None:
    respx.get(re.compile(r"https://.*ms\d{6}\.txt")).mock(
        return_value=httpx.Response(200, text=_TPF_TXT, headers={"Content-Type": "text/plain"})
    )
    client = TestClient(app)
    r = client.get("/anbima/tpf?data=2026-06-12&titulo=LFT")
    assert r.status_code == 200
    assert [d["titulo"] for d in r.json()] == ["LFT"]


def test_root_endpoint_lists_anbima_in_main_sources() -> None:
    client = TestClient(app)
    body = client.get("/meta").json()
    assert "anbima" in body["sources"]
    # The auth-required block was removed — ANBIMA is fully public now.
    assert "sources_with_auth" not in body
