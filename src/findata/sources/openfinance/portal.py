"""Open Finance Brasil public indicator Portal resources."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html import unescape
from typing import Literal
from urllib.parse import urljoin

from pydantic import BaseModel, ConfigDict

from findata.http_client import get_bytes, stream_bytes

PORTAL_BASE_URL = "https://dados.openfinancebrasil.org.br"
PORTAL_CACHE_TTL = 3600
DOWNLOAD_MAX_BYTES = 20_000_000

PortalDatasetSlug = Literal[
    "chamadas-por-apis-dados-abertos",
    "chamadas-por-apis-dados-do-cliente",
    "chamadas-por-apis-servicos",
    "consentimentos-ativos",
    "consentimentos-unicos",
    "funil-de-consentimentos",
    "funil-de-pagamentos",
    "ranking-dados-abertos",
    "ranking-dados-do-cliente",
    "ranking-servicos",
]


class OpenFinancePortalDataset(BaseModel):
    """Public dataset listed by the Open Finance data portal."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    title: str
    description: str
    url: str


class OpenFinancePortalFile(BaseModel):
    """Downloadable file listed on a public portal dataset page."""

    model_config = ConfigDict(extra="forbid")

    dataset_slug: str
    title: str
    date_range: str | None = None
    file_type: str | None = None
    download_id: str
    download_url: str


PORTAL_DATASETS: dict[str, OpenFinancePortalDataset] = {
    "chamadas-por-apis-dados-abertos": OpenFinancePortalDataset(
        slug="chamadas-por-apis-dados-abertos",
        title="Chamadas por APIs - Dados Abertos",
        description="Evolução do número total de chamadas das APIs públicas de dados abertos.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/chamadas-por-apis-dados-abertos",
    ),
    "chamadas-por-apis-dados-do-cliente": OpenFinancePortalDataset(
        slug="chamadas-por-apis-dados-do-cliente",
        title="Chamadas por APIs - Dados do Cliente",
        description="Evolução das chamadas de APIs de dados cadastrais e transacionais.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/chamadas-por-apis-dados-do-cliente",
    ),
    "chamadas-por-apis-servicos": OpenFinancePortalDataset(
        slug="chamadas-por-apis-servicos",
        title="Chamadas por APIs - Serviços",
        description="Evolução das chamadas de APIs de serviços no ecossistema.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/chamadas-por-apis-servicos",
    ),
    "consentimentos-ativos": OpenFinancePortalDataset(
        slug="consentimentos-ativos",
        title="Consentimentos Ativos",
        description="Indicadores agregados de consentimentos ativos no Open Finance.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/consentimentos-ativos",
    ),
    "consentimentos-unicos": OpenFinancePortalDataset(
        slug="consentimentos-unicos",
        title="Consentimentos Únicos",
        description="Indicadores agregados de consentimentos únicos.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/consentimentos-unicos",
    ),
    "funil-de-consentimentos": OpenFinancePortalDataset(
        slug="funil-de-consentimentos",
        title="Funil de Consentimentos",
        description="Indicadores agregados da jornada/funil de consentimento.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/funil-de-consentimentos",
    ),
    "funil-de-pagamentos": OpenFinancePortalDataset(
        slug="funil-de-pagamentos",
        title="Funil de Pagamentos",
        description="Indicadores agregados da jornada/funil de pagamentos.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/funil-de-pagamentos",
    ),
    "ranking-dados-abertos": OpenFinancePortalDataset(
        slug="ranking-dados-abertos",
        title="Ranking - Dados Abertos",
        description="Ranking público de indicadores das APIs de dados abertos.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/ranking-dados-abertos",
    ),
    "ranking-dados-do-cliente": OpenFinancePortalDataset(
        slug="ranking-dados-do-cliente",
        title="Ranking - Dados do Cliente",
        description="Ranking público de indicadores das APIs de dados do cliente.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/ranking-dados-do-cliente",
    ),
    "ranking-servicos": OpenFinancePortalDataset(
        slug="ranking-servicos",
        title="Ranking - Serviços",
        description="Ranking público de indicadores das APIs de serviços.",
        url=f"{PORTAL_BASE_URL}/conjuntos-de-dados/ranking-servicos",
    ),
}

_HTML_FILE_RE = re.compile(
    r'<div[^>]*>\s*(CSV|XLSX|JSON)\s*</div>\s*'
    r'<div[^>]*>\s*<p>([^<]+)</p>\s*<p[^>]*>([^<]+)</p>\s*</div>\s*'
    r'<a href="/api/download\?id=([0-9a-fA-F-]+)"',
    re.DOTALL,
)
_HREF_RE = re.compile(r'href="/api/download\?id=([0-9a-fA-F-]+)"')
_TITLE_RE = re.compile(r'children":"(Consolidado [^"]+|Ranking [^"]+)"')
_DATE_RE = re.compile(r'children":"(Dados de [^"]+)"')
_TYPE_RE = re.compile(r'children":"(CSV|XLSX|JSON)"')
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def list_datasets() -> list[OpenFinancePortalDataset]:
    """Return the public Portal dataset catalog supported by this adapter."""
    return list(PORTAL_DATASETS.values())


def _dataset_url(slug: str, page: int = 1) -> str:
    """Build the public Portal page URL for one supported dataset slug."""
    if slug not in PORTAL_DATASETS:
        raise ValueError(f"unknown Open Finance portal dataset: {slug}")
    suffix = f"?page={page}#files" if page > 1 else ""
    return f"{PORTAL_DATASETS[slug].url}{suffix}"


def _nearby_value(values: list[str], index: int) -> str | None:
    """Return the value at an index only when it exists."""
    if not values:
        return None
    if index < len(values):
        return values[index]
    return None


def _safe_download_id(download_id: str) -> str:
    """Validate a Portal download identifier as a UUID."""
    if not _UUID_RE.fullmatch(download_id):
        raise ValueError("invalid Open Finance download_id: expected UUID")
    return download_id


def parse_dataset_files(slug: str, html: str) -> list[OpenFinancePortalFile]:
    """Extract visible CSV download entries from a portal dataset page.

    The Portal is a Next.js app. Its server-rendered HTML contains both regular
    anchors and serialized React payloads; the parser intentionally looks only
    for public `/api/download?id=...` links and nearby display strings.
    """
    files: list[OpenFinancePortalFile] = []
    seen: set[str] = set()

    for file_type, title, date_range, download_id in _HTML_FILE_RE.findall(html):
        seen.add(download_id)
        path = f"/api/download?id={download_id}"
        files.append(
            OpenFinancePortalFile(
                dataset_slug=slug,
                title=unescape(title),
                date_range=unescape(date_range),
                file_type=unescape(file_type),
                download_id=download_id,
                download_url=urljoin(PORTAL_BASE_URL, path),
            )
        )

    ids = _HREF_RE.findall(html)
    titles = [unescape(value) for value in _TITLE_RE.findall(html)]
    ranges = [unescape(value) for value in _DATE_RE.findall(html)]
    types = [unescape(value) for value in _TYPE_RE.findall(html)]

    for index, download_id in enumerate(ids):
        if download_id in seen:
            continue
        seen.add(download_id)
        title = _nearby_value(titles, index) or f"Arquivo {index + 1}"
        date_range = _nearby_value(ranges, index)
        file_type = _nearby_value(types, index) or "CSV"
        path = f"/api/download?id={download_id}"
        files.append(
            OpenFinancePortalFile(
                dataset_slug=slug,
                title=title,
                date_range=date_range,
                file_type=file_type,
                download_id=download_id,
                download_url=urljoin(PORTAL_BASE_URL, path),
            )
        )
    return files


async def get_dataset_files(slug: str, page: int = 1) -> list[OpenFinancePortalFile]:
    """Fetch and parse downloadable files for one public Portal dataset page."""
    raw = await get_bytes(_dataset_url(slug, page), cache_ttl=PORTAL_CACHE_TTL)
    return parse_dataset_files(slug, raw.decode("utf-8", errors="replace"))


async def download_file(download_id: str) -> bytes:
    """Download one public Portal file by id without storing the bytes in cache."""
    safe_id = _safe_download_id(download_id)
    return await get_bytes(
        f"{PORTAL_BASE_URL}/api/download?id={safe_id}",
        cache_ttl=0,
        max_bytes=DOWNLOAD_MAX_BYTES,
    )


def download_filename(download_id: str) -> str:
    """Return a safe default filename for one public Portal download."""
    safe_id = _safe_download_id(download_id)
    return f"{safe_id}.bin"


@asynccontextmanager
async def stream_download_file(download_id: str) -> AsyncIterator[AsyncIterator[bytes]]:
    """Stream one public Portal file by id without caching the payload."""
    safe_id = _safe_download_id(download_id)
    async with stream_bytes(
        f"{PORTAL_BASE_URL}/api/download?id={safe_id}",
        max_bytes=DOWNLOAD_MAX_BYTES,
    ) as chunks:
        yield chunks
