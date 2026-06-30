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
    Signal,
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


def _subclasse_from_indexador(indexador: str | None, default: str = "Crédito Privado") -> str:
    if indexador == "IPCA+":
        return "Indexada à Inflação"
    if indexador in {"%CDI", "CDI+", "SELIC"}:
        return "Pós-fixada"
    if indexador == "PREFIXADO":
        return "Prefixada"
    return default


# Public-bond type → indexador, for names that carry the bond code but not the
# index word (e.g. "NTN-B 2035" has no "IPCA"). Folded substrings, so "NTN-B"
# and "NTNB" both hit. NTN-C (IGP-M) is left to the generic path.
def _tesouro_indexador(n: NormalizedInput) -> str | None:
    explicit = parse_indexador(n.name_folded)
    if explicit is not None:
        return explicit
    if n.name_contains("NTN-B", "NTNB"):
        return "IPCA+"
    if n.name_contains("LFT"):
        return "SELIC"
    if n.name_contains("NTN-F", "NTNF", "LTN"):
        return "PREFIXADO"
    return None


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


def _apply_fiscal_certainty(basis: str | None, deb: dict[str, Any], tax: dict[str, Any]) -> None:
    """Stamp the fiscal certainty axis on the debenture/tax sub-dicts.

    An explicit infra signal is structurally certain (confirmed exempt); the
    issuer+IPCA heuristic is only a candidate; with no incentivada signal it is a
    plain debenture (12.431 not applicable, tax treatment still unknown).
    """
    if basis == "explicit":
        deb["lei_12431_status"] = "confirmed"
        tax["isento_status"] = "confirmed_exempt"
    elif basis == "heuristic":
        deb["lei_12431_status"] = "candidate"
        tax["isento_status"] = "candidate_exempt"
    else:
        deb["lei_12431_status"] = "not_applicable"


# ── Signal helpers ─────────────────────────────────────────────────


def _first_matching_token(n: NormalizedInput, candidates: tuple[str, ...]) -> str | None:
    """Return the first candidate that appears as a whole token, or ``None``."""
    tset = set(n.tokens)
    for c in candidates:
        if c in tset:
            return c
    return None


def _first_matching_phrase(n: NormalizedInput, candidates: tuple[str, ...]) -> str | None:
    """Return the first candidate that is a substring of the folded name, or ``None``."""
    for c in candidates:
        if c in n.name_folded:
            return c
    return None


def _signal(rule: str, evidence: str, detail: str | None = None) -> list[dict[str, Any]]:
    """Build the single-entry ``signals`` list a rule branch records."""
    entry: dict[str, Any] = {"rule": rule, "evidence": evidence}
    if detail is not None:
        entry["detail"] = detail
    return [entry]


def _debenture_payload(n: NormalizedInput, deb_evidence: str) -> dict[str, Any]:
    """Classify a debenture → RF; parse indexador + Lei-12.431 incentivada."""
    indexador = parse_indexador(n.name_folded)
    incentivada, note, basis = _infer_incentivada(n, indexador)
    deb: dict[str, Any] = {"indexador": indexador}
    tax: dict[str, Any] = {}
    if incentivada:
        deb["incentivada_1243"] = True
        tax["isento"] = True
    _apply_fiscal_certainty(basis, deb, tax)
    # An *explicit* infra signal is high-confidence. The issuer+IPCA heuristic is
    # deliberately kept below the cascade short-circuit threshold
    # (_CONFIDENT_ENOUGH) so a wired provider re-checks the isento claim by ISIN
    # instead of it being taken as fact.
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
        "signals": _signal(
            "debenture", deb_evidence, detail=f"basis={basis};indexador={indexador}"
        ),
    }


def _internacional_payload(n: NormalizedInput, intl_evidence: str) -> dict[str, Any]:
    """Classify an internacional-mandate fund (IE / global keyword in a fund name)."""
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
        "signals": _signal("internacional", intl_evidence, detail=f"macro={macro}"),
    }


def _etf_payload(n: NormalizedInput, etf_evidence: str) -> dict[str, Any]:
    """Classify an ETF matched by name → infer underlying from name keywords."""
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
            "signals": _signal("etf_name", etf_evidence, detail="underlying=rf"),
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
        "signals": _signal("etf_name", etf_evidence, detail="underlying=acoes"),
    }


def _ticker_payload(n: NormalizedInput) -> dict[str, Any]:
    """Classify a bare ticker by its digit suffix (no name signal won)."""
    suffix = n.ticker_digits_suffix
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
            "signals": _signal("ticker_suffix_11", f"ticker={n.ticker}"),
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
            "signals": _signal("bdr", f"ticker={n.ticker}"),
        }
    # 3-8: ordinary/preferred share — ação brasileira.
    if suffix in {"3", "4", "5", "6", "7", "8"}:
        return {
            "kind": "acao",
            "macro_class": "Renda Variável",
            "subclasse": "Ações",
            "exposure": "Brasil",
            "underlying_nature": "acoes",
            "confidence": 0.85,
            "notes": "Ação listada na B3 → Renda Variável.",
            "signals": _signal("acao", f"ticker={n.ticker}"),
        }
    # Other suffixes (1/2/9/10/12/13… subscription rights, receipts, odd codes)
    # carry no reliable structural signal → defer to HITL/provider cascade.
    return {
        "kind": "outro",
        "macro_class": "Indefinido",
        "confidence": 0.2,
        "notes": "Ticker com sufixo sem sinal estrutural suficiente; requer revisão (HITL).",
        "signals": _signal("ticker_suffix_unknown", f"ticker={n.ticker}"),
    }


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
            "signals": _signal("credito_estruturado_trap", "CREDITO ESTRUTURADO"),
        }

    # 1) COE / operações estruturadas → Estruturados, never an ETF.
    _coe_phrases = (
        "OPERACOES ESTRUTURADAS",
        "OPERACAO ESTRUTURADA",
        "CERTIFICADO DE OPERACOES",
        "CERT DE OPERACOES",
        "NOTA ESTRUTURADA",
        "NOTAS ESTRUTURADAS",
    )
    if n.has_token("COE") or n.name_contains(*_coe_phrases):
        coe_evidence = _first_matching_token(n, ("COE",)) or _first_matching_phrase(n, _coe_phrases)
        return {
            "kind": "coe",
            "macro_class": "Estruturados",
            "subclasse": "COE",
            "underlying_nature": "outro",
            "estrutura": "COE",
            "confidence": 0.95,
            "notes": "COE (Certificado de Operações Estruturadas, CETIP) → Estruturados.",
            "signals": _signal("coe", coe_evidence or "COE"),
        }

    # 2) Debenture → RF; parse indexador + incentivada.
    _deb_tokens = ("DEB", "DEBENTURE", "DEBENTURES", "DEBENT")
    if n.has_token(*_deb_tokens):
        return _debenture_payload(n, _first_matching_token(n, _deb_tokens) or "DEB")

    # 3) Securitização (CRA/CRI) → RF.
    _cra_phrases = ("CERT. RECEBIVEIS", "CERTIFICADO DE RECEBIVEIS")
    if n.has_token("CRA", "CRI") or n.name_contains(*_cra_phrases):
        cra_evidence = _first_matching_token(n, ("CRA", "CRI")) or _first_matching_phrase(
            n, _cra_phrases
        )
        agro = n.has_token("CRA") or n.name_contains("AGRONEGOCIO")
        return {
            "kind": "cra" if agro else "cri",
            "macro_class": "Renda Fixa",
            "subclasse": "Crédito Privado",
            "exposure": "Brasil",
            "underlying_nature": "recebiveis",
            "tax": {
                "isento": True,
                "isento_status": "confirmed_exempt",
            },  # CRA/CRI: IR-exempt for PF
            "confidence": 0.9,
            "notes": "Securitização (recebíveis) → Renda Fixa, isento p/ PF.",
            "signals": _signal("cra_cri", cra_evidence or "CRA/CRI"),
        }

    # 4) Bank paper (CDB/RDB/LIG/Letra Financeira/Letra de Câmbio) → RF.
    #    NB: the bare 2-char tokens "LC"/"LF" are too collision-prone (they hit
    #    issuer names, share classes, internal codes), so they are matched only
    #    via their unambiguous phrases, never as bare tokens.
    _bank_phrases = ("LETRA FINANCEIRA", "LETRA DE CAMBIO")
    if n.has_token("CDB", "RDB", "LIG") or n.name_contains(*_bank_phrases):
        bank_evidence = _first_matching_token(n, ("CDB", "RDB", "LIG")) or _first_matching_phrase(
            n, _bank_phrases
        )
        return {
            "kind": "cdb",
            "macro_class": "Renda Fixa",
            "subclasse": _subclasse_from_indexador(parse_indexador(n.name_folded)),
            "exposure": "Brasil",
            "underlying_nature": "credito",
            "confidence": 0.88,
            "notes": "Emissão bancária → Renda Fixa.",
            "signals": _signal("bank_paper", bank_evidence or "CDB"),
        }
    _lci_phrases = ("LETRA DE CREDITO IMOBILIARIO", "LETRA DE CREDITO DO AGRONEGOCIO")
    if n.has_token("LCI", "LCA") or n.name_contains(*_lci_phrases):
        lci_evidence = _first_matching_token(n, ("LCI", "LCA")) or _first_matching_phrase(
            n, _lci_phrases
        )
        return {
            "kind": "lci_lca",
            "macro_class": "Renda Fixa",
            "subclasse": _subclasse_from_indexador(parse_indexador(n.name_folded)),
            "exposure": "Brasil",
            "underlying_nature": "credito",
            "tax": {"isento": True, "isento_status": "confirmed_exempt"},
            "confidence": 0.9,
            "notes": "LCI/LCA → Renda Fixa, isento p/ PF.",
            "signals": _signal("lci_lca", lci_evidence or "LCI/LCA"),
        }

    # 5) Tesouro / public bonds → RF.
    _tesouro_tokens = ("TESOURO", "NTN", "LTN", "LFT", "NTNB", "NTNF")
    _tesouro_phrases = ("TESOURO DIRETO", "TESOURO SELIC", "TESOURO IPCA", "TESOURO PREFIXADO")
    if n.has_token(*_tesouro_tokens) or n.name_contains(*_tesouro_phrases):
        tesouro_evidence = _first_matching_token(n, _tesouro_tokens) or _first_matching_phrase(
            n, _tesouro_phrases
        )
        return {
            "kind": "tesouro",
            "macro_class": "Renda Fixa",
            # Public bonds carry the index in their type code, not always a word;
            # default to "Título Público", never the credit-private subclasse.
            "subclasse": _subclasse_from_indexador(_tesouro_indexador(n), default="Título Público"),
            "exposure": "Brasil",
            "underlying_nature": "tesouro",
            "confidence": 0.95,
            "notes": "Título público federal → Renda Fixa.",
            "signals": _signal("tesouro", tesouro_evidence or "TESOURO"),
        }

    # 6) Internacional EXPOSURE — IE structure, or global keyword. Geography is
    #    the `exposure` axis, NOT a macro class: the asset class still comes from
    #    the fund type (equities→RV, dívida externa→RF, else Multimercado). BOTH
    #    triggers require a fund context: a bare "IE"/"GLOBAL" token outside a
    #    fund name is too collision-prone (e.g. "COMPANHIA IE ENERGIA SA").
    #    Runs before FIA/Ações so "FIC FIA IE" / "GLOBAL FIM" land here.
    fund_context = n.has_token(*_FUND_CONTEXT_TOKENS)
    _intl_phrases = (*_GLOBAL_KEYWORDS, "INVESTIMENTO NO EXTERIOR", "INV EXTERIOR")
    if fund_context and (n.has_token("IE") or n.name_contains(*_intl_phrases)):
        intl_evidence = _first_matching_token(n, ("IE",)) or _first_matching_phrase(
            n, _intl_phrases
        )
        return _internacional_payload(n, intl_evidence or "IE")

    # 7) FII (by name; ticker-only 11s are caught at step 12).
    _fii_phrases = (
        "FUNDO IMOBILIARIO",
        "FDO INV IMOB",
        "FUNDO DE INVESTIMENTO IMOBILIARIO",
        "INVESTIMENTO IMOBILIARIO",
    )
    if n.has_token("FII") or n.name_contains(*_fii_phrases):
        fii_evidence = _first_matching_token(n, ("FII",)) or _first_matching_phrase(n, _fii_phrases)
        return {
            "kind": "fii",
            "macro_class": "Renda Variável",
            "subclasse": "FII",
            "exposure": "Brasil",
            "underlying_nature": "imoveis",
            "estrutura": "FII",
            "confidence": 0.92,
            "notes": "Fundo Imobiliário → Renda Variável (subclasse FII).",
            "signals": _signal("fii_name", fii_evidence or "FII"),
        }

    # 8) ETF by name, no curated hit → infer underlying from name keywords.
    _etf_phrases = ("ISHARES", "INDEX FUND")
    if n.has_token("ETF") or n.name_contains(*_etf_phrases):
        etf_evidence = _first_matching_token(n, ("ETF",)) or _first_matching_phrase(n, _etf_phrases)
        return _etf_payload(n, etf_evidence or "ETF")

    # 9) FIDC → RF (direitos creditórios, natureza de crédito).
    if n.has_token("FIDC") or n.name_contains("DIREITOS CREDITORIOS"):
        fidc_evidence = _first_matching_token(n, ("FIDC",)) or "DIREITOS CREDITORIOS"
        return {
            "kind": "fundo",
            "macro_class": "Renda Fixa",
            "subclasse": "Crédito Estruturado",
            "exposure": "Brasil",
            "underlying_nature": "recebiveis",
            "estrutura": "FIDC",
            "confidence": 0.85,
            "notes": "FIDC (direitos creditórios) → Renda Fixa (crédito).",
            "signals": _signal("fidc", fidc_evidence),
        }

    # 10) FIP → Alternativos (private equity). The FIP token is unambiguous; the
    #     "PARTICIPACOES"/"PRIVATE EQUITY" phrases need a fund context so a holding
    #     company ("XYZ Participações SA") is not classified as a fund.
    _fip_phrases = ("PARTICIPACOES", "PRIVATE EQUITY")
    if n.has_token("FIP") or (fund_context and n.name_contains(*_fip_phrases)):
        fip_evidence = _first_matching_token(n, ("FIP",)) or _first_matching_phrase(n, _fip_phrases)
        return {
            "kind": "fundo",
            "macro_class": "Alternativos",
            "subclasse": "Private Equity",
            "underlying_nature": "private_equity",
            "estrutura": "FIP",
            "confidence": 0.88,
            "notes": "FIP (participações) → Alternativos.",
            "signals": _signal("fip", fip_evidence or "FIP"),
        }

    # 11) Multimercado. FIM token is unambiguous; the phrases (esp. "MACRO",
    #     common in trade names like "Macro Atacadista") need a fund context.
    _mm_phrases = ("MULTIMERCADO", "MULTIESTRATEGIA", "MACRO")
    if n.has_token("FIM") or (fund_context and n.name_contains(*_mm_phrases)):
        mm_evidence = _first_matching_token(n, ("FIM",)) or _first_matching_phrase(n, _mm_phrases)
        return {
            "kind": "fundo",
            "macro_class": "Multimercado",
            "subclasse": "Multimercado",
            "underlying_nature": "multiativos",
            "estrutura": "FIM",
            "confidence": 0.85,
            "notes": "Multimercado.",
            "signals": _signal("multimercado", mm_evidence or "FIM"),
        }

    # 12) Ações / FIA (domestic equities). FIA token is unambiguous; the bare
    #     "ACOES"/"EQUITY" keywords need a fund context (avoid company names).
    _fia_phrases = ("FUNDO DE ACOES", "ACOES", "EQUITY")
    if n.has_token("FIA") or (fund_context and n.name_contains(*_fia_phrases)):
        fia_evidence = _first_matching_token(n, ("FIA",)) or _first_matching_phrase(n, _fia_phrases)
        return {
            "kind": "fundo",
            "macro_class": "Renda Variável",
            "subclasse": "Ações",
            "exposure": "Brasil",
            "underlying_nature": "acoes",
            "estrutura": "FIA",
            "confidence": 0.85,
            "notes": "Fundo de Ações → Renda Variável.",
            "signals": _signal("fia", fia_evidence or "FIA"),
        }

    # 13) Ticker shapes (no name signal won above).
    if n.ticker:
        return _ticker_payload(n)

    # 14) Nothing matched — honest "I don't know" for HITL review.
    return {
        "kind": "outro",
        "macro_class": "Indefinido",
        "confidence": 0.2,
        "notes": "Sem sinal estrutural suficiente; requer revisão (human-in-the-loop).",
        "signals": _signal("fallback", "no_structural_signal"),
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
        signals=[Signal(**s) for s in payload.get("signals", [])],
        notes=payload.get("notes"),
    )


def classify(norm: NormalizedInput) -> AssetClassification:
    """Pure, offline classification: curated seed → structural rules.

    Always returns a record (``Indefinido`` when nothing matches). This is the
    deterministic core that the spec test set exercises with no network.
    """
    seed = lookup_seed(ticker=norm.ticker, cnpj=norm.cnpj, name_folded=norm.name_folded)
    if seed is not None:
        # Synthesize the curated_seed signal here (the frozen seed entry must not
        # be mutated): describe HOW the entry matched — by ticker, then CNPJ, then
        # name substrings. A copy keeps the seed payload immutable.
        if seed.ticker and norm.ticker == seed.ticker:
            evidence = f"ticker={norm.ticker}"
        elif seed.cnpj and norm.cnpj == seed.cnpj:
            evidence = f"cnpj={norm.cnpj}"
        else:
            evidence = f"name:{'+'.join(seed.name_substrings)}"
        payload = {**seed.payload}
        payload.setdefault("signals", [{"rule": "curated_seed", "evidence": evidence}])
        return _assemble(norm, payload, step="openfindata:curated")
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
        # Providers are best-effort enrichment: a flaky network/provider must not
        # nuke the deterministic core result. Isolate the failure, log it on the
        # cascade, and keep the last good classification.
        try:
            enriched = await provider(norm, result)
        except Exception as exc:  # any provider failure is non-fatal
            result.cascade.append(f"provider_error:{type(exc).__name__}")
            continue
        if enriched is not None:
            enriched.cascade = [*result.cascade, *enriched.cascade]
            result = enriched
    return result
