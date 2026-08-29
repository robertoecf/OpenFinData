"""CVM — Comissão de Valores Mobiliários (dados abertos).

Listed-company data + investment funds.

Listed-company (CIA_ABERTA) coverage:

| Module           | Product (CVM)                                 | Cadence    |
|------------------|-----------------------------------------------|------------|
| `companies.py`   | Companies registry                            | static     |
| `financials.py`  | DFP (annual) / ITR (quarterly) statements     | yearly/qtr |
| `ipe.py`         | IPE — fatos relevantes / comunicados / atas   | event      |
| `fca.py`         | FCA — formulário cadastral (geral / VM / DRI) | yearly     |

Fund (FI / FIF) coverage:

| Module             | Product (CVM)                                | Cadence           |
|--------------------|----------------------------------------------|-------------------|
| `funds.py`         | CAD legado (`cad_fi.csv`) + INF_DIARIO (cota)| static / daily    |
| `cadastro.py`      | RCVM 175 registro fundo/classe/subclasse     | daily (Tue–Sat)   |
| `holdings.py`      | CDA (Composição da Carteira) — every asset   | monthly           |
| `lamina.py`        | LAMINA (factsheet + rentabilidade mês/ano)   | monthly           |
| `profile.py`       | PERFIL_MENSAL (cotistas por tipo)            | monthly           |
| `fii.py`           | FII — Fundos Imobiliários (geral + complemento) | monthly        |
| `fidc.py`          | FIDC — Fundos de Direitos Creditórios (TAB I/IV/VII) | monthly   |
| `fip.py`           | FIP — Fundos de Investimento em Participações | quarterly        |
| `_directory.py`    | HTML scrape helper for dynamic period lookup | (utility)         |
"""

from findata.sources.cvm._directory import (
    latest_period,
    list_files,
    list_periods,
)
from findata.sources.cvm.cadastro import (
    FundCadastro,
    FundClasse,
    FundSubclass,
    get_fund_cadastro,
)
from findata.sources.cvm.companies import Company, get_companies, search_company
from findata.sources.cvm.fca import (
    FCAGeneral,
    FCAInvestorRelations,
    FCASecurity,
    get_fca_dri,
    get_fca_geral,
    get_fca_valores_mobiliarios,
)
from findata.sources.cvm.fidc import (
    FIDCDireitosCreditorios,
    FIDCGeneral,
    FIDCPatrimonio,
    get_fidc_direitos_creditorios,
    get_fidc_geral,
    get_fidc_pl,
)
from findata.sources.cvm.fii import (
    FIIComplement,
    FIIGeneral,
    get_fii_complemento,
    get_fii_geral,
)
from findata.sources.cvm.financials import (
    FinancialEntry,
    StatementType,
    get_dfp,
    get_itr,
)
from findata.sources.cvm.fip import FIPInforme, get_fip
from findata.sources.cvm.funds import Fund, FundDaily, get_fund_catalog, get_fund_daily
from findata.sources.cvm.holdings import FundHolding, get_fund_holdings
from findata.sources.cvm.ipe import IPEDocument, get_ipe
from findata.sources.cvm.lamina import (
    FundLamina,
    FundLaminaReturnMonth,
    FundLaminaReturnYear,
    get_fund_lamina,
    get_fund_monthly_returns,
    get_fund_yearly_returns,
)
from findata.sources.cvm.profile import FundProfile, get_fund_profile

__all__ = [
    "Company",
    "FCAGeneral",
    "FCAInvestorRelations",
    "FCASecurity",
    "FIDCDireitosCreditorios",
    "FIDCGeneral",
    "FIDCPatrimonio",
    "FIIComplement",
    "FIIGeneral",
    "FIPInforme",
    "FinancialEntry",
    "Fund",
    "FundCadastro",
    "FundClasse",
    "FundDaily",
    "FundHolding",
    "FundLamina",
    "FundLaminaReturnMonth",
    "FundLaminaReturnYear",
    "FundProfile",
    "FundSubclass",
    "IPEDocument",
    "StatementType",
    "get_companies",
    "get_dfp",
    "get_fca_dri",
    "get_fca_geral",
    "get_fca_valores_mobiliarios",
    "get_fidc_direitos_creditorios",
    "get_fidc_geral",
    "get_fidc_pl",
    "get_fii_complemento",
    "get_fii_geral",
    "get_fip",
    "get_fund_cadastro",
    "get_fund_catalog",
    "get_fund_daily",
    "get_fund_holdings",
    "get_fund_lamina",
    "get_fund_monthly_returns",
    "get_fund_profile",
    "get_fund_yearly_returns",
    "get_ipe",
    "get_itr",
    "latest_period",
    "list_files",
    "list_periods",
    "search_company",
]
