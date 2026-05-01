"""FastAPI application — REST API + auto-generated MCP server."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.middleware import SlowAPIMiddleware

from findata import __version__ as _pkg_version
from findata._limits import RateLimitExceeded, _rate_limit_exceeded_handler, limiter
from findata.api.routers import (
    anbima,
    aneel,
    b3,
    basedosdados,
    bcb,
    cvm,
    ibge,
    ipea,
    openfinance,
    receita,
    registry,
    susep,
    tesouro,
    yahoo,
)
from findata.http_client import MAX_CACHE_SIZE as _CACHE_MAX
from findata.http_client import _cache as _http_cache
from findata.http_client import close_client
from findata.web.landing import WEB_STATIC_DIR, render_developer_page, render_landing_page

_STARTED_AT = time.time()
_PROJECT_NAME = "Dados Financeiros Abertos"
_PROJECT_SLUG = "findata-br"


def _resolve_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version(_PROJECT_SLUG)
    except (ImportError, PackageNotFoundError):
        return _pkg_version


_VERSION = _resolve_version()

ADVERTISED_SOURCES: dict[str, str] = {
    "bcb": "Banco Central do Brasil (Selic, IPCA, PTAX, Focus)",
    "basedosdados": "Base dos Dados (free logged-in SQL/Python/R via BigQuery; BD Pro marked paid)",
    "cvm": "CVM (companies, financial statements, funds)",
    "tesouro": "Tesouro Direto (treasury bonds)",
    "ibge": "IBGE (economic indicators)",
    "ipea": "IPEA Data (~8k macro series, long historical coverage)",
    "openfinance": "Open Finance Brasil (public Directory + indicator Portal)",
    "b3": "B3 (stock quotes via yfinance)",
    "yahoo": "Yahoo Finance chart endpoint (experimental, unofficial)",
    "anbima": "ANBIMA (IMA family, ETTJ, debêntures — public file downloads)",
    "receita": "Receita Federal (federal tax collection)",
    "aneel": "ANEEL (generation and transmission auctions)",
    "susep": "SUSEP (supervised insurance entities)",
    "registry": "Offline CNPJ/ticker/name registry",
}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_client()
    # Shut the optional B3 thread pool down only if it was ever created.
    try:
        from findata.sources.b3.quotes import close_executor

        close_executor()
    except ImportError:
        # yfinance not installed — the executor module never loaded.
        pass


app = FastAPI(
    title=_PROJECT_NAME,
    description=(
        "Dados financeiros públicos do Brasil via API, MCP server e CLI. "
        "Agrega dados públicos de BCB, CVM, B3, IBGE, IPEA, "
        "Tesouro Nacional, Base dos Dados, and Open Finance Brasil. "
        "Grátis. Sem chave de API."
    ),
    version=_VERSION,
    docs_url="/api/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.mount("/site", StaticFiles(directory=WEB_STATIC_DIR), name="site")

# Attach the SlowAPI limiter so routes can use the `limiter` dependency and
# the middleware can short-circuit requests that exceed the bucket. Disabled
# when FINDATA_RATE_LIMIT_ENABLED=false (useful for local dev).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(ValueError)
async def _value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ── Routers ────────────────────────────────────────────────────────

app.include_router(bcb.router)
app.include_router(basedosdados.router)
app.include_router(cvm.router)
app.include_router(tesouro.router)
app.include_router(ibge.router)
app.include_router(ipea.router)
app.include_router(openfinance.router)
app.include_router(b3.router)
app.include_router(anbima.router)
app.include_router(receita.router)
app.include_router(aneel.router)
app.include_router(susep.router)
app.include_router(registry.router)
app.include_router(yahoo.router)


# ── MCP Server (auto-generated from FastAPI endpoints) ─────────────
# Mounted lazily — fastapi_mcp may fail in minimal environments, we don't
# want the whole API to 500 just because the MCP companion isn't ready.
try:
    from fastapi_mcp import FastApiMCP

    _mcp = FastApiMCP(
        app,
        name=_PROJECT_SLUG,
        description=(
            "Dados financeiros públicos do Brasil via MCP — BCB, CVM, B3, "
            "IBGE, IPEA, Tesouro, Base dos Dados, Open Finance, Yahoo experimental charts"
        ),
    )
    _mcp.mount_http()  # Serves MCP at /mcp (fastapi-mcp >=0.4)
    _MCP_ENABLED = True
except Exception:  # optional subsystem must never break core API
    _MCP_ENABLED = False


# ── Health / Root ──────────────────────────────────────────────────


def _meta_payload() -> dict[str, object]:
    return {
        "name": _PROJECT_NAME,
        "slug": _PROJECT_SLUG,
        "version": _VERSION,
        "site": "/",
        "docs": "/docs",
        "swagger": "/api/docs",
        "redoc": "/redoc",
        "mcp": "/mcp" if _MCP_ENABLED else None,
        "sources": ADVERTISED_SOURCES,
    }


@app.get("/", include_in_schema=False)
async def root() -> HTMLResponse:
    return render_landing_page(
        version=_VERSION,
        sources=ADVERTISED_SOURCES,
        mcp_enabled=_MCP_ENABLED,
    )


@app.get("/docs", include_in_schema=False)
async def developer_docs() -> HTMLResponse:
    return render_developer_page(
        version=_VERSION,
        sources=ADVERTISED_SOURCES,
        mcp_enabled=_MCP_ENABLED,
    )


@app.get("/meta", tags=["Meta"])
async def meta() -> dict[str, object]:
    """Machine-readable API and site metadata."""
    return _meta_payload()


@app.get("/health", tags=["Meta"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": _VERSION}


@app.get("/stats", tags=["Meta"])
async def stats() -> dict[str, object]:
    """Observability snapshot for the public deployment.

    Cheap enough to hit from a status page or a scraping script; returns
    the same info you'd otherwise have to SSH in to get.
    """
    return {
        "version": _VERSION,
        "uptime_seconds": int(time.time() - _STARTED_AT),
        "mcp_enabled": _MCP_ENABLED,
        "cache": {
            "size": len(_http_cache),
            "max_size": _CACHE_MAX,
        },
        "sources": list(ADVERTISED_SOURCES),
        "rate_limits": {
            "enabled": limiter.enabled,
        },
    }
