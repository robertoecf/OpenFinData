"""CVM RCVM 175 cadastro + INF_DIARIO CNPJ matching (offline, respx)."""

from __future__ import annotations

import io
import zipfile

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from findata.api.app import app
from findata.api.mcp_app import mcp_app
from findata.http_client import clear_cache
from findata.sources.cvm.cadastro import REGISTRO_URL, _registro_cache, get_fund_cadastro
from findata.sources.cvm.funds import FUND_DAILY_URL, get_fund_daily


@pytest.fixture(autouse=True)
def _clean_caches() -> None:
    clear_cache()
    _registro_cache.invalidate()


def _zip_csv(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text.encode("iso-8859-1"))
    return buf.getvalue()


_FUNDO_HEADER = (
    "ID_Registro_Fundo;CNPJ_Fundo;Codigo_CVM;Data_Registro;Data_Constituicao;"
    "Tipo_Fundo;Denominacao_Social;Data_Cancelamento;Situacao;Data_Inicio_Situacao;"
    "Data_Adaptacao_RCVM175;Data_Inicio_Exercicio_Social;Data_Fim_Exercicio_Social;"
    "Patrimonio_Liquido;Data_Patrimonio_Liquido;Diretor;CNPJ_Administrador;"
    "Administrador;Tipo_Pessoa_Gestor;CPF_CNPJ_Gestor;Gestor\n"
)
_CLASSE_HEADER = (
    "ID_Registro_Fundo;ID_Registro_Classe;CNPJ_Classe;Codigo_CVM;Data_Registro;"
    "Data_Constituicao;Data_Inicio;Tipo_Classe;Denominacao_Social;Situacao;"
    "Data_Inicio_Situacao;Classificacao;Indicador_Desempenho;Classe_Cotas;"
    "Classificacao_Anbima;Tributacao_Longo_Prazo;Entidade_Investimento;"
    "Permitido_Aplicacao_CemPorCento_Exterior;Classe_ESG;Forma_Condominio;"
    "Exclusivo;Publico_Alvo;Patrimonio_Liquido;Data_Patrimonio_Liquido;"
    "CNPJ_Auditor;Auditor;CNPJ_Custodiante;Custodiante;CNPJ_Controlador;Controlador\n"
)
_SUB_HEADER = (
    "ID_Registro_Classe;ID_Subclasse;Codigo_CVM;Data_Constituicao;Data_Inicio;"
    "Denominacao_Social;Situacao;Data_Inicio_Situacao;Forma_Condominio;Exclusivo;"
    "Publico_Alvo;Previdenciario;Exclusivo_INR;Exclusivo_Previdencia_Complementar\n"
)

_AMW_FUNDO = (
    "66089;38729027000192;377910;2020-09-28;2020-09-17;FI;"
    "AMW PREVIDÊNCIA GESTÃO ATIVA FUNDO DE INVESTIMENTO FINANCEIRO MULTIMERCADO;;"
    "Em Funcionamento Normal;2021-02-01;2024-09-27;2026-01-01;2026-12-31;"
    "55454535.34;2024-09-27;GUSTAVO COTTA PIERSANTI;59281253000123;"
    "BTG PACTUAL SERVIÇOS FINANCEIROS S/A DTVM;PJ;26737584000176;AMW ASSET MANAGEMENT LTDA\n"
)
_AMW_CLASSE = (
    "66089;12189;38729027000192;65510;2024-09-27;2020-09-17;2024-09-27;"
    "Classes de Cotas de Fundos FIF;"
    "AMW PREVIDÊNCIA GESTÃO ATIVA FUNDO DE INVESTIMENTO FINANCEIRO MULTIMERCADO;"
    "Em Funcionamento Normal;2024-09-27;Multimercado;DI de um dia;N;"
    "Previdência Multimercado Livre;N/A;;N;N;Aberto;S;Profissional;"
    "29428273.87;2026-08-26;61562112000120;"
    "PRICEWATERHOUSECOOPERS AUDITORES INDEPENDENTES LTDA.;"
    "30306294000145;BANCO BTG PACTUAL S/A;59281253000123;"
    "BTG PACTUAL SERVIÇOS FINANCEIROS S/A DTVM\n"
)
_OTHER_FUNDO = (
    "51617;21494444000109;238686;2015-02-04;2015-02-04;FI;"
    "ICATU VANGUARDA ABSOLUTO FIF PREVIDENCIÁRIO RENDA FIXA CRÉDITO PRIVADO;;"
    "Em Funcionamento Normal;2015-05-12;2024-12-02;2026-04-01;2027-03-31;"
    "1933990736.88;2024-11-29;RICARDO BARBIERI;00066670000100;"
    "BEM DTVM;PJ;68622174000120;ICATU VANGUARDA GESTÃO DE RECURSOS LTDA\n"
)


def _registro_zip() -> bytes:
    return _zip_csv(
        {
            "registro_fundo.csv": _FUNDO_HEADER + _AMW_FUNDO + _OTHER_FUNDO,
            "registro_classe.csv": _CLASSE_HEADER + _AMW_CLASSE,
            "registro_subclasse.csv": _SUB_HEADER,
        }
    )


@respx.mock
async def test_cadastro_by_punctuated_cnpj() -> None:
    respx.get(REGISTRO_URL).mock(return_value=httpx.Response(200, content=_registro_zip()))
    rows = await get_fund_cadastro(cnpj="38.729.027/0001-92")
    assert len(rows) == 1
    fund = rows[0]
    assert fund.cnpj == "38729027000192"
    assert fund.nome.startswith("AMW PREVID")
    assert fund.gestor.startswith("AMW ASSET")
    assert fund.classes[0].forma_condominio == "Aberto"
    assert fund.classes[0].classificacao == "Multimercado"
    assert fund.classes[0].classe_anbima.startswith("Previdência")
    assert fund.classes[0].patrimonio_liquido == 29428273.87


@respx.mock
async def test_cadastro_by_name_fragment() -> None:
    respx.get(REGISTRO_URL).mock(return_value=httpx.Response(200, content=_registro_zip()))
    rows = await get_fund_cadastro(q="icatu vanguarda absoluto fif")
    assert len(rows) == 1
    assert rows[0].cnpj == "21494444000109"


@respx.mock
async def test_cadastro_ignores_administrator_cnpj() -> None:
    respx.get(REGISTRO_URL).mock(return_value=httpx.Response(200, content=_registro_zip()))
    rows = await get_fund_cadastro(cnpj="59.281.253/0001-23")
    assert rows == []


@respx.mock
async def test_cadastro_requires_cnpj_or_q() -> None:
    with pytest.raises(ValueError, match="cnpj"):
        await get_fund_cadastro()


def _daily_zip() -> bytes:
    header = (
        "TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;DT_COMPTC;"
        "VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
    )
    rows = (
        "CLASSES - FIF;38.729.027/0001-92;;2026-08-03;1;2.94;100;0;0;1\n"
        "CLASSES - FIF;21.494.444/0001-09;;2026-08-03;1;2.95;200;0;0;1\n"
        "CLASSES - FIF;38.729.027/0001-92;;2026-08-04;1;2.95;101;10;0;1\n"
    )
    return _zip_csv({"inf_diario_fi_202608.csv": header + rows})


@respx.mock
async def test_daily_bare_digit_cnpj_matches_punctuated() -> None:
    url = FUND_DAILY_URL.format(ym="202608")
    respx.get(url).mock(return_value=httpx.Response(200, content=_daily_zip()))
    rows = await get_fund_daily(2026, 8, "38729027000192")
    assert len(rows) == 2
    assert {r.dt_comptc for r in rows} == {"2026-08-03", "2026-08-04"}
    assert all(r.cnpj == "38.729.027/0001-92" for r in rows)
    assert rows[1].vl_quota == 2.95
    assert rows[0].tp_fundo_classe == "CLASSES - FIF"


@respx.mock
def test_rest_cadastro_requires_cnpj_or_q() -> None:
    rest = TestClient(app).get("/cvm/funds/cadastro")
    assert rest.status_code == 400
    assert "cnpj" in rest.json()["detail"]


@respx.mock
def test_rest_and_mcp_cadastro_by_cnpj() -> None:
    respx.get(REGISTRO_URL).mock(return_value=httpx.Response(200, content=_registro_zip()))
    rest = TestClient(app).get("/cvm/funds/cadastro", params={"cnpj": "38729027000192"})
    assert rest.status_code == 200
    assert rest.json()[0]["codigo_cvm"] == "377910"
    mcp = TestClient(mcp_app).get(
        "/cvm/fund",
        params={"dataset": "catalog", "cnpj": "38.729.027/0001-92"},
    )
    assert mcp.status_code == 200
    assert mcp.json()[0]["cnpj"] == "38729027000192"


@respx.mock
def test_mcp_daily_accepts_digit_cnpj() -> None:
    url = FUND_DAILY_URL.format(ym="202608")
    respx.get(url).mock(return_value=httpx.Response(200, content=_daily_zip()))
    mcp = TestClient(mcp_app).get(
        "/cvm/fund",
        params={"dataset": "daily", "cnpj": "38729027000192", "year": 2026, "month": 8},
    )
    assert mcp.status_code == 200
    assert len(mcp.json()) == 2
