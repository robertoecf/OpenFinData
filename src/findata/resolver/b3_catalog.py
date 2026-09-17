"""Official B3 listed-funds provider for ``resolve_asset``.

Injected by REST, MCP and ``findata resolve``. Not the default of the
library ``resolve_asset`` call — the spec test set stays offline.

Only ``*11`` tickers are looked up. The catalog type is the official
ETF / ETF-RF / FII / FI-INFRA split; geography is still inferred from the
official ``fundName`` when the type does not carry it (``ETF-INT-RF`` does).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from findata.resolver.models import (
    AssetClassification,
    CvmInfo,
    DebentureInfo,
    IdentifierResolved,
    Signal,
    TaxInfo,
)
from findata.resolver.normalize import NormalizedInput, fold, tokenize
from findata.sources.b3.listed_funds import ListedFund, lookup_listed_fund

_BR_TZ = ZoneInfo("America/Sao_Paulo")
_CATALOG_CONFIDENCE = 0.91
_INTL_NAME_MARKERS = (
    "S&P",
    "SP500",
    "NASDAQ",
    "MSCI",
    "GLOBAL",
    "WORLD",
    "WORLDWIDE",
    "INTERNACIONAL",
    "INTERNATIONAL",
    "EXTERIOR",
    "QUANTO",
)

# Official B3 typeFund → allocation fields the listing itself supports.
_TYPE_HINTS: dict[str, dict[str, Any]] = {
    "ETF": {
        "kind": "etf",
        "macro_class": "Renda Variável",
        "subclasse": "ETF de ações",
        "underlying_nature": "acoes",
        "estrutura": "ETF",
        "exposure": None,
        "notes": "Catálogo B3: ETF de renda variável. Exposição geográfica não vem do tipo.",
    },
    "ETF-RF": {
        "kind": "etf",
        "macro_class": "Renda Fixa",
        "subclasse": "ETF de renda fixa",
        "underlying_nature": "credito",
        "estrutura": "ETF",
        "exposure": "Brasil",
        "notes": "Catálogo B3: ETF de renda fixa.",
    },
    "ETF-INT-RF": {
        "kind": "etf",
        "macro_class": "Renda Fixa",
        "subclasse": "ETF de renda fixa internacional",
        "underlying_nature": "credito",
        "estrutura": "ETF",
        "exposure": "Internacional",
        "notes": "Catálogo B3: ETF de renda fixa internacional.",
    },
    "ETF-FII": {
        "kind": "etf",
        "macro_class": "Renda Variável",
        "subclasse": "ETF de FII",
        "underlying_nature": "imoveis",
        "estrutura": "ETF",
        "exposure": "Brasil",
        "notes": "Catálogo B3: ETF de FII.",
    },
    "ETF-CRIPTO": {
        "kind": "etf",
        "macro_class": "Alternativos",
        "subclasse": "ETF de cripto",
        "underlying_nature": "outro",
        "estrutura": "ETF",
        "exposure": None,
        "notes": "Catálogo B3: ETF de cripto.",
    },
    "ETF-MOEDA": {
        "kind": "etf",
        "macro_class": "Alternativos",
        "subclasse": "ETF de moeda",
        "underlying_nature": "cambio",
        "estrutura": "ETF",
        "exposure": None,
        "notes": "Catálogo B3: ETF de moeda.",
    },
    "FII": {
        "kind": "fii",
        "macro_class": "Renda Variável",
        "subclasse": "FII",
        "underlying_nature": "imoveis",
        "estrutura": "FII",
        "exposure": "Brasil",
        "notes": "Catálogo B3: fundo imobiliário listado.",
    },
    "FI-INFRA": {
        "kind": "fundo",
        "macro_class": "Renda Fixa",
        "subclasse": "FI-Infra",
        "underlying_nature": "debentures",
        "estrutura": "FI-INFRA",
        "exposure": "Brasil",
        "notes": "Catálogo B3: FI-Infra (incentivado). Não é o tipo ETF-RF.",
        "incentivada": True,
    },
    "FIAGRO": {
        "kind": "fundo",
        "macro_class": "Alternativos",
        "subclasse": "FIAGRO",
        "underlying_nature": "outro",
        "estrutura": "FIAGRO",
        "exposure": "Brasil",
        "notes": "Catálogo B3: FIAGRO.",
    },
    "FIAGRO-FII": {
        "kind": "fundo",
        "macro_class": "Renda Variável",
        "subclasse": "FIAGRO",
        "underlying_nature": "imoveis",
        "estrutura": "FIAGRO",
        "exposure": "Brasil",
        "notes": "Catálogo B3: FIAGRO imobiliário.",
    },
    "FIAGRO-FIDC": {
        "kind": "fundo",
        "macro_class": "Renda Fixa",
        "subclasse": "FIAGRO",
        "underlying_nature": "recebiveis",
        "estrutura": "FIAGRO",
        "exposure": "Brasil",
        "notes": "Catálogo B3: FIAGRO de direitos creditórios.",
    },
    "FIAGRO-FIP": {
        "kind": "fundo",
        "macro_class": "Alternativos",
        "subclasse": "FIAGRO",
        "underlying_nature": "private_equity",
        "estrutura": "FIAGRO",
        "exposure": "Brasil",
        "notes": "Catálogo B3: FIAGRO de participações.",
    },
    "FIP": {
        "kind": "fundo",
        "macro_class": "Alternativos",
        "subclasse": "Private Equity",
        "underlying_nature": "private_equity",
        "estrutura": "FIP",
        "exposure": None,
        "notes": "Catálogo B3: FIP listado.",
    },
    "FIDC": {
        "kind": "fundo",
        "macro_class": "Renda Fixa",
        "subclasse": "Crédito Estruturado",
        "underlying_nature": "recebiveis",
        "estrutura": "FIDC",
        "exposure": "Brasil",
        "notes": "Catálogo B3: FIDC listado.",
    },
}


def _name_signals_internacional(fund_name: str) -> bool:
    folded = fold(fund_name)
    if any(fold(marker) in folded for marker in _INTL_NAME_MARKERS):
        return True
    return "IE" in set(tokenize(fund_name))


def classification_from_listed_fund(norm: NormalizedInput, fund: ListedFund) -> AssetClassification:
    """Map one official B3 listed-fund row onto the resolver contract."""
    hint = _TYPE_HINTS.get(fund.type_fund)
    if hint is None:
        hint = {
            "kind": "fundo",
            "macro_class": "Indefinido",
            "subclasse": fund.type_fund,
            "underlying_nature": "outro",
            "estrutura": fund.type_fund,
            "exposure": None,
            "notes": f"Catálogo B3: tipo {fund.type_fund} sem mapeamento de alocação.",
        }
    exposure = hint["exposure"]
    notes = hint["notes"]
    if exposure is None and _name_signals_internacional(fund.fund_name):
        exposure = "Internacional"
        notes = f"{notes} Exposição Internacional inferida do nome oficial B3."
    debenture = None
    tax: dict[str, Any] = {}
    if hint.get("incentivada"):
        debenture = DebentureInfo(
            incentivada_1243=True,
            lei_12431_status="confirmed",
            indexador=None,
        )
        tax = {"isento": True, "isento_status": "confirmed_exempt"}
    return AssetClassification(
        identifier_resolved=IdentifierResolved(
            cnpj=norm.cnpj,
            ticker=norm.ticker or fund.ticker,
            isin=norm.isin,
            name=norm.name_raw or fund.fund_name,
        ),
        kind=hint["kind"],
        cvm=CvmInfo(estrutura=hint["estrutura"]),
        macro_class=hint["macro_class"],
        subclasse=hint["subclasse"],
        exposure=exposure,
        underlying_nature=hint["underlying_nature"],
        debenture=debenture,
        tax=TaxInfo(**tax),
        source="b3",
        confidence=_CATALOG_CONFIDENCE,
        as_of=datetime.now(_BR_TZ).date().isoformat(),
        cascade=["b3:listed-funds"],
        signals=[
            Signal(
                rule="b3_listed_funds",
                evidence=f"ticker={fund.ticker}",
                detail=f"type={fund.type_fund}",
            )
        ],
        notes=notes,
    )


async def b3_listed_provider(
    norm: NormalizedInput, current: AssetClassification
) -> AssetClassification | None:
    """Cascade step: official B3 catalog for ``*11`` tickers."""
    del current
    if not norm.ticker or norm.ticker_digits_suffix != "11":
        return None
    fund = await lookup_listed_fund(norm.ticker)
    if fund is None:
        return None
    return classification_from_listed_fund(norm, fund)
