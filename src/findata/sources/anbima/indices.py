"""ANBIMA public indices and curves — IMA, ETTJ, Debêntures.

All data here is fetched from free static files on `www.anbima.com.br`.
No credentials, no API key, no rate-limit tricks (just the upstream's
once-a-day refresh cadence).
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import ssl
import time
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

import httpx
import xlrd
from pydantic import BaseModel

from findata._cache import TTLCache
from findata.http_client import USER_AGENT, get_bytes

logger = logging.getLogger(__name__)

# ── URLs ──────────────────────────────────────────────────────────

IMA_HISTORY_URL = "https://www.anbima.com.br/informacoes/ima/arqs/ima_completo.xls"
IMA_HISTORY_DOWNLOAD_URL = "https://www.anbima.com.br/informacoes/ima/ima-sh-down.asp"
ETTJ_URL = "https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp"
DEBENTURES_URL = "https://www.anbima.com.br/informacoes/merc-sec-debentures/arqs/db{ymd}.txt"


# ── Models ────────────────────────────────────────────────────────


class IMAFamily(StrEnum):
    IMA_GERAL = "IMA-Geral"
    IMA_B = "IMA-B"
    IMA_B_5 = "IMA-B 5"
    IMA_B_5_PLUS = "IMA-B 5+"
    IMA_S = "IMA-S"
    IRF_M = "IRF-M"
    IRF_M_1 = "IRF-M 1"
    IRF_M_1_PLUS = "IRF-M 1+"


class IMADataPoint(BaseModel):
    indice: str
    data_referencia: str  # YYYY-MM-DD
    numero_indice: float | None = None
    variacao_dia_pct: float | None = None
    variacao_mes_pct: float | None = None
    variacao_ano_pct: float | None = None
    variacao_12m_pct: float | None = None
    variacao_24m_pct: float | None = None
    duration_du: float | None = None
    valor_mercado_rs_mil: float | None = None
    peso_pct: float | None = None


class ETTJDataPoint(BaseModel):
    data_referencia: str  # YYYY-MM-DD
    vertice_du: int  # business days to maturity
    taxa_pre_pct: float | None = None
    taxa_ipca_pct: float | None = None
    inflacao_implicita_pct: float | None = None


class DebentureQuote(BaseModel):
    data_referencia: str  # YYYY-MM-DD
    codigo: str
    emissor: str
    repactuacao_vencimento: str
    indice_correcao: str
    taxa_compra_pct: float | None = None
    taxa_venda_pct: float | None = None
    taxa_indicativa_pct: float | None = None
    desvio_padrao: float | None = None
    intervalo_min_pct: float | None = None
    intervalo_max_pct: float | None = None
    pu: float | None = None
    pu_par_pct: float | None = None
    duration_du: float | None = None
    pct_reune: float | None = None
    referencia_ntn_b: str | None = None


# ── Helpers ───────────────────────────────────────────────────────


def _f_br(val: str | None) -> float | None:
    """Parse a Brazilian-formatted decimal ('1.234,56' or '0,1294')."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s in {"--", "N/D", "n/d", "-"}:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


_ISO_DATE_PARTS = 3
_TWO_DIGIT_YEAR_LEN = 2
_TWO_DIGIT_YEAR_PIVOT = 80  # < 80 → 20xx, >= 80 → 19xx


def _date_to_iso(s: str) -> str:
    """ANBIMA ships dates as DD/MM/YYYY. Normalise to YYYY-MM-DD."""
    s = s.strip()
    if "/" not in s:
        return s
    parts = s.split("/")
    if len(parts) != _ISO_DATE_PARTS:
        return s
    d, m, y = parts
    if len(y) == _TWO_DIGIT_YEAR_LEN:
        y = ("20" + y) if int(y) < _TWO_DIGIT_YEAR_PIVOT else ("19" + y)
    return f"{y}-{int(m):02d}-{int(d):02d}"


# ── IMA (snapshot of the latest trading day) ─────────────────────
# The file ANBIMA publishes is named `ima_completo.xls` but it's actually
# a one-day snapshot of every IMA family — not a multi-year history.
# Refresh daily; caller filters by family if they want a single index.

_ima_cache: TTLCache[list[IMADataPoint]] = TTLCache(ttl=86400)

_EXCEL_DATE_THRESHOLD = 1000  # any positive float > this is a plausible Excel serial
_QUADRO_FIRST_DATA_ROW = 3  # row 0..2 is title + headers; data starts at row 3


def _excel_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return _f_br(str(v))


def _excel_date(book: Any, v: Any) -> str | None:
    if isinstance(v, (int, float)) and float(v) > _EXCEL_DATE_THRESHOLD:
        try:
            tup = xlrd.xldate_as_tuple(float(v), book.datemode)
        except Exception:
            return None
        return f"{tup[0]:04d}-{tup[1]:02d}-{tup[2]:02d}"
    if isinstance(v, str) and "/" in v:
        return _date_to_iso(v)
    return None


def _ima_index_name(family: str, sub: Any) -> str | None:
    """Combine family + subfamily cell into a canonical IMA name.

    'IRF-M', 1.0   -> 'IRF-M 1'
    'IRF-M', '1+'  -> 'IRF-M 1+'
    'IMA-B', 'TOTAL' -> 'IMA-B' (rolling total)
    'IMA-S', ''    -> 'IMA-S'
    """
    family = family.strip()
    if not family:
        return None
    if sub is None or sub == "":
        return family
    sub_str = str(sub).strip()
    if sub_str.upper() == "TOTAL":
        return family
    # Strip trailing ".0" from numeric subs that came back as floats.
    if sub_str.endswith(".0"):
        sub_str = sub_str[:-2]
    return f"{family} {sub_str}".strip()


def _cell(cells: list[Any], idx: int) -> Any:
    return cells[idx] if idx < len(cells) else None


async def _load_ima() -> list[IMADataPoint]:
    """Parse `ima_completo.xls`'s 'Quadro Resumo' snapshot tab."""
    raw = await get_bytes(IMA_HISTORY_URL, cache_ttl=86400)
    book = xlrd.open_workbook(file_contents=raw)
    if "Quadro Resumo" not in book.sheet_names():
        return []
    sheet = book.sheet_by_name("Quadro Resumo")
    rows: list[IMADataPoint] = []
    for r in range(_QUADRO_FIRST_DATA_ROW, sheet.nrows):
        cells = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
        family = str(_cell(cells, 0) or "").strip()
        if not family:
            continue
        index_name = _ima_index_name(family, _cell(cells, 1))
        if index_name is None:
            continue
        date_iso = _excel_date(book, _cell(cells, 2))
        if not date_iso:
            continue
        rows.append(
            IMADataPoint(
                indice=index_name,
                data_referencia=date_iso,
                numero_indice=_excel_float(_cell(cells, 3)),
                variacao_dia_pct=_excel_float(_cell(cells, 4)),
                variacao_mes_pct=_excel_float(_cell(cells, 5)),
                variacao_ano_pct=_excel_float(_cell(cells, 6)),
                variacao_12m_pct=_excel_float(_cell(cells, 7)),
                variacao_24m_pct=_excel_float(_cell(cells, 8)),
                duration_du=_excel_float(_cell(cells, 9)),
                valor_mercado_rs_mil=_excel_float(_cell(cells, 10)),
                peso_pct=_excel_float(_cell(cells, 11)),
            )
        )
    return rows


async def get_ima(family: IMAFamily | str | None = None) -> list[IMADataPoint]:
    """Latest IMA snapshot, optionally filtered to one family.

    The upstream file is a one-day snapshot, so this returns one row per
    sub-index (e.g., `IRF-M 1`, `IRF-M 1+`, `IRF-M` rolling total) for the
    most recent published date. Cached for 24 hours.
    """
    rows = await _ima_cache.get_or_load(_load_ima)
    if family:
        wanted = str(family)
        rows = [r for r in rows if r.indice == wanted]
    return rows


# Back-compat alias — old callers / tests may still import this.
get_ima_latest = get_ima


# ── IMA historical series (one CSV per business day) ────────────
# ANBIMA's "Série Histórica" form (https://www.anbima.com.br/informacoes/ima/ima-sh.asp)
# POSTs to ``ima-sh-down.asp`` and returns a CSV (latin-1, ``;`` delimited)
# with one IMA snapshot for the requested calendar day. Non-business days
# return the literal banner ``Não há dados disponíveis para [DATE] !``.

_IMA_NO_DATA_MARKER = "não há dados"
_IMA_HISTORY_CONCURRENCY = 8
_IMA_HISTORY_TIMEOUT = 30.0
_IMA_HISTORY_CACHE_TTL = 86400.0
_IMA_HISTORY_HEADER_NEEDLE = "data de refer"  # locates the column-header row
_SATURDAY = 5
_SUNDAY = 6
_IMA_CSV_MIN_FIELDS = 11  # core schema (Index .. Carteira) — newer files add more

# Per-date result cache: iso_date -> (loaded_at, rows). Cached entries are
# whole-day snapshots from ANBIMA, immutable once published, so 24h TTL is safe.
_ima_history_cache: dict[str, tuple[float, list[IMADataPoint]]] = {}


def _ima_history_cache_get(iso: str) -> list[IMADataPoint] | None:
    entry = _ima_history_cache.get(iso)
    if entry is None:
        return None
    loaded_at, rows = entry
    if time.time() - loaded_at >= _IMA_HISTORY_CACHE_TTL:
        del _ima_history_cache[iso]
        return None
    return rows


def _ima_history_cache_set(iso: str, rows: list[IMADataPoint]) -> None:
    _ima_history_cache[iso] = (time.time(), rows)


def _ima_history_cache_clear() -> None:
    _ima_history_cache.clear()


def _ima_history_ssl_context() -> Any:
    """Mirror ``http_client._ssl_context`` (kept private over there)."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def _parse_ima_history_csv(text: str, expected_iso: str) -> list[IMADataPoint]:
    """Parse the ``ima-sh-down.asp`` CSV payload for one reference day.

    The payload is wrapped with a banner row and a header row. The header
    column order is (positionally): Índice, Data, Número, Var Dia, Var Mês,
    Var Ano, Var 12m, Var 24m, Peso, Duration, Carteira (R$ mil), and seven
    optional trailing fields (number of trades, volumes, PMR, convexity,
    yield, redemption yield) we don't model.
    """
    if not text or _IMA_NO_DATA_MARKER in text.lower():
        return []
    rows: list[IMADataPoint] = []
    in_data = False
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if not in_data:
            # Skip everything until we see the header row.
            if _IMA_HISTORY_HEADER_NEEDLE in s.lower() and ";" in s:
                in_data = True
            continue
        parts = [p.strip() for p in s.split(";")]
        if len(parts) < _IMA_CSV_MIN_FIELDS:
            continue
        family = parts[0]
        if not family or family.upper().startswith("TOTAIS"):
            continue
        date_iso = _date_to_iso(parts[1]) if parts[1] else expected_iso
        rows.append(
            IMADataPoint(
                indice=family,
                data_referencia=date_iso,
                numero_indice=_f_br(parts[2]),
                variacao_dia_pct=_f_br(parts[3]),
                variacao_mes_pct=_f_br(parts[4]),
                variacao_ano_pct=_f_br(parts[5]),
                variacao_12m_pct=_f_br(parts[6]),
                variacao_24m_pct=_f_br(parts[7]),
                peso_pct=_f_br(parts[8]),
                duration_du=_f_br(parts[9]),
                valor_mercado_rs_mil=_f_br(parts[10]),
            )
        )
    return rows


async def _post_ima_history_csv(client: httpx.AsyncClient, d: date) -> str | None:
    """POST the form for date ``d`` and return the decoded payload (or None)."""
    payload = {
        "Tipo": "",
        "DataRef": "",
        "Pai": "ima",
        "escolha": "2",
        "Idioma": "PT",
        "saida": "csv",
        "Dt_Ref": d.strftime("%d/%m/%Y"),
        "Dt_Ref_Ver": d.strftime("%Y%m%d"),
    }
    try:
        resp = await client.post(IMA_HISTORY_DOWNLOAD_URL, data=payload)
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("IMA history fetch failed for %s: HTTP %s", d, exc.response.status_code)
        return None
    except httpx.HTTPError as exc:
        logger.warning("IMA history fetch failed for %s: %s", d, exc)
        return None
    return resp.content.decode("latin1", errors="replace")


async def _fetch_ima_for_date(client: httpx.AsyncClient, d: date) -> list[IMADataPoint]:
    """Return the IMA snapshot for one calendar day (cached for 24 h)."""
    iso = d.strftime("%Y-%m-%d")
    cached = _ima_history_cache_get(iso)
    if cached is not None:
        return cached
    text = await _post_ima_history_csv(client, d)
    if text is None:
        return []
    rows = _parse_ima_history_csv(text, iso)
    if not rows:
        # No-data days (weekends, holidays, dates before IMA inception) are
        # cached as empty so we don't re-hit ANBIMA on every backtest call.
        logger.debug("No IMA data published for %s", iso)
    _ima_history_cache_set(iso, rows)
    return rows


def _iter_candidate_days(start: date, end: date) -> list[date]:
    """All calendar days in ``[start, end]`` excluding weekends.

    Brazilian bank holidays still get probed (and skipped on no-data); we
    don't carry a holiday calendar here to avoid a runtime dependency.
    """
    if end < start:
        return []
    days: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() not in (_SATURDAY, _SUNDAY):
            days.append(cur)
        cur += timedelta(days=1)
    return days


async def get_ima_history(
    family: IMAFamily | str | None,
    start: date,
    end: date,
) -> list[IMADataPoint]:
    """Historical IMA series across a date range.

    One snapshot per business day in ``[start, end]``. Optionally filtered
    to a single ``family`` (e.g. ``IMAFamily.IMA_B`` or the literal string
    ``"IMA-B 5"``); pass ``None`` to keep every sub-index. Days with no
    published data (weekends, holidays, pre-inception) are silently skipped.

    Each daily fetch is cached for 24 hours and concurrent fetches are
    capped at 8 to stay polite with ANBIMA's static-file server.
    """
    if end < start:
        return []
    wanted = str(family).strip().lower() if family else None

    sem = asyncio.Semaphore(_IMA_HISTORY_CONCURRENCY)
    async with httpx.AsyncClient(
        timeout=_IMA_HISTORY_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        verify=_ima_history_ssl_context(),
    ) as client:

        async def _one(d: date) -> list[IMADataPoint]:
            async with sem:
                return await _fetch_ima_for_date(client, d)

        results = await asyncio.gather(*(_one(d) for d in _iter_candidate_days(start, end)))

    out: list[IMADataPoint] = []
    for daily in results:
        for r in daily:
            if wanted is not None and r.indice.lower() != wanted:
                continue
            out.append(r)
    out.sort(key=lambda r: r.data_referencia)
    return out


# ── ETTJ (curva zero, daily CSV) ─────────────────────────────────


async def get_ettj(data_referencia: date | None = None) -> list[ETTJDataPoint]:
    """Yield curve (zero coupon) for a reference date.

    The CSV ANBIMA serves has two stacked sections — Nelson-Siegel-Svensson
    parameters first, then a `Vertices;ETTJ IPCA;ETTJ PREF;Inflação Implícita`
    table. We parse the second section.
    """
    d = data_referencia or date.today()
    raw = await get_bytes(
        f"{ETTJ_URL}?Dt_Ref={d.strftime('%d%m%y')}&saida=csv",
        cache_ttl=3600,
    )
    text = raw.decode("latin1", errors="replace")
    iso = d.strftime("%Y-%m-%d")
    rows: list[ETTJDataPoint] = []
    in_table = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            in_table = False
            continue
        if line.startswith("Vertices"):
            in_table = True
            continue
        if not in_table:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 2:  # noqa: PLR2004
            continue
        # First column "Vertices" arrives as "126" or "1.260" (thousands sep)
        v = parts[0].replace(".", "")
        try:
            vert = int(v)
        except ValueError:
            continue
        rows.append(
            ETTJDataPoint(
                data_referencia=iso,
                vertice_du=vert,
                taxa_ipca_pct=_f_br(parts[1] if len(parts) > 1 else None),
                taxa_pre_pct=_f_br(parts[2] if len(parts) > 2 else None),  # noqa: PLR2004
                inflacao_implicita_pct=_f_br(parts[3] if len(parts) > 3 else None),  # noqa: PLR2004
            )
        )
    return rows


# ── Debêntures (daily TXT) ───────────────────────────────────────


async def get_debentures(data_referencia: date | None = None) -> list[DebentureQuote]:
    """Daily secondary-market quotes for outstanding debentures."""
    d = data_referencia or date.today()
    ymd = d.strftime("%y%m%d")
    raw = await get_bytes(DEBENTURES_URL.format(ymd=ymd), cache_ttl=3600)
    text = raw.decode("latin1", errors="replace")
    iso = d.strftime("%Y-%m-%d")
    reader = csv.reader(io.StringIO(text), delimiter="@")
    rows: list[DebentureQuote] = []
    header_seen = False
    for cells in reader:
        if not cells or len(cells) < 14:  # noqa: PLR2004
            continue
        if not header_seen:
            if cells[0].strip().lower().startswith("c") and "nome" in (cells[1] or "").lower():
                header_seen = True
            continue
        rows.append(
            DebentureQuote(
                data_referencia=iso,
                codigo=cells[0].strip(),
                emissor=cells[1].strip(),
                repactuacao_vencimento=cells[2].strip(),
                indice_correcao=cells[3].strip(),
                taxa_compra_pct=_f_br(cells[4]),
                taxa_venda_pct=_f_br(cells[5]),
                taxa_indicativa_pct=_f_br(cells[6]),
                desvio_padrao=_f_br(cells[7]),
                intervalo_min_pct=_f_br(cells[8]),
                intervalo_max_pct=_f_br(cells[9]),
                pu=_f_br(cells[10]),
                pu_par_pct=_f_br(cells[11]),
                duration_du=_f_br(cells[12]),
                pct_reune=_f_br(cells[13]),
                referencia_ntn_b=(
                    (cells[14].strip() or None) if len(cells) > 14 else None  # noqa: PLR2004
                ),
            )
        )
    return rows
