"""Resolver test set — the canonical cases from ``openfindata-mcp-spec.md``.

Every assertion is offline and deterministic: the curated seed + structural
rules settle each case with no network. The 8 spec cases plus the explicit
traps the ordering must defend.
"""

from __future__ import annotations

import asyncio

import pytest

from findata.resolver import classify, normalize, resolve_asset


def _resolve(**kw):
    return asyncio.run(resolve_asset(**kw))


# ── The spec test set (§Test set) ──────────────────────────────────


def test_ifra11_is_renda_fixa_inflation_etf_of_debentures():
    r = _resolve(ticker="IFRA11", name="FI ITAUINFRA CI")
    assert r.macro_class == "Renda Fixa"
    assert r.kind == "etf"
    assert r.subclasse == "Indexada à Inflação"
    assert r.underlying_nature == "debentures"
    assert r.debenture and r.debenture.incentivada_1243 is True
    assert r.tax.isento is True


def test_arbor_fic_fia_global_mandate_is_rv_exposure_internacional():
    # Geography is the exposure axis: a global equities FIA is RV by class.
    r = _resolve(name="ARBOR FIC FIA")
    assert r.macro_class == "Renda Variável"
    assert r.exposure == "Internacional"


def test_whg_global_fic_fia_ie_is_rv_exposure_internacional():
    r = _resolve(name="WHG GLOBAL EQUITY FIC FIA IE")
    assert r.macro_class == "Renda Variável"
    assert r.exposure == "Internacional"


def test_deb_petrobras_ipca_is_incentivada_isento_rf():
    r = _resolve(name="DEB PETROBRAS IPCA+")
    assert r.macro_class == "Renda Fixa"
    assert r.kind == "debenture"
    assert r.debenture and r.debenture.incentivada_1243 is True
    assert r.debenture.indexador == "IPCA+"
    assert r.tax.isento is True


def test_coe_is_estruturados_never_etf():
    r = _resolve(name="INVEST. ESTRUTURADOS COE BTG")
    assert r.macro_class == "Estruturados"
    assert r.kind == "coe"
    assert r.kind != "etf"


def test_credito_estruturado_name_trap_is_renda_fixa():
    # "Crédito Estruturado" (Warren/AMW) is RF credit, NOT Estruturados.
    r = _resolve(name="AMW CREDITO ESTRUTURADO FIC FIM CP")
    assert r.macro_class == "Renda Fixa"
    assert r.macro_class != "Estruturados"


def test_ivvb11_sp500_etf_is_renda_variavel_exposure_internacional():
    # Asset class is RV (spec); the international S&P 500 exposure lives on the
    # orthogonal `exposure` axis — B3 listing is domicile, not where the risk is.
    r = _resolve(ticker="IVVB11")
    assert r.macro_class == "Renda Variável"
    assert r.exposure == "Internacional"
    assert r.kind == "etf"
    assert r.underlying_nature == "acoes"


@pytest.mark.parametrize("ticker", ["HGLG11", "MXRF11"])
def test_fiis_are_renda_variavel_subclasse_fii(ticker):
    r = _resolve(ticker=ticker)
    assert r.macro_class == "Renda Variável"
    assert r.subclasse == "FII"
    assert r.kind == "fii"


# ── Trap regressions (spec §Armadilhas) ────────────────────────────


def test_acao_ticker_is_rv():
    r = _resolve(ticker="PETR4")
    assert r.macro_class == "Renda Variável"
    assert r.kind == "acao"
    assert r.exposure == "Brasil"


def test_bdr_is_rv_exposure_internacional():
    # BDR: RV by class, but the holder bears foreign/USD risk → Internacional.
    r = _resolve(ticker="AAPL34")
    assert r.macro_class == "Renda Variável"
    assert r.kind == "bdr"
    assert r.exposure == "Internacional"


def test_domestic_etf_is_brasil_exposure():
    r = _resolve(ticker="BOVA11")
    assert r.macro_class == "Renda Variável"
    assert r.exposure == "Brasil"


def test_internacional_funds_carry_internacional_exposure():
    # Asset class varies (RV here), but the exposure axis flags Internacional.
    for kw in ("ARBOR FIC FIA", "WHG GLOBAL EQUITY FIC FIA IE"):
        r = _resolve(name=kw)
        assert r.exposure == "Internacional"
        assert r.macro_class != "Indefinido"


def test_macro_class_has_no_internacional_value():
    # Geography is exposure-only; "Internacional" must never appear as macro.
    from findata.resolver import classify, normalize

    for ident in ("ARBOR FIC FIA", "WHG GLOBAL FIC FIA IE", "VINCI GLOBAL FIM IE"):
        r = classify(normalize(name=ident))
        assert r.macro_class != "Internacional"


def test_cra_cri_are_rf_isento():
    r = _resolve(name="CRA AGRONEGOCIO RAIZEN IPCA")
    assert r.macro_class == "Renda Fixa"
    assert r.kind == "cra"
    assert r.tax.isento is True


def test_tesouro_ipca_is_rf_inflation():
    r = _resolve(name="Tesouro IPCA+ 2035")
    assert r.macro_class == "Renda Fixa"
    assert r.kind == "tesouro"
    assert r.subclasse == "Indexada à Inflação"


def test_multimercado():
    r = _resolve(name="KAPITALO ZETA FIC FIM")
    assert r.macro_class == "Multimercado"


def test_fip_is_alternativos():
    r = _resolve(name="SPX FIP MULTIESTRATEGIA PARTICIPACOES")
    assert r.macro_class == "Alternativos"


# ── Adversarial-review regressions (token-collision traps) ─────────


def test_bare_ie_token_outside_fund_is_not_internacional():
    # "IE" must mean "Investimento no Exterior" only in a fund context.
    r = _resolve(name="COMPANHIA IE ENERGIA SA")
    assert r.macro_class != "Internacional"


def test_bare_lc_lf_tokens_do_not_force_renda_fixa():
    # Short tokens LC/LF used to misfire as bank paper.
    r = _resolve(name="FUNDO GLOBAL LC MASTER FIC FIM")
    assert r.kind != "cdb"


def test_alcione_substring_is_not_lci():
    # Substring "LCI" inside "ALCIONE" must not classify as LCI/LCA.
    r = _resolve(name="ALCIONE FUNDO DE ACOES")
    assert r.kind != "lci_lca"
    assert r.macro_class == "Renda Variável"


def test_arbor_credito_is_not_swept_into_global_equity_seed():
    # ARBOR brand without the FIA structure must not hit the curated global seed.
    r = _resolve(name="ARBOR CREDITO PRIVADO FIC FIM")
    assert r.macro_class != "Internacional"


def test_debenture_issuer_heuristic_keeps_confidence_below_short_circuit():
    # Heuristic incentivada must stay below the cascade short-circuit so a wired
    # provider can confirm the isento claim by ISIN.
    r = _resolve(name="DEB PETROBRAS IPCA+")
    assert r.debenture.incentivada_1243 is True  # spec still satisfied
    assert r.confidence < 0.9  # but flagged for confirmation


def test_unknown_is_indefinido_low_confidence():
    r = _resolve(name="????")
    assert r.macro_class == "Indefinido"
    assert r.confidence < 0.5


# ── Review-bot regressions (token collisions + Tesouro subclasse) ──


def test_ntnb_bond_code_maps_to_inflation_subclasse():
    # "NTN-B" carries no "IPCA" word, but it is an inflation-linked public bond.
    r = _resolve(name="NTN-B 2035")
    assert r.kind == "tesouro"
    assert r.subclasse == "Indexada à Inflação"


def test_lft_and_ltn_bond_codes_map_to_right_subclasse():
    assert _resolve(name="LFT 2029").subclasse == "Pós-fixada"
    assert _resolve(name="LTN 2028").subclasse == "Prefixada"


def test_tesouro_without_indexador_is_titulo_publico_not_credito_privado():
    # NTN-C (IGP-M) isn't mapped → generic public-bond subclasse, never credit.
    r = _resolve(name="NTN-C 2031")
    assert r.kind == "tesouro"
    assert r.subclasse == "Título Público"


def test_holding_company_participacoes_is_not_fip():
    # "Participações" in a company name (no fund context) must not be a FIP.
    r = _resolve(name="RANDON PARTICIPACOES SA")
    assert r.macro_class != "Alternativos"


def test_macro_trade_name_is_not_multimercado():
    r = _resolve(name="MACRO ATACADISTA DISTRIBUIDORA SA")
    assert r.macro_class != "Multimercado"


def test_bare_acoes_keyword_without_fund_context_is_not_fia():
    r = _resolve(name="EMPRESA BRASILEIRA ACOES ON SA")
    assert not (r.kind == "fundo" and r.subclasse == "Ações")


# ── Fiscal-certainty axis (lei_12431_status / isento_status) ───────


def test_deb_petrobras_heuristic_carries_candidate_certainty():
    r = _resolve(name="DEB PETROBRAS IPCA+")
    assert r.debenture and r.debenture.incentivada_1243 is True
    assert r.debenture.lei_12431_status == "candidate"
    assert r.tax.isento is True
    assert r.tax.isento_status == "candidate_exempt"


def test_ifra11_carries_confirmed_certainty():
    r = _resolve(ticker="IFRA11", name="FI ITAUINFRA CI")
    assert r.debenture and r.debenture.lei_12431_status == "confirmed"
    assert r.tax.isento_status == "confirmed_exempt"


def test_explicit_infra_debenture_is_confirmed():
    r = _resolve(name="DEB INFRA ENERGIA INCENTIVADA IPCA+")
    assert r.debenture and r.debenture.lei_12431_status == "confirmed"


def test_cra_isento_status_is_confirmed_exempt():
    r = _resolve(name="CRA AGRONEGOCIO RAIZEN IPCA")
    assert r.tax.isento_status == "confirmed_exempt"


def test_plain_non_infra_debenture_is_not_applicable():
    r = _resolve(name="DEB LOJAS RENNER CDI+")
    assert r.debenture and r.debenture.incentivada_1243 is None
    assert r.debenture.lei_12431_status == "not_applicable"
    assert r.tax.isento_status == "unknown"


# ── Contract / determinism ─────────────────────────────────────────


def test_output_carries_audit_fields():
    r = _resolve(ticker="IFRA11")
    assert r.source == "openfindata"
    assert r.cascade == ["openfindata:curated"]
    assert 0.0 <= r.confidence <= 1.0
    assert r.as_of  # YYYY-MM-DD


def test_classify_is_deterministic():
    norm = normalize(ticker="IVVB11")
    a, b = classify(norm), classify(norm)
    assert a.model_dump(exclude={"as_of"}) == b.model_dump(exclude={"as_of"})


def test_bare_ticker_passed_as_name_is_promoted():
    # The consolidator often only has the statement label.
    r = _resolve(name="IVVB11")
    assert r.identifier_resolved.ticker == "IVVB11"
    assert r.macro_class == "Renda Variável"


def test_provider_chain_enriches_only_when_weak():
    calls = {"n": 0}

    async def fake_provider(norm, current):
        calls["n"] += 1
        return None  # noqa: RET501 — explicit "pass" signal in the provider protocol

    # Confident core result → provider must be skipped.
    asyncio.run(resolve_asset(ticker="IFRA11", providers=[fake_provider]))
    assert calls["n"] == 0

    # Weak result → provider is consulted.
    asyncio.run(resolve_asset(name="????", providers=[fake_provider]))
    assert calls["n"] == 1


# ── Structured signals trail ───────────────────────────────────────


def test_curated_seed_emits_curated_signal():
    r = _resolve(ticker="IFRA11")
    assert r.signals
    assert r.signals[0].rule == "curated_seed"
    assert "IFRA11" in r.signals[0].evidence


def test_debenture_signal_records_evidence_and_detail():
    r = _resolve(name="DEB PETROBRAS IPCA+")
    deb = [s for s in r.signals if s.rule == "debenture"]
    assert deb
    assert deb[0].evidence == "DEB"
    assert deb[0].detail is not None
    assert "basis=" in deb[0].detail
    assert "IPCA+" in deb[0].detail


def test_coe_signal_fires():
    r = _resolve(name="INVEST. ESTRUTURADOS COE BTG")
    assert any(s.rule == "coe" for s in r.signals)


def test_credito_estruturado_trap_signal_carries_phrase():
    r = _resolve(name="AMW CREDITO ESTRUTURADO FIC FIM CP")
    trap = [s for s in r.signals if s.rule == "credito_estruturado_trap"]
    assert trap
    assert "CREDITO ESTRUTURADO" in trap[0].evidence


@pytest.mark.parametrize(
    "ident",
    ["PETR4", "HGLG11", "Tesouro IPCA+ 2035", "KAPITALO ZETA FIC FIM"],
)
def test_every_result_carries_at_least_one_signal(ident):
    r = classify(normalize(name=ident))
    assert len(r.signals) >= 1
