"""The resolver engine: deterministic rule cascade + ``resolve_asset``.

Classification is decided in this order, most-specific signal first:

1. **Curated seed** (:mod:`findata.resolver.seed`) — only the non-derivable
   cases (ETF underlying, global-mandate FIA).
2. **Structural rules** (this module) — name/ticker patterns that *are*
   derivable: COE, debenture, CRA/CRI, bank paper, Tesouro, IE/global,
   FII, FIA/Ações, Multimercado, FIDC/FIP, plain tickers.
3. **External providers** (optional, injected) — Mais Retorno MCP, CVM/B3,
   restricted web search. Not bundled here (they are client-side / networked);
   the resolver takes a chain of async callbacks so a deployment can wire them.
   Each step that fires lowers ``confidence`` and is appended to ``cascade``.

The seed + rules layers are pure and offline, so the spec's test set resolves
deterministically with no network. ``source`` is ``"openfindata"`` for every
core hit; an external provider that overrides a field updates ``source`` too.

Key traps the ordering encodes (spec §Armadilhas):
  * ``"Crédito Estruturado"`` is RF (credit), **not** Estruturados — checked
    before any COE/Estruturados rule.
  * **COE** is always Estruturados and **never** an ETF.
  * an ETF/fund is classified by its **underlying** (IFRA11 debêntures → RF;
    IVVB11 ações → RV).
  * geography is the orthogonal ``exposure`` axis, never a macro class: a
    global-mandate FIA is RV + exposure=Internacional; IVVB11 is RV +
    Internacional; a BDR is RV + Internacional.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

from findata.resolver.models import (
    AssetClassification,
    CvmInfo,
    DebentureInfo,
    Exposure,
    IdentifierResolved,
    TaxInfo,
)
from findata.resolver.normalize import NormalizedInput, normalize
from findata.resolver.seed import lookup_seed

# Issuers with a well-known programme of Lei-12.431 infrastructure debentures.
# Used only as a *heuristic* signal (debenture + IPCA-linked + infra issuer →
# likely incentivada); the live ANBIMA/debentures.com.br step confirms by ISIN.
# Explicit list = auditable; not a claim that every issue from these is 12.431.
_INFRA_DEBENTURE_ISSUERS = frozenset(
    {
        "PETROBRAS",
        "RUMO",
        "ENGIE",
        "TAESA",
        "ISA",
        "CTEEP",
        "ECORODOVIAS",
        "CPFL",
        "ENEVA",
        "AEGEA",
        "EQUATORIAL",
        "NEOENERGIA",
        "SABESP",
        "COPEL",
        "ELETROBRAS",
        "ENERGISA",
        "OMEGA",
        "AUREN",
        "COMGAS",
        "VIBRA",
        "MOTIVA",
        "SANEPAR",
        "CEMIG",
    }
)

_GLOBAL_KEYWORDS = (
    "GLOBAL",
    "GLOBAIS",
    "WORLD",
    "WORLDWIDE",
    "INTERNACIONAL",
    "INTERNATIONAL",
    "EXTERIOR",
)

_FUND_CONTEXT_TOKENS = ("FIA", "FIC", "FIM", "FUNDO", "FDO", "FUND", "MASTER", "FI")

# ``as_of`` is stamped in Brazil time: the consolidation is a BR-market artifact,
# so a server in another timezone must not shift the audit date across midnight.
_BR_TZ = ZoneInfo("America/Sao_Paulo")

# Above this confidence (and with a decided macro) the cascade short-circuits:
# no point spending an external round-trip to confirm a strong core hit.
_CONFIDENT_ENOUGH = 0.9


class AssetProvider(Protocol):
    """An external cascade step (Mais Retorno, CVM/B3, web search).

    Receives the normalized input and the best classification so far; returns an
    enriched classification (new ``source``, possibly higher-detail fields) or
    ``None`` to pass. Implementations live outside the library because they are
    networked / client-side; the resolver only orchestrates them.
    """

    async def __call__(
        self, norm: NormalizedInput, current: AssetClassification
    ) -> AssetClassification | None: ...


# ── Small parsers ──────────────────────────────────────────────────


def parse_indexador(name_folded: str) -> str | None:
    """Recover the index from a folded RF instrument name, or ``None``."""
    if "IPCA" in name_folded:
        return "IPCA+"
    if "CDI+" in name_folded or "CDI +" in name_folded:
        return "CDI+"
    if "%CDI" in name_folded or "% CDI" in name_folded or "DO CDI" in name_folded:
        return "%CDI"
    if "SELIC" in name_folded:
        return "SELIC"
    if "PREFIX" in name_folded or "PRE FIXAD" in name_folded:
        return "PREFIXADO"
    if "CDI" in name_folded:
        return "%CDI"
    return None


def _subclasse_from_indexador(indexador: str | None) -> str:
    if indexador == "IPCA+":
        return "Indexada à Inflação"
    if indexador in {"%CDI", "CDI+", "SELIC"}:
        return "Pós-fixada"
    if indexador == "PREFIXADO":
        return "Prefixada"
    return "Crédito Privado"


def _infer_incentivada(
    norm: NormalizedInput, indexador: str | None
) -> tuple[bool | None, str, str | None]:
    """Decide Lei-12.431 incentivada for a debenture. Returns (flag, note, basis).

    ``basis`` is ``"explicit"`` for an in-name signal (high certainty),
    ``"heuristic"`` for the IPCA+infra-issuer inference (must be confirmed by
    ISIN, so the caller keeps confidence low and lets the cascade verify), or
    ``None`` when there is no signal at all (we return ``None`` for the flag —
    unknown, never assert False).
    """
    if norm.name_contains("INCENTIVAD", "12.431", "12431", "INFRAESTRUTURA", "FI-INFRA") or (
        norm.has_token("INFRA") and norm.has_token("DEB", "DEBENTURE", "DEBENTURES")
    ):
        return (
            True,
            "Incentivada Lei 12.431 (sinal explícito de infraestrutura no nome).",
            "explicit",
        )
    issuer_hit = any(t in _INFRA_DEBENTURE_ISSUERS for t in norm.tokens)
    if issuer_hit and indexador == "IPCA+":
        return (
            True,
            (
                "Incentivada Lei 12.431 SÓ por heurística (debênture IPCA+ de emissor com "
                "programa de infra); confidence baixa de propósito — confirmar por ISIN em "
                "ANBIMA/debentures.com.br antes de tratar como isento."
            ),
            "heuristic",
        )
    return None, "", None


# ── The rule cascade ───────────────────────────────────────────────


def _rule_payload(norm: NormalizedInput) -> dict[str, Any]:
    """Run the structural rules; return a partial payload dict (always non-empty).

    The first matching rule wins. Every branch sets at least ``kind`` and
    ``macro_class``; the assembler fills defaults for the rest.
    """
    n = norm

    # 0) Name-trap: "Crédito Estruturado" is structured *credit* → RF, NOT
    #    Estruturados. Must precede the COE rule.
    if n.name_contains("CREDITO ESTRUTURADO"):
        return {
            "kind": "fundo",
            "macro_class": "Renda Fixa",
            "subclasse": "Crédito Privado",
            "exposure": "Brasil",
            "underlying_nature": "credito",
            "confidence": 0.9,
            "notes": "Name-trap: 'Crédito Estruturado' é crédito (RF), não COE/Estruturados.",
        }

    # 1) COE / operações estruturadas → Estruturados, never an ETF.
    if n.has_token("COE") or n.name_contains(
        "OPERACOES ESTRUTURADAS",
        "OPERACAO ESTRUTURADA",
        "CERTIFICADO DE OPERACOES",
        "CERT DE OPERACOES",
        "NOTA ESTRUTURADA",
        "NOTAS ESTRUTURADAS",
    ):
        return {
            "kind": "coe",
            "macro_class": "Estruturados",
            "subclasse": "COE",
            "underlying_nature": "outro",
            "estrutura": "COE",
            "confidence": 0.95,
            "notes": "COE (Certificado de Operações Estruturadas, CETIP) → Estruturados.",
        }

    # 2) Debenture → RF; parse indexador + incentivada.
    if n.has_token("DEB", "DEBENTURE", "DEBENTURES", "DEBENT"):
        indexador = parse_indexador(n.name_folded)
        incentivada, note, basis = _infer_incentivada(n, indexador)
        deb: dict[str, Any] = {"indexador": indexador}
        tax: dict[str, Any] = {}
        if incentivada:
            deb["incentivada_1243"] = True
            tax["isento"] = True
        # An *explicit* infra signal is high-confidence. The issuer+IPCA
        # heuristic is deliberately kept below the cascade short-circuit
        # threshold (_CONFIDENT_ENOUGH) so a wired provider re-checks the
        # isento claim by ISIN instead of it being taken as fact.
        if basis == "explicit":
            confidence = 0.92
        elif basis == "heuristic":
            confidence = 0.7
        else:
            confidence = 0.88
        return {
            "kind": "debenture",
            "macro_class": "Renda Fixa",
            "subclasse": _subclasse_from_indexador(indexador),
            "exposure": "Brasil",
            "underlying_nature": "credito",
            "estrutura": "debenture",
            "debenture": deb,
            "tax": tax,
            "confidence": confidence,
            "notes": note or "Debênture → Renda Fixa.",
        }

    # 3) Securitização (CRA/CRI) → RF.
    if n.has_token("CRA", "CRI") or n.name_contains(
        "CERT. RECEBIVEIS", "CERTIFICADO DE RECEBIVEIS"
    ):
        agro = n.has_token("CRA") or n.name_contains("AGRONEGOCIO")
        return {
            "kind": "cra" if agro else "cri",
            "macro_class": "Renda Fixa",
            "subclasse": "Crédito Privado",
            "exposure": "Brasil",
            "underlying_nature": "recebiveis",
            "tax": {"isento": True},  # CRA/CRI: IR-exempt for PF
            "confidence": 0.9,
            "notes": "Securitização (recebíveis) → Renda Fixa, isento p/ PF.",
        }

    # 4) Bank paper (CDB/RDB/LIG/Letra Financeira/Letra de Câmbio) → RF.
    #    NB: the bare 2-char tokens "LC"/"LF" are too collision-prone (they hit
    #    issuer names, share classes, internal codes), so they are matched only
    #    via their unambiguous phrases, never as bare tokens.
    if n.has_token("CDB", "RDB", "LIG") or n.name_contains("LETRA FINANCEIRA", "LETRA DE CAMBIO"):
        return {
            "kind": "cdb",
            "macro_class": "Renda Fixa",
            "subclasse": _subclasse_from_indexador(parse_indexador(n.name_folded)),
            "exposure": "Brasil",
            "underlying_nature": "credito",
            "confidence": 0.88,
            "notes": "Emissão bancária → Renda Fixa.",
        }
    if n.has_token("LCI", "LCA") or n.name_contains(
        "LETRA DE CREDITO IMOBILIARIO", "LETRA DE CREDITO DO AGRONEGOCIO"
    ):
        return {
            "kind": "lci_lca",
            "macro_class": "Renda Fixa",
            "subclasse": _subclasse_from_indexador(parse_indexador(n.name_folded)),
            "exposure": "Brasil",
            "underlying_nature": "credito",
            "tax": {"isento": True},
            "confidence": 0.9,
            "notes": "LCI/LCA → Renda Fixa, isento p/ PF.",
        }

    # 5) Tesouro / public bonds → RF.
    if n.has_token("TESOURO", "NTN", "LTN", "LFT", "NTNB", "NTNF") or n.name_contains(
        "TESOURO DIRETO", "TESOURO SELIC", "TESOURO IPCA", "TESOURO PREFIXADO"
    ):
        return {
            "kind": "tesouro",
            "macro_class": "Renda Fixa",
            "subclasse": _subclasse_from_indexador(parse_indexador(n.name_folded)),
            "exposure": "Brasil",
            "underlying_nature": "tesouro",
            "confidence": 0.95,
            "notes": "Título público federal → Renda Fixa.",
        }

    # 6) Internacional EXPOSURE — IE structure, or global keyword. Geography is
    #    the `exposure` axis, NOT a macro class: the asset class still comes from
    #    the fund type (equities→RV, dívida externa→RF, else Multimercado). BOTH
    #    triggers require a fund context: a bare "IE"/"GLOBAL" token outside a
    #    fund name is too collision-prone (e.g. "COMPANHIA IE ENERGIA SA").
    #    Runs before FIA/Ações so "FIC FIA IE" / "GLOBAL FIM" land here.
    fund_context = n.has_token(*_FUND_CONTEXT_TOKENS)
    if fund_context and (
        n.has_token("IE")
        or n.name_contains(*_GLOBAL_KEYWORDS, "INVESTIMENTO NO EXTERIOR", "INV EXTERIOR")
    ):
        equities = n.has_token("FIA") or n.name_contains("ACOES", "EQUITY")
        rf = n.name_contains("DIVIDA EXTERNA", "RENDA FIXA", "BOND", "CREDITO", "DEBT")
        if equities:
            macro, subclasse, underlying = "Renda Variável", "Ações Global", "acoes"
        elif rf:
            macro, subclasse, underlying = "Renda Fixa", "Dívida Externa", "credito"
        else:
            macro, subclasse, underlying = "Multimercado", "Multimercado Global", "multiativos"
        return {
            "kind": "fundo",
            "macro_class": macro,
            "subclasse": subclasse,
            "exposure": "Internacional",
            "underlying_nature": underlying,
            "estrutura": "IE" if n.has_token("IE") else "FIC",
            "confidence": 0.9,
            "notes": f"Mandato internacional (IE / global): {macro}, exposição Internacional.",
        }

    # 7) FII (by name; ticker-only 11s are caught at step 12).
    if n.has_token("FII") or n.name_contains(
        "FUNDO IMOBILIARIO",
        "FDO INV IMOB",
        "FUNDO DE INVESTIMENTO IMOBILIARIO",
        "INVESTIMENTO IMOBILIARIO",
    ):
        return {
            "kind": "fii",
            "macro_class": "Renda Variável",
            "subclasse": "FII",
            "exposure": "Brasil",
            "underlying_nature": "imoveis",
            "estrutura": "FII",
            "confidence": 0.92,
            "notes": "Fundo Imobiliário → Renda Variável (subclasse FII).",
        }

    # 8) ETF by name, no curated hit → infer underlying from name keywords.
    if n.has_token("ETF") or n.name_contains("ISHARES", "INDEX FUND"):
        rf = n.name_contains("RENDA FIXA", "DEBENTURE", "BOND", "IMA-", "IRF-", "TESOURO", "INFRA")
        if rf:
            sovereign = n.name_contains("TESOURO", "IMA-", "IRF-", "LFT", "NTN", "LTN")
            credit = n.name_contains("DEBENTURE", "INFRA")
            return {
                "kind": "etf",
                "macro_class": "Renda Fixa",
                "subclasse": "ETF de renda fixa",
                "exposure": "Brasil",
                "underlying_nature": "debentures"
                if credit
                else ("tesouro" if sovereign else "credito"),
                "estrutura": "ETF",
                "confidence": 0.78,
                "notes": "ETF com underlying de renda fixa (inferido do nome).",
            }
        intl = n.name_contains(*_GLOBAL_KEYWORDS, "S&P", "SP500", "NASDAQ", "MSCI", "EUA", "US ")
        return {
            "kind": "etf",
            "macro_class": "Renda Variável",
            "subclasse": "ETF de ações internacional" if intl else "ETF de ações",
            "exposure": "Internacional" if intl else "Brasil",
            "underlying_nature": "acoes",
            "estrutura": "ETF",
            "confidence": 0.72,
            "notes": "ETF sem ticker no seed; underlying assumido = ações. Confirmar.",
        }

    # 9) FIDC → RF (direitos creditórios, natureza de crédito).
    if n.has_token("FIDC") or n.name_contains("DIREITOS CREDITORIOS"):
        return {
            "kind": "fundo",
            "macro_class": "Renda Fixa",
            "subclasse": "Crédito Estruturado",
            "exposure": "Brasil",
            "underlying_nature": "recebiveis",
            "estrutura": "FIDC",
            "confidence": 0.85,
            "notes": "FIDC (direitos creditórios) → Renda Fixa (crédito).",
        }

    # 10) FIP → Alternativos (private equity).
    if n.has_token("FIP") or n.name_contains("PARTICIPACOES", "PRIVATE EQUITY"):
        return {
            "kind": "fundo",
            "macro_class": "Alternativos",
            "subclasse": "Private Equity",
            "underlying_nature": "private_equity",
            "estrutura": "FIP",
            "confidence": 0.88,
            "notes": "FIP (participações) → Alternativos.",
        }

    # 11) Multimercado.
    if n.has_token("FIM") or n.name_contains("MULTIMERCADO", "MULTIESTRATEGIA", "MACRO"):
        return {
            "kind": "fundo",
            "macro_class": "Multimercado",
            "subclasse": "Multimercado",
            "underlying_nature": "multiativos",
            "estrutura": "FIM",
            "confidence": 0.85,
            "notes": "Multimercado.",
        }

    # 12) Ações / FIA (domestic equities).
    if n.has_token("FIA") or n.name_contains("FUNDO DE ACOES", "ACOES", "EQUITY"):
        return {
            "kind": "fundo",
            "macro_class": "Renda Variável",
            "subclasse": "Ações",
            "exposure": "Brasil",
            "underlying_nature": "acoes",
            "estrutura": "FIA",
            "confidence": 0.85,
            "notes": "Fundo de Ações → Renda Variável.",
        }

    # 13) Ticker shapes (no name signal won above).
    suffix = n.ticker_digits_suffix
    if n.ticker:
        # 11 not in any curated ETF/RF list → overwhelmingly a FII.
        if suffix == "11":
            return {
                "kind": "fii",
                "macro_class": "Renda Variável",
                "subclasse": "FII",
                "exposure": "Brasil",
                "underlying_nature": "imoveis",
                "estrutura": "FII",
                "confidence": 0.72,
                "notes": "Ticker terminado em 11 fora do seed de ETFs → FII (heurística).",
            }
        # BDR (34/35): recibo de ação estrangeira. RV por classe, mas o holder
        # carrega risco cambial/exterior → Internacional por exposição (default;
        # BDRs de empresa brasileira no exterior são exceção, não a regra).
        if suffix in {"34", "35"}:
            return {
                "kind": "bdr",
                "macro_class": "Renda Variável",
                "subclasse": "BDR",
                "exposure": "Internacional",
                "underlying_nature": "acoes",
                "confidence": 0.8,
                "notes": "BDR (recibo de ação estrangeira) → RV, exposição Internacional.",
            }
        # 3-8: ordinary/preferred share — ação brasileira.
        return {
            "kind": "acao",
            "macro_class": "Renda Variável",
            "subclasse": "Ações",
            "exposure": "Brasil",
            "underlying_nature": "acoes",
            "confidence": 0.85,
            "notes": "Ação listada na B3 → Renda Variável.",
        }

    # 14) Nothing matched — honest "I don't know" for HITL review.
    return {
        "kind": "outro",
        "macro_class": "Indefinido",
        "confidence": 0.2,
        "notes": "Sem sinal estrutural suficiente; requer revisão (human-in-the-loop).",
    }


# ── Assembly ───────────────────────────────────────────────────────


def _resolve_exposure(payload: dict[str, Any]) -> Exposure | None:
    """The geography axis, taken from the rule/seed payload. ``None`` when the
    rule could not decide (e.g. a COE whose underlying may be either)."""
    explicit = payload.get("exposure")
    return cast(Exposure, explicit) if explicit is not None else None


def _assemble(norm: NormalizedInput, payload: dict[str, Any], step: str) -> AssetClassification:
    """Turn a rule/seed payload dict into the typed output contract."""
    deb = payload.get("debenture")
    tax = payload.get("tax") or {}
    return AssetClassification(
        identifier_resolved=IdentifierResolved(
            cnpj=norm.cnpj, ticker=norm.ticker, isin=norm.isin, name=norm.name_raw
        ),
        kind=payload["kind"],
        cvm=CvmInfo(
            classe=payload.get("cvm_classe"),
            anbima_categoria=payload.get("anbima_categoria"),
            estrutura=payload.get("estrutura"),
        ),
        macro_class=payload["macro_class"],
        subclasse=payload.get("subclasse"),
        exposure=_resolve_exposure(payload),
        underlying_nature=payload.get("underlying_nature"),
        debenture=DebentureInfo(**deb) if deb else None,
        tax=TaxInfo(**tax),
        source=payload.get("source", "openfindata"),
        confidence=payload.get("confidence", 0.5),
        as_of=datetime.now(_BR_TZ).date().isoformat(),
        cascade=[step],
        notes=payload.get("notes"),
    )


def classify(norm: NormalizedInput) -> AssetClassification:
    """Pure, offline classification: curated seed → structural rules.

    Always returns a record (``Indefinido`` when nothing matches). This is the
    deterministic core that the spec test set exercises with no network.
    """
    seed = lookup_seed(ticker=norm.ticker, cnpj=norm.cnpj, name_folded=norm.name_folded)
    if seed is not None:
        return _assemble(norm, seed.payload, step="openfindata:curated")
    return _assemble(norm, _rule_payload(norm), step="openfindata:rules")


async def resolve_asset(
    name: str | None = None,
    *,
    cnpj: str | None = None,
    ticker: str | None = None,
    isin: str | None = None,
    providers: list[AssetProvider] | None = None,
) -> AssetClassification:
    """Resolve an asset to its Wealthuman classification.

    Runs the deterministic core (curated seed → structural rules), then walks the
    optional external provider chain (Mais Retorno → CVM/B3 → restricted web
    search) only while the result is still weak (``Indefinido`` or low
    confidence). Each provider that fires is appended to ``cascade`` and may lower
    confidence; the deepest one to set a field owns ``source``.

    No PII: callers pass only an asset identifier, never client data.
    """
    norm = normalize(name=name, cnpj=cnpj, ticker=ticker, isin=isin)
    result = classify(norm)

    for provider in providers or []:
        # Stop early once we are confident — saves the network round-trips.
        if result.macro_class != "Indefinido" and result.confidence >= _CONFIDENT_ENOUGH:
            break
        enriched = await provider(norm, result)
        if enriched is not None:
            enriched.cascade = [*result.cascade, *enriched.cascade]
            result = enriched
    return result
