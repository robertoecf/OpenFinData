"""CLI interface for findata-br."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import date
from typing import Any, Literal, TypeVar, cast

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from findata import __version__
from findata.banner import render_animated_banner, render_startup_panel
from findata.sources.bcb import focus, ptax, sgs

app = typer.Typer(
    name="findata",
    help="Open-source Brazilian financial data CLI",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

_console = Console()


_R = TypeVar("_R")


def _run(coro: Coroutine[Any, Any, _R]) -> _R:
    """Run an async function from a sync CLI context, preserving its return type."""
    return asyncio.run(coro)


def _fmt(val: float | None, spec: str = ".2f") -> str:
    """Format a nullable float, returning '-' when None."""
    return format(val, spec) if val is not None else "-"


def _version_callback(value: bool) -> None:
    """Print the package version and exit when the eager flag is set."""
    if value:
        rprint(f"findata-br [bold]{__version__}[/bold]")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        None,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """findata-br — Brazilian financial data CLI."""
    _ = version  # handled by the eager callback above


# ── Banner ─────────────────────────────────────────────────────────


@app.command()
def banner() -> None:
    """Print the animated findata-br banner."""
    render_animated_banner(_console)


# ── BCB commands ───────────────────────────────────────────────────

bcb_app = typer.Typer(help="Banco Central do Brasil data", no_args_is_help=True)
app.add_typer(bcb_app, name="bcb")


@bcb_app.command("series")
def bcb_series() -> None:
    """List all available BCB time series."""
    table = Table(title="BCB Series Catalog")
    table.add_column("Name", style="cyan")
    table.add_column("Code", style="green")
    table.add_column("Description")
    table.add_column("Unit")
    table.add_column("Freq")

    for name, info in sgs.SERIES_CATALOG.items():
        table.add_row(name, str(info["code"]), info["name"], info["unit"], info["freq"])

    rprint(table)


@bcb_app.command("get")
def bcb_get(
    name: str = typer.Argument(help="Series name (selic, ipca, dolar_ptax, etc.)"),
    n: int = typer.Option(10, "--last", "-n", help="Number of recent values"),
) -> None:
    """Get recent values for a BCB time series."""
    try:
        data = _run(sgs.get_series_by_name(name, n))
    except ValueError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title=f"BCB: {name}")
    table.add_column("Date", style="cyan")
    table.add_column("Value", style="green", justify="right")
    for point in data:
        table.add_row(point.data, f"{point.valor:.4f}")
    rprint(table)


@bcb_app.command("ptax")
def bcb_ptax(
    d: str | None = typer.Option(None, "--date", "-d", help="Date (YYYY-MM-DD)"),
) -> None:
    """Get USD/BRL PTAX quote."""
    dt = date.fromisoformat(d) if d else None
    data = _run(ptax.get_ptax_usd(dt))
    if not data:
        rprint("[yellow]No data (weekend/holiday?)[/yellow]")
        return
    for q in data:
        rprint(
            f"[green]Compra:[/green] {q.cotacao_compra:.4f}  "
            f"[green]Venda:[/green] {q.cotacao_venda:.4f}  "
            f"({q.data_hora_cotacao})"
        )


@bcb_app.command("focus")
def bcb_focus(
    indicator: str = typer.Option("IPCA", "--indicator", "-i"),
    top: int = typer.Option(10, "--top", "-n"),
) -> None:
    """Get Focus market expectations (annual)."""
    try:
        data = _run(focus.get_focus_annual(indicator, top))
    except ValueError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title=f"Focus: {indicator} (annual)")
    table.add_column("Date", style="cyan")
    table.add_column("Reference", style="blue")
    table.add_column("Median", style="green", justify="right")
    table.add_column("Mean", justify="right")
    table.add_column("Min", justify="right")
    table.add_column("Max", justify="right")

    for e in data:
        table.add_row(
            e.data,
            e.data_referencia,
            _fmt(e.mediana),
            _fmt(e.media),
            _fmt(e.minimo),
            _fmt(e.maximo),
        )

    rprint(table)


# ── B3 commands ────────────────────────────────────────────────────

b3_app = typer.Typer(help="B3 stock exchange data (requires [b3] extra)", no_args_is_help=True)
app.add_typer(b3_app, name="b3")


@b3_app.command("quote")
def b3_quote(
    ticker: str = typer.Argument(help="B3 ticker (e.g., PETR4, VALE3)"),
) -> None:
    """Get current stock quote."""
    from findata.sources.b3 import quotes

    q = _run(quotes.get_quote(ticker))
    rprint(f"[bold]{q.ticker}[/bold] — {q.nome or 'N/A'}")
    if q.preco is not None:
        rprint(f"  [green]Preco:[/green] R$ {q.preco:.2f}")
    if q.variacao_dia is not None:
        rprint(f"  [green]Variacao:[/green] {q.variacao_dia:+.2f}%")
    if q.abertura is not None:
        rprint(f"  Abertura: {q.abertura:.2f}")
    if q.volume is not None:
        rprint(f"  Volume: {q.volume:,}")
    if q.setor:
        rprint(f"  Setor: {q.setor}")


@b3_app.command("history")
def b3_history(
    ticker: str = typer.Argument(help="B3 ticker"),
    period: str = typer.Option("1mo", "--period", "-p"),
) -> None:
    """Get stock price history."""
    from findata.sources.b3 import quotes

    data = _run(quotes.get_history(ticker, period))
    table = Table(title=f"{ticker.upper()} — {period}")
    table.add_column("Date", style="cyan")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right", style="green")
    table.add_column("Low", justify="right", style="red")
    table.add_column("Close", justify="right", style="bold")
    table.add_column("Volume", justify="right")

    for p in data:
        table.add_row(
            p.date,
            f"{p.open:.2f}",
            f"{p.high:.2f}",
            f"{p.low:.2f}",
            f"{p.close:.2f}",
            f"{p.volume:,}",
        )

    rprint(table)


@b3_app.command("cotahist")
def b3_cotahist(
    ticker: str = typer.Argument(help="B3 ticker (e.g. PETR4)"),
    year: int = typer.Option(..., "--year", "-y"),
    month: int | None = typer.Option(None, "--month", "-m"),
    day: int | None = typer.Option(None, "--day", "-d"),
) -> None:
    """B3 COTAHIST — official daily history. With --month or --day for finer slices."""
    from findata.sources.b3 import (
        get_cotahist_day,
        get_cotahist_month,
        get_cotahist_year,
    )

    if day is not None and month is not None:
        rows = _run(get_cotahist_day(year, month, day, ticker=ticker))
        title = f"{ticker.upper()} — {year}-{month:02d}-{day:02d}"
    elif month is not None:
        rows = _run(get_cotahist_month(year, month, ticker=ticker))
        title = f"{ticker.upper()} — {year}-{month:02d}"
    else:
        rows = _run(get_cotahist_year(year, ticker=ticker))
        title = f"{ticker.upper()} — {year}"

    if not rows:
        rprint(f"[yellow]No COTAHIST data for {ticker} in {title.split('—')[1].strip()}.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Date", style="cyan")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right", style="green")
    table.add_column("Low", justify="right", style="red")
    table.add_column("Close", justify="right", style="bold")
    table.add_column("Vol R$", justify="right")
    max_shown = 60
    for r in rows[-max_shown:]:
        table.add_row(
            r.data,
            f"{r.preco_abertura:.2f}",
            f"{r.preco_maximo:.2f}",
            f"{r.preco_minimo:.2f}",
            f"{r.preco_ultimo:.2f}",
            f"{r.volume_financeiro:,.0f}",
        )
    rprint(table)
    if len(rows) > max_shown:
        rprint(f"[dim](showing last {max_shown} of {len(rows)} sessions)[/dim]")


@b3_app.command("index")
def b3_index(
    symbol: str = typer.Argument(help="Index symbol (e.g. IBOV, IBXL, SMLL, IDIV, IFIX)"),
) -> None:
    """Show current theoretical portfolio of a B3 index."""
    from findata.sources.b3 import get_index_portfolio

    p = _run(get_index_portfolio(symbol))
    if not p.componentes:
        rprint(f"[yellow]No data for index {symbol}.[/yellow]")
        return
    rprint(f"[bold]{p.nome}[/bold]  ({p.indice})  ·  {p.data}  ·  {len(p.componentes)} ativos")
    table = Table(title=f"{p.indice} — composição teórica")
    table.add_column("Ticker", style="cyan")
    table.add_column("Ativo")
    table.add_column("Classe", style="dim")
    table.add_column("Peso %", justify="right", style="bold")
    table.add_column("Qtd Teórica", justify="right")
    for c in p.componentes:
        table.add_row(
            c.ticker,
            c.nome_ativo,
            c.classe,
            f"{c.peso_pct:.3f}" if c.peso_pct is not None else "-",
            f"{c.qtd_teorica:,}" if c.qtd_teorica is not None else "-",
        )
    rprint(table)


# ── Tesouro commands ───────────────────────────────────────────────

tesouro_app = typer.Typer(help="Tesouro Direto treasury bonds", no_args_is_help=True)
app.add_typer(tesouro_app, name="tesouro")


@tesouro_app.command("search")
def tesouro_search(
    query: str = typer.Argument(help="Search query (e.g., 'IPCA+', 'Selic')"),
) -> None:
    """Search available treasury bonds."""
    from findata.sources.tesouro import search_bonds

    titles = _run(search_bonds(query))
    if not titles:
        rprint("[yellow]No bonds matched.[/yellow]")
        return
    for t in titles:
        rprint(f"  {t}")


@tesouro_app.command("history")
def tesouro_history(
    titulo: str = typer.Argument(help="Bond name"),
    n: int = typer.Option(20, "--last", "-n"),
) -> None:
    """Get price/rate history for a treasury bond."""
    from findata.sources.tesouro import get_bond_history

    data = _run(get_bond_history(titulo))
    if not data:
        rprint(f"[yellow]No history for '{titulo}'.[/yellow]")
        return
    table = Table(title=titulo)
    table.add_column("Date", style="cyan")
    table.add_column("Buy Rate %", style="green", justify="right")
    table.add_column("Sell Rate %", justify="right")
    table.add_column("Buy PU R$", style="green", justify="right")
    table.add_column("Sell PU R$", justify="right")

    for b in data[-n:]:
        table.add_row(
            b.dt_base,
            _fmt(b.taxa_compra, ".4f"),
            _fmt(b.taxa_venda, ".4f"),
            _fmt(b.pu_compra),
            _fmt(b.pu_venda),
        )

    rprint(table)


@tesouro_app.command("rreo")
def tesouro_rreo(
    cod_ibge: int = typer.Argument(help="IBGE code (1=União, see siconfi.entes)"),
    year: int = typer.Option(..., "--year", "-y"),
    bimestre: int = typer.Option(..., "--bimestre", "-b", min=1, max=6),
    anexo: str | None = typer.Option(None, "--anexo", "-a"),
) -> None:
    """RREO — Relatório Resumido de Execução Orçamentária."""
    from findata.sources.tesouro import get_rreo

    rows = _run(get_rreo(year, bimestre, cod_ibge, anexo=anexo))
    if not rows:
        rprint(f"[yellow]No RREO for IBGE={cod_ibge} {year}/B{bimestre}.[/yellow]")
        return
    table = Table(title=f"RREO {rows[0].instituicao} {year}/B{bimestre}")
    table.add_column("Anexo", style="cyan")
    table.add_column("Conta")
    table.add_column("Coluna", style="dim")
    table.add_column("Valor R$", justify="right")
    max_shown = 80
    for r in rows[:max_shown]:
        valor = f"{r.valor:,.0f}" if r.valor is not None else "-"
        table.add_row(r.anexo, r.conta[:50], r.coluna, valor)
    rprint(table)
    if len(rows) > max_shown:
        rprint(f"[dim](showing {max_shown} of {len(rows)} rows — use --anexo to slice)[/dim]")


@tesouro_app.command("entes")
def tesouro_entes(
    uf: str | None = typer.Option(None, "--uf"),
) -> None:
    """List SICONFI federation entities (filter by UF optional)."""
    from findata.sources.tesouro import get_entes

    entes = _run(get_entes())
    if uf:
        entes = [e for e in entes if e.uf == uf.upper()]
    table = Table(title=f"SICONFI entities ({len(entes)})")
    table.add_column("IBGE", style="cyan", justify="right")
    table.add_column("UF")
    table.add_column("Esfera", style="dim")
    table.add_column("Instituição")
    table.add_column("População", justify="right")
    max_shown = 60
    for e in entes[:max_shown]:
        pop = f"{e.populacao:,}" if e.populacao else "-"
        table.add_row(str(e.cod_ibge), e.uf, e.esfera, e.instituicao[:50], pop)
    rprint(table)
    if len(entes) > max_shown:
        rprint(f"[dim](showing {max_shown} of {len(entes)} — filter with --uf)[/dim]")


# ── Receita commands ──────────────────────────────────────────────

receita_app = typer.Typer(help="Receita Federal — federal-tax revenue", no_args_is_help=True)
app.add_typer(receita_app, name="receita")


@receita_app.command("arrecadacao")
def receita_arrecadacao(
    year: int = typer.Option(..., "--year", "-y"),
    month: int | None = typer.Option(None, "--month", "-m", min=1, max=12),
    uf: str | None = typer.Option(None, "--uf"),
    tributo: str | None = typer.Option(None, "--tributo", "-t"),
) -> None:
    """Federal-tax revenue by year/month/UF/tributo."""
    from findata.sources.receita import get_arrecadacao

    rows = _run(get_arrecadacao(year=year, month=month, uf=uf, tributo=tributo))
    if not rows:
        rprint("[yellow]No data matched filter.[/yellow]")
        return
    table = Table(title=f"Receita arrecadação {year}{'-' + str(month).zfill(2) if month else ''}")
    table.add_column("Ano-Mês", style="cyan")
    table.add_column("UF")
    table.add_column("Tributo")
    table.add_column("Valor R$", justify="right", style="bold")
    max_shown = 40
    for r in rows[:max_shown]:
        valor = f"{r.valor:,.0f}" if r.valor is not None else "-"
        table.add_row(f"{r.ano}-{r.mes:02d}", r.uf, r.tributo[:50], valor)
    rprint(table)
    if len(rows) > max_shown:
        rprint(f"[dim](showing {max_shown} of {len(rows)} — narrow with --tributo)[/dim]")


# ── ANEEL commands ────────────────────────────────────────────────

aneel_app = typer.Typer(help="ANEEL — energy-auction results", no_args_is_help=True)
app.add_typer(aneel_app, name="aneel")


@aneel_app.command("leiloes")
def aneel_leiloes(
    year: int | None = typer.Option(None, "--year", "-y"),
    fonte: str | None = typer.Option(None, "--fonte", "-f"),
    uf: str | None = typer.Option(None, "--uf"),
    tipo: str = typer.Option("geracao", "--tipo", "-t", help="geracao | transmissao"),
) -> None:
    """List ANEEL energy-auction results."""
    from findata.sources.aneel import get_aneel_leiloes_geracao, get_aneel_leiloes_transmissao

    if tipo == "transmissao":
        rows = _run(get_aneel_leiloes_transmissao(year=year, uf=uf))
        if not rows:
            rprint("[yellow]No transmission auctions matched.[/yellow]")
            return
        table = Table(title=f"ANEEL leilões transmissão{f' {year}' if year else ''}")
        table.add_column("Ano", style="cyan", justify="right")
        table.add_column("Empreendimento")
        table.add_column("UF", style="dim")
        table.add_column("Km", justify="right")
        table.add_column("RAP R$/ano", justify="right", style="bold")
        table.add_column("Vencedor")
        max_shown = 40
        for r in rows[-max_shown:]:
            km = f"{r.extensao_linha_km:,.0f}" if r.extensao_linha_km else "-"
            rap = f"{r.rap_vencedor_brl:,.0f}" if r.rap_vencedor_brl else "-"
            table.add_row(
                str(r.ano_leilao or "-"),
                (r.nome_empreendimento or "")[:50],
                r.uf or "-",
                km,
                rap,
                (r.nome_vencedor or "")[:30],
            )
        rprint(table)
    else:
        rows_g = _run(get_aneel_leiloes_geracao(year=year, fonte=fonte, uf=uf))
        if not rows_g:
            rprint("[yellow]No generation auctions matched.[/yellow]")
            return
        table = Table(title=f"ANEEL leilões geração{f' {year}' if year else ''}")
        table.add_column("Ano", style="cyan", justify="right")
        table.add_column("Empreendimento")
        table.add_column("Fonte")
        table.add_column("MW", justify="right")
        table.add_column("Preço R$/MWh", justify="right", style="bold")
        table.add_column("Vencedor")
        max_shown = 40
        for g in rows_g[-max_shown:]:
            mw = f"{g.potencia_instalada_mw:,.0f}" if g.potencia_instalada_mw else "-"
            preco = f"{g.preco_leilao_brl_mwh:.2f}" if g.preco_leilao_brl_mwh else "-"
            table.add_row(
                str(g.ano_leilao or "-"),
                (g.nome_empreendimento or "")[:35],
                (g.fonte_energia or "")[:15],
                mw,
                preco,
                (g.empresa_vencedora or "")[:25],
            )
        rprint(table)


# ── SUSEP commands ────────────────────────────────────────────────

susep_app = typer.Typer(help="SUSEP — supervised insurance entities", no_args_is_help=True)
app.add_typer(susep_app, name="susep")


@susep_app.command("search")
def susep_search(
    query: str = typer.Argument(help="Substring of entity name"),
) -> None:
    """Search SUSEP-supervised entities by name."""
    from findata.sources.susep import search_susep_empresa

    results = _run(search_susep_empresa(query))
    if not results:
        rprint("[yellow]No entities matched.[/yellow]")
        return
    table = Table(title=f"SUSEP empresas matching '{query}'")
    table.add_column("FIP", style="cyan", justify="right")
    table.add_column("CNPJ")
    table.add_column("Nome")
    max_shown = 50
    for e in results[:max_shown]:
        table.add_row(e.codigo_fip, e.cnpj, e.nome)
    rprint(table)
    if len(results) > max_shown:
        rprint(f"[dim](showing {max_shown} of {len(results)})[/dim]")


# ── Registry commands (cross-source CNPJ resolver) ─────────────────

registry_app = typer.Typer(
    help="Registry — cross-source CNPJ / ticker / name resolver",
    no_args_is_help=True,
)
app.add_typer(registry_app, name="registry")


@registry_app.command("lookup")
def registry_lookup(
    query: str = typer.Argument(
        help="CNPJ (with or without mask), B3 ticker, CVM code, FIP code, or name"
    ),
    limit: int = typer.Option(20, "--limit", "-n", min=1, max=100),
) -> None:
    """Resolve a CNPJ-, ticker-, or name-shaped query against the embedded registry.

    Examples:

        findata registry lookup 33000167000101
        findata registry lookup PETR4
        findata registry lookup "porto seguro"
        findata registry lookup "33.000.167/0001-01"
    """
    from findata.registry import lookup

    result = _run(lookup(query, limit=limit))
    if result.total == 0:
        rprint(
            "[yellow]No entities matched.[/yellow] "
            "Try a name fragment, a B3 ticker (PETR4), or a clean 14-digit CNPJ."
        )
        return
    table = Table(title=f"Registry hits for '{query}' ({result.total} of ≤{limit})")
    table.add_column("Rank", style="dim", justify="right")
    table.add_column("Kind", style="cyan")
    table.add_column("CNPJ", style="green")
    table.add_column("Nome")
    table.add_column("Tickers", style="magenta")
    for e in result.entities:
        rank_str = f"{e.rank:.2f}" if e.rank is not None else "-"
        tickers = ", ".join(e.tickers) if e.tickers else "-"
        table.add_row(rank_str, e.kind, e.cnpj or "-", e.nome[:60], tickers)
    rprint(table)
    rprint(
        "[dim]rank: more negative = more confident match. "
        "< -5 ≈ exact CNPJ/ticker/code; > -2 ≈ fuzzy name.[/dim]"
    )


@registry_app.command("meta")
def registry_meta_cmd() -> None:
    """Show build metadata of the embedded registry."""
    from findata.registry import get_meta

    meta = _run(get_meta())
    table = Table(title="Registry metadata")
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    for k, v in meta.items():
        table.add_row(k, v)
    rprint(table)


# ── IBGE commands ──────────────────────────────────────────────────

ibge_app = typer.Typer(help="IBGE economic indicators", no_args_is_help=True)
app.add_typer(ibge_app, name="ibge")


@ibge_app.command("ipca")
def ibge_ipca(
    periods: int = typer.Option(6, "--periods", "-n"),
) -> None:
    """Get IPCA breakdown by major groups."""
    from findata.sources.ibge import get_ipca_breakdown

    data = _run(get_ipca_breakdown(periods))
    table = Table(title="IPCA Breakdown by Group")
    table.add_column("Period", style="cyan")
    table.add_column("Group")
    table.add_column("Value %", style="green", justify="right")

    for d in data:
        table.add_row(d.periodo, d.classificacao or "Geral", _fmt(d.valor))

    rprint(table)


# ── ANBIMA commands (public file downloads, no auth) ─────────────

anbima_app = typer.Typer(
    help="ANBIMA — IMA, ETTJ, debêntures (public file downloads)",
    no_args_is_help=True,
)
app.add_typer(anbima_app, name="anbima")


@anbima_app.command("ima")
def anbima_ima(
    family: str | None = typer.Option(None, "--family", "-i"),
) -> None:
    """Latest IMA snapshot — every sub-index for the most recent published day."""
    from findata.sources.anbima import IMAFamily, get_ima

    fam = IMAFamily(family) if family else None
    data = _run(get_ima(fam))
    if not data:
        rprint(f"[yellow]No IMA data for {family or 'any family'}.[/yellow]")
        return
    table = Table(title=f"ANBIMA: IMA ({family or 'all families'})")
    table.add_column("Index", style="blue")
    table.add_column("Date", style="cyan")
    table.add_column("Number Index", style="green", justify="right")
    table.add_column("Day %", justify="right")
    table.add_column("Month %", justify="right")
    table.add_column("Year %", justify="right")
    table.add_column("12m %", justify="right")
    table.add_column("Duration (du)", justify="right")
    for p in sorted(data, key=lambda r: r.indice):
        table.add_row(
            p.indice,
            p.data_referencia,
            _fmt(p.numero_indice, ".4f"),
            _fmt(p.variacao_dia_pct, "+.4f"),
            _fmt(p.variacao_mes_pct, "+.4f"),
            _fmt(p.variacao_ano_pct, "+.4f"),
            _fmt(p.variacao_12m_pct, "+.4f"),
            _fmt(p.duration_du, ".0f"),
        )
    rprint(table)


@anbima_app.command("ettj")
def anbima_ettj(d: str | None = typer.Option(None, "--date", "-d")) -> None:
    """Yield curve (zero coupon) for a reference date."""
    from findata.sources.anbima import get_ettj

    dt = date.fromisoformat(d) if d else None
    data = _run(get_ettj(dt))
    if not data:
        rprint(f"[yellow]No ETTJ data for {dt or 'today'}.[/yellow]")
        return
    table = Table(title=f"ANBIMA: ETTJ ({dt or 'today'})")
    table.add_column("Vértice (du)", style="cyan", justify="right")
    table.add_column("Pré %", style="green", justify="right")
    table.add_column("IPCA %", justify="right")
    table.add_column("Inflação Implícita %", justify="right")
    for p in data:
        table.add_row(
            str(p.vertice_du),
            _fmt(p.taxa_pre_pct, ".4f"),
            _fmt(p.taxa_ipca_pct, ".4f"),
            _fmt(p.inflacao_implicita_pct, ".4f"),
        )
    rprint(table)


@anbima_app.command("debentures")
def anbima_debentures(
    d: str | None = typer.Option(None, "--date", "-d"),
    emissor: str | None = typer.Option(None, "--emissor", "-e"),
    n: int = typer.Option(50, "--last", "-n"),
) -> None:
    """Daily secondary-market quotes for outstanding debentures."""
    from findata.sources.anbima import get_debentures

    dt = date.fromisoformat(d) if d else None
    rows = _run(get_debentures(dt))
    if emissor:
        needle = emissor.upper()
        rows = [r for r in rows if needle in r.emissor.upper()]
    rows = rows[:n]
    if not rows:
        rprint("[yellow]No debenture quotes matched.[/yellow]")
        return
    table = Table(title=f"ANBIMA: Debêntures ({dt or 'today'})")
    table.add_column("Code", style="cyan")
    table.add_column("Issuer")
    table.add_column("Maturity", style="blue")
    table.add_column("Rate Indicative %", style="green", justify="right")
    table.add_column("PU R$", justify="right")
    table.add_column("Duration (du)", justify="right")
    for r in rows:
        table.add_row(
            r.codigo,
            r.emissor[:40],
            r.repactuacao_vencimento,
            _fmt(r.taxa_indicativa_pct, ".4f"),
            _fmt(r.pu, ".2f"),
            _fmt(r.duration_du, ".0f"),
        )
    rprint(table)


# ── IPEA commands ──────────────────────────────────────────────────

ipea_app = typer.Typer(help="IPEA Data — macro series catalog", no_args_is_help=True)
app.add_typer(ipea_app, name="ipea")


@ipea_app.command("catalog")
def ipea_catalog() -> None:
    """List the curated IPEA catalog."""
    from findata.sources.ipea import series as ipea_series

    table = Table(title="IPEA Curated Catalog")
    table.add_column("Name", style="cyan")
    table.add_column("SERCODIGO", style="green")
    table.add_column("Description")
    table.add_column("Unit")
    table.add_column("Freq")
    for name, info in ipea_series.IPEA_CATALOG.items():
        table.add_row(
            name,
            info["code"],
            info["description"],
            info["unidade"],
            info["periodicidade"],
        )
    rprint(table)


@ipea_app.command("get")
def ipea_get(
    sercodigo: str = typer.Argument(help="IPEA series code (e.g., BM12_TJOVER12)"),
    n: int = typer.Option(10, "--last", "-n", help="Number of recent values"),
) -> None:
    """Fetch values for an IPEA series."""
    from findata.sources.ipea import series as ipea_series

    data = _run(ipea_series.get_series_values(sercodigo, top=n))
    if not data:
        rprint(f"[yellow]No values for '{sercodigo}'.[/yellow]")
        return
    table = Table(title=f"IPEA: {sercodigo}")
    table.add_column("Date", style="cyan")
    table.add_column("Value", style="green", justify="right")
    for point in data:
        table.add_row(point.data[:10], _fmt(point.valor, ".4f"))
    rprint(table)


@ipea_app.command("search")
def ipea_search(
    query: str = typer.Argument(help="Free-text search"),
    top: int = typer.Option(20, "--top", "-n"),
) -> None:
    """Search the IPEA series catalog (~8k series)."""
    from findata.sources.ipea import series as ipea_series

    results = _run(ipea_series.search_series(query, top=top))
    if not results:
        rprint("[yellow]No series matched.[/yellow]")
        return
    table = Table(title=f"IPEA search: '{query}'")
    table.add_column("SERCODIGO", style="cyan")
    table.add_column("Name")
    table.add_column("Periodicidade", style="green")
    table.add_column("Fonte")
    for m in results:
        table.add_row(
            m.sercodigo,
            m.sernome[:60],
            m.serperiodicidade or "-",
            m.serfonte or "-",
        )
    rprint(table)


# ── Open Finance Brasil commands (public Track A only) ─────────────

openfinance_app = typer.Typer(
    help="Open Finance Brasil — public Directory and indicator Portal",
    no_args_is_help=True,
)
app.add_typer(openfinance_app, name="openfinance")


@openfinance_app.command("resources")
def openfinance_resources(
    environment: str = typer.Option("production", "--env", help="production | sandbox"),
) -> None:
    """List public Open Finance resources supported by findata-br."""
    from findata.sources.openfinance import directory as of_dir

    env = _openfinance_env(environment)
    table = Table(title=f"Open Finance public resources ({env})")
    table.add_column("Name", style="cyan")
    table.add_column("URL")
    table.add_column("Cache", justify="right")
    table.add_column("Description")
    for resource in of_dir.public_resources(env):
        table.add_row(
            resource.name,
            resource.url,
            f"{resource.cache_ttl_seconds}s",
            resource.description[:70],
        )
    rprint(table)


@openfinance_app.command("participants")
def openfinance_participants(
    role: str | None = typer.Option(None, "--role", help="Filter by role, e.g. DADOS"),
    api_family: str | None = typer.Option(None, "--api-family", help="API family substring"),
    query: str | None = typer.Option(None, "--query", "-q", help="Name/CNPJ substring"),
    status: str | None = typer.Option(
        "Active",
        "--status",
        help="Participant status; empty for all",
    ),
    limit: int = typer.Option(30, "--limit", "-n", min=1, max=1000),
    environment: str = typer.Option("production", "--env", help="production | sandbox"),
) -> None:
    """List Open Finance participants from the public Directory."""
    from findata.sources.openfinance import directory as of_dir

    env = _openfinance_env(environment)
    raw = _run(of_dir.get_participants(env))
    filtered = of_dir.filter_participants(
        raw,
        role=role,
        status=status or None,
        api_family=api_family,
        query=query,
    )
    rows = of_dir.summarise_participants(filtered[:limit])
    table = Table(title=f"Open Finance participants ({env})")
    table.add_column("OrganisationId", style="cyan")
    table.add_column("Name")
    table.add_column("CNPJ")
    table.add_column("Roles")
    table.add_column("AS", justify="right")
    table.add_column("Resources", justify="right")
    for row in rows:
        table.add_row(
            row.organisation_id[:8],
            (row.organisation_name or row.registered_name or "-")[:45],
            row.registration_number or "-",
            ",".join(row.roles) or "-",
            str(row.authorization_servers),
            str(row.api_resources),
        )
    rprint(table)
    if len(filtered) > limit:
        rprint(f"[dim](showing {limit} of {len(filtered)})[/dim]")


@openfinance_app.command("endpoints")
def openfinance_endpoints(
    api_family: str | None = typer.Option(None, "--api-family", help="API family substring"),
    status: str | None = typer.Option(
        "Active",
        "--status",
        help="Participant status; empty for all",
    ),
    limit: int = typer.Option(40, "--limit", "-n", min=1, max=5000),
    environment: str = typer.Option("production", "--env", help="production | sandbox"),
) -> None:
    """List API endpoints advertised by public /participants metadata."""
    from findata.sources.openfinance import directory as of_dir

    env = _openfinance_env(environment)
    raw = _run(of_dir.get_participants(env))
    rows = of_dir.flatten_api_endpoints(raw, api_family=api_family, status=status or None)
    table = Table(title=f"Open Finance API endpoints ({env})")
    table.add_column("Org", style="cyan")
    table.add_column("Brand")
    table.add_column("Family", style="green")
    table.add_column("Version")
    table.add_column("Endpoint")
    for row in rows[:limit]:
        table.add_row(
            row.organisation_id[:8],
            (row.authorisation_server_name or row.organisation_name or "-")[:30],
            (row.api_family_type or "-")[:35],
            row.api_version or "-",
            row.api_endpoint[:80],
        )
    rprint(table)
    if len(rows) > limit:
        rprint(f"[dim](showing {limit} of {len(rows)})[/dim]")


@openfinance_app.command("datasets")
def openfinance_datasets() -> None:
    """List public datasets from the Open Finance data Portal."""
    from findata.sources.openfinance import portal as of_portal

    table = Table(title="Open Finance Portal datasets")
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Description")
    for dataset in of_portal.list_datasets():
        table.add_row(dataset.slug, dataset.title, dataset.description[:70])
    rprint(table)


@openfinance_app.command("files")
def openfinance_files(
    slug: str = typer.Argument(help="Dataset slug from `findata openfinance datasets`"),
    page: int = typer.Option(1, "--page", min=1, max=20),
) -> None:
    """List downloadable files for a public Portal dataset."""
    from findata.sources.openfinance import portal as of_portal

    rows = _run(of_portal.get_dataset_files(slug, page=page))
    if not rows:
        rprint("[yellow]No files found on that dataset page.[/yellow]")
        return
    table = Table(title=f"Open Finance files: {slug} (page {page})")
    table.add_column("ID", style="cyan")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Range")
    for row in rows:
        table.add_row(
            row.download_id,
            row.file_type or "-",
            row.title,
            row.date_range or "-",
        )
    rprint(table)


_OpenFinanceEnvironment = Literal["production", "sandbox"]


def _openfinance_env(value: str) -> _OpenFinanceEnvironment:
    """Validate an Open Finance Directory environment CLI option."""
    if value not in ("production", "sandbox"):
        rprint("[red]Error:[/red] --env must be 'production' or 'sandbox'")
        raise typer.Exit(code=1)
    return cast(_OpenFinanceEnvironment, value)


# ── CVM commands ───────────────────────────────────────────────────

cvm_app = typer.Typer(help="CVM — companies and funds", no_args_is_help=True)
app.add_typer(cvm_app, name="cvm")


@cvm_app.command("holdings")
def cvm_holdings(
    cnpj: str = typer.Argument(help="Fund CNPJ (with or without punctuation)"),
    year: int = typer.Option(..., "--year", "-y"),
    month: int = typer.Option(..., "--month", "-m"),
    blocks: str | None = typer.Option(
        None,
        "--blocks",
        "-b",
        help="Comma list (BLC_1..BLC_8, CONFID, PL, FIE)",
    ),
) -> None:
    """Show one fund's full portfolio (CDA) for a given YYYY/MM."""
    from findata.sources.cvm import get_fund_holdings

    block_list = [b.strip() for b in blocks.split(",")] if blocks else None
    rows = _run(get_fund_holdings(cnpj, year, month, block_list))
    if not rows:
        rprint(f"[yellow]No holdings for {cnpj} in {year}-{month:02d}.[/yellow]")
        return
    table = Table(title=f"Holdings — {cnpj} — {year}-{month:02d}")
    table.add_column("Block", style="blue")
    table.add_column("Tipo Aplicação")
    table.add_column("Tipo Ativo")
    table.add_column("Emissor")
    table.add_column("Qtd", justify="right")
    table.add_column("VL Mercado R$", style="green", justify="right")
    table.add_column("Descrição")
    for h in rows[:200]:
        table.add_row(
            h.bloco,
            (h.tipo_aplicacao or "")[:25],
            (h.tipo_ativo or "")[:25],
            (h.emissor or "")[:25],
            _fmt(h.quantidade_final, ".2f"),
            _fmt(h.valor_mercado, ",.2f"),
            (h.descricao or "")[:30],
        )
    rprint(table)
    max_rows = 200
    if len(rows) > max_rows:
        rprint(f"[dim](showing {max_rows} of {len(rows)} rows)[/dim]")


def _print_lamina_header(f: Any) -> None:
    """Print the compact header for a CVM fund lâmina."""
    rprint(f"[bold]{f.denom_social}[/bold]  ({f.cnpj})")
    if f.nome_fantasia:
        rprint(f"  Fantasia: {f.nome_fantasia}")
    rprint(f"  Ref: {f.dt_referencia}")
    if f.publico_alvo:
        rprint(f"  Público alvo: {f.publico_alvo}")
    if f.objetivo:
        rprint(f"  Objetivo: {f.objetivo[:200]}")
    if f.pct_pl_alavancagem is not None:
        rprint(f"  % PL Alavancagem: {f.pct_pl_alavancagem:.2f}%")
    if f.pct_pl_ativo_exterior is not None:
        rprint(f"  % PL Exterior: {f.pct_pl_ativo_exterior:.2f}%")
    if f.pct_pl_ativo_credito_privado is not None:
        rprint(f"  % PL Crédito Privado: {f.pct_pl_ativo_credito_privado:.2f}%")


def _print_returns_table(title: str, rows: list[Any], columns: list[tuple[str, str]]) -> None:
    """Print a returns table. ``columns`` is a list of (header, attribute_name)."""
    if not rows:
        return
    table = Table(title=title)
    for header, _ in columns:
        table.add_column(header, justify="right", style="cyan")
    for r in rows:
        cells: list[str] = []
        for _, attr in columns:
            val = getattr(r, attr, None)
            if isinstance(val, (int, float)):
                cells.append(_fmt(float(val), "+.4f"))
            else:
                cells.append(str(val) if val is not None else "")
        table.add_row(*cells)
    rprint(table)


@cvm_app.command("lamina")
def cvm_lamina(
    cnpj: str = typer.Argument(help="Fund CNPJ"),
    year: int = typer.Option(..., "--year", "-y"),
    month: int = typer.Option(..., "--month", "-m"),
) -> None:
    """Show one fund's regulatory factsheet (lâmina) for a given YYYY/MM."""
    from findata.sources.cvm import (
        get_fund_lamina,
        get_fund_monthly_returns,
        get_fund_yearly_returns,
    )

    main = _run(get_fund_lamina(year, month, cnpj))
    if not main:
        rprint(f"[yellow]No lâmina for {cnpj} in {year}-{month:02d}.[/yellow]")
        return
    _print_lamina_header(main[0])

    monthly = _run(get_fund_monthly_returns(year, month, cnpj))
    _print_returns_table(
        "Rentabilidade Mensal",
        monthly[:24],
        [("Mês", "mes_competencia"), ("Rent %", "rentabilidade_pct"), ("Bench %", "bench_pct")],
    )

    yearly = _run(get_fund_yearly_returns(year, month, cnpj))
    _print_returns_table(
        "Rentabilidade Anual",
        yearly,
        [
            ("Ano", "ano"),
            ("Rent %", "rentabilidade_pct"),
            ("Bench %", "bench_pct"),
            ("Bench Nome", "bench_nome"),
        ],
    )


@cvm_app.command("profile")
def cvm_profile(
    cnpj: str = typer.Argument(help="Fund CNPJ"),
    year: int = typer.Option(..., "--year", "-y"),
    month: int = typer.Option(..., "--month", "-m"),
) -> None:
    """Show one fund's investor profile breakdown (cotistas por tipo)."""
    from findata.sources.cvm import get_fund_profile

    rows = _run(get_fund_profile(year, month, cnpj))
    if not rows:
        rprint(f"[yellow]No profile for {cnpj} in {year}-{month:02d}.[/yellow]")
        return
    p = rows[0]
    rprint(f"[bold]{p.denom_social}[/bold]  ({p.cnpj})")
    rprint(f"  Ref: {p.dt_referencia}")
    rprint("\n  Cotistas:")
    rprint(f"    PF Private:           {p.cotistas_pf_private or 0:,}")
    rprint(f"    PF Varejo:            {p.cotistas_pf_varejo or 0:,}")
    rprint(f"    PJ Não-Financ Private:{p.cotistas_pj_nao_financ_private or 0:,}")
    rprint(f"    PJ Não-Financ Varejo: {p.cotistas_pj_nao_financ_varejo or 0:,}")
    rprint(f"    Banco:                {p.cotistas_banco or 0:,}")
    rprint(f"    Corretora/Distrib:    {p.cotistas_corretora_distrib or 0:,}")
    rprint(f"    PJ Financeira:        {p.cotistas_pj_financ or 0:,}")


@cvm_app.command("fii")
def cvm_fii(
    cnpj: str = typer.Argument(help="FII CNPJ"),
    year: int = typer.Option(..., "--year", "-y"),
    month: int | None = typer.Option(None, "--month", "-m"),
) -> None:
    """Show one FII's cadastral + complement facets."""
    from findata.sources.cvm import get_fii_complemento, get_fii_geral

    geral = _run(get_fii_geral(year, cnpj=cnpj, month=month))
    if not geral:
        rprint(f"[yellow]No FII data for {cnpj} in {year}.[/yellow]")
        return
    g = geral[0]
    rprint(f"[bold]{g.nome_fundo}[/bold]  ({g.cnpj})")
    rprint(f"  Segmento: {g.segmento_atuacao or '-'}")
    rprint(f"  Mandato:  {g.mandato or '-'}")
    rprint(f"  Gestão:   {g.tipo_gestao or '-'}")
    rprint(f"  Admin:    {g.nome_administrador or '-'}")
    rprint(f"  ISIN:     {g.isin or '-'}")

    comp = _run(get_fii_complemento(year, cnpj=cnpj, month=month))
    if comp:
        c = comp[-1]  # most recent month if multiple
        rprint(f"\n  Ref:      {c.dt_referencia}")
        if c.patrimonio_liquido:
            rprint(f"  PL:       R$ {c.patrimonio_liquido:,.0f}")
        if c.valor_patrimonial_cotas:
            rprint(f"  VP cota:  R$ {c.valor_patrimonial_cotas:.2f}")
        rprint(f"  Cotistas: {c.total_cotistas or 0:,}  (PF {c.cotistas_pf or 0:,})")


@cvm_app.command("fidc")
def cvm_fidc(
    cnpj: str = typer.Argument(help="FIDC CNPJ"),
    year: int = typer.Option(..., "--year", "-y"),
    month: int = typer.Option(..., "--month", "-m"),
) -> None:
    """Show one FIDC's PL + direitos creditórios."""
    from findata.sources.cvm import (
        get_fidc_direitos_creditorios,
        get_fidc_geral,
        get_fidc_pl,
    )

    geral = _run(get_fidc_geral(year, month, cnpj=cnpj))
    if not geral:
        rprint(f"[yellow]No FIDC data for {cnpj} in {year}-{month:02d}.[/yellow]")
        return
    g = geral[0]
    rprint(f"[bold]{g.nome_fundo}[/bold]  ({g.cnpj})")
    rprint(f"  Ref:    {g.dt_referencia}")
    rprint(f"  Tipo:   {g.tipo_fundo_classe or '-'}  ·  Classe: {g.classe or '-'}")
    rprint(f"  Admin:  {g.nome_administrador or '-'}")

    pl = _run(get_fidc_pl(year, month, cnpj=cnpj))
    if pl:
        p = pl[0]
        rprint(f"\n  PL final:  R$ {p.pl_final:,.0f}" if p.pl_final else "  PL final:  -")
        rprint(f"  PL médio:  R$ {p.pl_medio:,.0f}" if p.pl_medio else "  PL médio:  -")

    dc = _run(get_fidc_direitos_creditorios(year, month, cnpj=cnpj))
    if dc:
        d = dc[0]
        rprint("\n  Direitos creditórios:")
        if d.valor_com_risco:
            rprint(f"    Com risco:    R$ {d.valor_com_risco:,.0f}")
        if d.valor_sem_risco:
            rprint(f"    Sem risco:    R$ {d.valor_sem_risco:,.0f}")


@cvm_app.command("fip")
def cvm_fip(
    cnpj: str = typer.Argument(help="FIP CNPJ"),
    year: int = typer.Option(..., "--year", "-y"),
    quarter: int | None = typer.Option(None, "--quarter", "-q", min=1, max=4),
) -> None:
    """Show one FIP's quarterly informe."""
    from findata.sources.cvm import get_fip

    rows = _run(get_fip(year, cnpj=cnpj, quarter=quarter))
    if not rows:
        rprint(f"[yellow]No FIP data for {cnpj} in {year}.[/yellow]")
        return
    r = rows[-1]
    rprint(f"[bold]{r.nome_fundo}[/bold]  ({r.cnpj})")
    rprint(f"  Ref:           {r.dt_referencia}")
    if r.patrimonio_liquido:
        rprint(f"  PL:            R$ {r.patrimonio_liquido:,.0f}")
    if r.valor_patrimonial_cota:
        rprint(f"  VP cota:       R$ {r.valor_patrimonial_cota:,.4f}")
    rprint(f"  Cotistas:      {r.num_cotistas or 0:,}")
    if r.capital_comprometido:
        rprint(f"  Cap comprom.:  R$ {r.capital_comprometido:,.0f}")
    if r.capital_integralizado:
        rprint(f"  Cap integr.:   R$ {r.capital_integralizado:,.0f}")
    rprint(f"  Classe cota:   {r.classe_cota or '-'}")


@cvm_app.command("ipe")
def cvm_ipe(
    cnpj: str = typer.Argument(help="Issuer CNPJ"),
    year: int = typer.Option(..., "--year", "-y"),
    categoria: str | None = typer.Option(None, "--categoria", "-c"),
) -> None:
    """List IPE corporate filings (fatos relevantes / comunicados / atas)."""
    from findata.sources.cvm import get_ipe

    rows = _run(get_ipe(year, cnpj=cnpj, categoria=categoria))
    if not rows:
        rprint(f"[yellow]No IPE filings for {cnpj} in {year}.[/yellow]")
        return
    table = Table(title=f"IPE filings — {rows[0].nome_empresa} ({year})")
    table.add_column("Date", style="cyan")
    table.add_column("Categoria")
    table.add_column("Tipo")
    table.add_column("Espécie / Assunto")
    max_shown = 50
    for d in rows[:max_shown]:
        subject = d.especie or d.assunto or ""
        table.add_row(d.dt_referencia, d.categoria, d.tipo or "-", subject)
    rprint(table)
    if len(rows) > max_shown:
        rprint(f"[dim](showing {max_shown} of {len(rows)} — filter by --categoria)[/dim]")


@cvm_app.command("ticker")
def cvm_ticker(
    ticker: str = typer.Argument(help="B3 ticker (e.g. PETR4, VALE3, ITUB4)"),
    year: int = typer.Option(..., "--year", "-y"),
) -> None:
    """Resolve a B3 ticker → CNPJ + company facts via FCA."""
    from findata.sources.cvm import get_fca_geral, get_fca_valores_mobiliarios

    securities = _run(get_fca_valores_mobiliarios(year, ticker=ticker))
    if not securities:
        rprint(f"[yellow]No security '{ticker}' found in FCA {year}.[/yellow]")
        return
    s = securities[0]
    rprint(f"[bold]{s.nome_empresarial}[/bold]  ({s.cnpj})")
    rprint(f"  Ticker:   {s.codigo_negociacao}")
    rprint(f"  Tipo:     {s.valor_mobiliario}")
    rprint(f"  Mercado:  {s.mercado}  ·  Segmento: {s.segmento or '-'}")
    rprint(f"  Listada:  {s.dt_inicio_listagem or '-'}  →  {s.dt_fim_listagem or 'atual'}")
    geral = _run(get_fca_geral(year, cnpj=s.cnpj))
    if geral:
        g = geral[0]
        rprint(f"\n  Setor:    {g.setor_atividade or '-'}")
        rprint(f"  Atividade: {g.descricao_atividade or '-'}")
        rprint(f"  Controle: {g.especie_controle_acionario or '-'}")
        rprint(f"  Situação: {g.situacao_emissor or '-'}  ·  Registro: {g.situacao_registro_cvm}")
        rprint(f"  Site:     {g.pagina_web or '-'}")


@cvm_app.command("search")
def cvm_search(
    query: str = typer.Argument(help="Company name to search"),
    only_active: bool = typer.Option(True, "--active/--all"),
) -> None:
    """Search CVM-registered companies."""
    from findata.sources.cvm import search_company

    results = _run(search_company(query, only_active))
    if not results:
        rprint("[yellow]No companies matched.[/yellow]")
        return
    table = Table(title=f"CVM companies matching '{query}'")
    table.add_column("CNPJ", style="cyan")
    table.add_column("Name")
    table.add_column("Situação", style="green")
    table.add_column("Setor")
    max_shown = 50
    for c in results[:max_shown]:
        table.add_row(c.cnpj, c.nome_comercial or c.nome_social, c.situacao, c.setor)
    rprint(table)
    if len(results) > max_shown:
        rprint(f"[dim](showing {max_shown} of {len(results)} — refine your query)[/dim]")


# ── Serve command ──────────────────────────────────────────────────


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
    reload: bool = typer.Option(False, help="Enable hot reload"),
    no_banner: bool = typer.Option(False, "--no-banner", help="Skip the animated banner"),
) -> None:
    """Start the API + MCP server."""
    import uvicorn

    if not no_banner:
        render_animated_banner(_console)
    _console.print(render_startup_panel(host, port))
    uvicorn.run("findata.api.app:app", host=host, port=port, reload=reload)


# ── Base dos Dados commands ───────────────────────────────────────

basedosdados_app = typer.Typer(
    help="Base dos Dados — free logged-in SQL/Python/R access", no_args_is_help=True
)
app.add_typer(basedosdados_app, name="basedosdados")


@basedosdados_app.command("info")
def basedosdados_info() -> None:
    """Show Base dos Dados access modes."""
    from findata.sources.basedosdados import source_info

    info = source_info()
    rprint(f"[bold]{info.source}[/bold] — {info.status}")
    for path in info.access_paths:
        req = f" ({', '.join(path.requires)})" if path.requires else ""
        rprint(f"  [cyan]{path.access}[/cyan] · {path.name}: {path.description}{req}")


@basedosdados_app.command("sql")
def basedosdados_sql(
    dataset_id: str = typer.Argument(help="Dataset id, e.g. br_bd_diretorios_brasil"),
    table_id: str = typer.Argument(help="Table id, e.g. municipio"),
    limit: int = typer.Option(100, "--limit", "-n", min=1, max=10_000),
) -> None:
    """Print starter BigQuery SQL for a Base dos Dados table."""
    from findata.sources.basedosdados import table_ref

    ref = table_ref(dataset_id, table_id, limit)
    rprint(f"[bold]{ref.full_table_id}[/bold] ({ref.access})")
    rprint(ref.sql)


@basedosdados_app.command("direct-download-free")
def basedosdados_direct_download_free(
    theme: str | None = typer.Option(None, "--theme", help="Theme filter, e.g. economics"),
    page: int = typer.Option(1, "--page", min=1),
) -> None:
    """List datasets with free direct download in Base dos Dados."""
    from findata.sources.basedosdados import search_direct_download_free

    result = _run(search_direct_download_free(theme=theme, page=page))
    rows = result.get("results", [])
    table = Table(title=f"Base dos Dados — download direto gratuito ({result.get('count', 0)})")
    table.add_column("slug", style="cyan")
    table.add_column("name")
    table.add_column("tables", justify="right")
    for row in rows:
        if not isinstance(row, dict):
            continue
        table.add_row(
            str(row.get("slug", "-")),
            str(row.get("name", "-"))[:70],
            str(row.get("n_tables", "-")),
        )
    rprint(table)


def _write_basedosdados_rows(
    rows: list[dict[str, object]],
    row_count: int,
    output: Literal["table", "csv", "json"],
    out: str | None,
    project: str,
) -> None:
    """Render or write a Base dos Dados BigQuery query result."""
    import csv
    import json
    from pathlib import Path

    if output == "json":
        payload = json.dumps(rows, ensure_ascii=False, indent=2)
        if out:
            Path(out).write_text(payload)
            rprint(f"[green]Wrote[/green] {out} ({row_count} rows)")
        else:
            rprint(payload)
        return

    if not rows:
        rprint("[yellow]No rows returned.[/yellow]")
        return

    fieldnames = list(rows[0])
    if output == "csv":
        if out:
            with Path(out).open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            rprint(f"[green]Wrote[/green] {out} ({row_count} rows)")
        else:
            writer = csv.DictWriter(_console.file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return

    table = Table(title=f"Base dos Dados BigQuery ({row_count} rows, project={project})")
    for name in fieldnames:
        table.add_column(name)
    for row in rows:
        table.add_row(*(str(row.get(name, "")) for name in fieldnames))
    rprint(table)


@basedosdados_app.command("query")
def basedosdados_query(
    query: str = typer.Argument(help="SQL string, or file path when --from-file is set"),
    billing_project_id: str | None = typer.Option(
        None,
        "--billing-project-id",
        "-p",
        help="Google Cloud project billed by BigQuery",
    ),
    from_file: bool = typer.Option(False, "--from-file", help="Read SQL from query file path"),
    reauth: bool = typer.Option(False, "--reauth", help="Force Google re-authentication"),
    use_bqstorage_api: bool = typer.Option(
        False,
        "--use-bqstorage-api",
        help="Use BigQuery Storage API for faster downloads; can increase cost",
    ),
    max_rows: int = typer.Option(100, "--max-rows", min=1, max=10_000),
    output: Literal["table", "csv", "json"] = typer.Option("table", "--output", "-o"),
    out: str | None = typer.Option(None, "--out", help="Write csv/json output to this path"),
) -> None:
    """Run a free logged-in Base dos Dados BigQuery query locally."""
    from pathlib import Path

    from findata.sources.basedosdados import (
        BaseDosDadosSDKNotInstalledError,
        read_sql_preview,
        resolve_billing_project_id,
    )

    sql = Path(query).read_text() if from_file else query
    project = resolve_billing_project_id(billing_project_id) or "SDK/default auth"
    try:
        result = read_sql_preview(
            sql,
            billing_project_id=billing_project_id,
            from_file=False,
            reauth=reauth,
            use_bqstorage_api=use_bqstorage_api,
            max_rows=max_rows,
        )
    except BaseDosDadosSDKNotInstalledError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        rprint(f"[red]BigQuery error:[/red] {exc}")
        rprint(
            "[dim]Check Google auth and set --billing-project-id or "
            "FINDATA_BD_BILLING_PROJECT_ID.[/dim]"
        )
        raise typer.Exit(code=1) from exc

    _write_basedosdados_rows(result.rows, result.row_count, output, out, project)


@basedosdados_app.command("datasets")
def basedosdados_datasets(
    name: str | None = typer.Option(None, "--name", help="Dataset name search"),
    dataset_id: str | None = typer.Option(None, "--id", help="Dataset id"),
    page: int = typer.Option(1, "--page", min=1),
    page_size: int = typer.Option(10, "--page-size", min=1, max=100),
) -> None:
    """List datasets via the optional basedosdados SDK."""
    from findata.sources.basedosdados import BaseDosDadosSDKNotInstalledError, get_datasets

    try:
        rows = get_datasets(
            dataset_id=dataset_id, dataset_name=name, page=page, page_size=page_size
        )
    except BaseDosDadosSDKNotInstalledError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Base dos Dados datasets")
    table.add_column("dataset_id", style="cyan")
    table.add_column("name")
    for row in rows:
        table.add_row(
            str(row.get("dataset_id", "-")), str(row.get("name", row.get("dataset_name", "-")))
        )
    rprint(table)


@basedosdados_app.command("tables")
def basedosdados_tables(
    dataset_id: str | None = typer.Option(None, "--dataset-id", help="Dataset id"),
    table_name: str | None = typer.Option(None, "--name", help="Table name search"),
    table_id: str | None = typer.Option(None, "--id", help="Table id"),
    page: int = typer.Option(1, "--page", min=1),
    page_size: int = typer.Option(10, "--page-size", min=1, max=100),
) -> None:
    """List tables via the optional basedosdados SDK."""
    from findata.sources.basedosdados import BaseDosDadosSDKNotInstalledError, get_tables

    try:
        rows = get_tables(
            dataset_id=dataset_id,
            table_id=table_id,
            table_name=table_name,
            page=page,
            page_size=page_size,
        )
    except BaseDosDadosSDKNotInstalledError as exc:
        rprint(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Base dos Dados tables")
    table.add_column("dataset_id", style="cyan")
    table.add_column("table_id", style="green")
    table.add_column("name")
    for row in rows:
        table.add_row(
            str(row.get("dataset_id", "-")),
            str(row.get("table_id", "-")),
            str(row.get("name", row.get("table_name", "-"))),
        )
    rprint(table)


# ── Yahoo Finance commands ────────────────────────────────────────

yahoo_app = typer.Typer(
    help="Yahoo Finance market data (experimental, unofficial)",
    no_args_is_help=True,
)
app.add_typer(yahoo_app, name="yahoo")


@yahoo_app.command("chart")
def yahoo_chart(
    symbol: str = typer.Argument(help="Yahoo symbol (e.g., PETR4.SA, ^BVSP, BTC-USD)"),
    range_: str = typer.Option("1mo", "--range", "-r", help="Range: 1mo, 1y, ytd, max"),
    interval: str = typer.Option("1d", "--interval", "-i", help="Interval: 1d, 1wk, 1mo"),
) -> None:
    """Get an experimental OHLCV chart from Yahoo Finance."""
    from findata.sources.yahoo import get_chart

    data = _run(get_chart(symbol, range_, interval))
    table = Table(title=f"Yahoo: {data.symbol} — {range_}/{interval}")
    table.add_column("Date", style="cyan")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right", style="green")
    table.add_column("Low", justify="right", style="red")
    table.add_column("Close", justify="right", style="bold")
    table.add_column("Volume", justify="right")

    for point in data.points[-60:]:
        table.add_row(
            point.date,
            _fmt(point.open),
            _fmt(point.high),
            _fmt(point.low),
            _fmt(point.close),
            f"{point.volume:,}" if point.volume is not None else "-",
        )

    rprint(table)
    rprint("[dim]Source: Yahoo Finance v8 chart (unofficial, best-effort).[/dim]")


if __name__ == "__main__":
    app()
