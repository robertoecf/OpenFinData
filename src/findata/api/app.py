"""FastAPI application — REST API + auto-generated MCP server."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.middleware import SlowAPIMiddleware

from findata import __version__ as _pkg_version
from findata._limits import RateLimitExceeded, _rate_limit_exceeded_handler, limiter
from findata.api.routers import (
    anbima,
    aneel,
    b3,
    bcb,
    cvm,
    ibge,
    ipea,
    openfinance,
    receita,
    registry,
    susep,
    tesouro,
)
from findata.http_client import MAX_CACHE_SIZE as _CACHE_MAX
from findata.http_client import _cache as _http_cache
from findata.http_client import close_client

_STARTED_AT = time.time()


def _resolve_version() -> str:
    try:
        return version("findata-br")
    except PackageNotFoundError:
        return _pkg_version


_VERSION = _resolve_version()


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
    title="findata-br",
    description=(
        "Open-source Brazilian financial data API. "
        "Aggregates public data from BCB, CVM, B3, IBGE, IPEA, "
        "Tesouro Nacional, and Open Finance Brasil. "
        "Free. No API key required."
    ),
    version=_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

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


# ── MCP Server (auto-generated from FastAPI endpoints) ─────────────
# Mounted lazily — fastapi_mcp may fail in minimal environments, we don't
# want the whole API to 500 just because the MCP companion isn't ready.
try:
    from fastapi_mcp import FastApiMCP

    _mcp = FastApiMCP(
        app,
        name="findata-br",
        description=(
            "Brazilian financial data MCP server — BCB, CVM, B3, "
            "IBGE, IPEA, Tesouro, Open Finance"
        ),
    )
    _mcp.mount_http()  # Serves MCP at /mcp (fastapi-mcp >=0.4)
    _MCP_ENABLED = True
except Exception:  # optional subsystem must never break core API
    _MCP_ENABLED = False


# ── Health / Root ──────────────────────────────────────────────────


@app.get("/", tags=["Meta"])
async def root() -> dict[str, object]:
    return {
        "name": "findata-br",
        "version": _VERSION,
        "docs": "/docs",
        "mcp": "/mcp" if _MCP_ENABLED else None,
        "sources": {
            "bcb": "Banco Central do Brasil (Selic, IPCA, PTAX, Focus)",
            "cvm": "CVM (companies, financial statements, funds)",
            "tesouro": "Tesouro Direto (treasury bonds)",
            "ibge": "IBGE (economic indicators)",
            "ipea": "IPEA Data (~8k macro series, long historical coverage)",
            "openfinance": "Open Finance Brasil (public Directory + indicator Portal)",
            "b3": "B3 (stock quotes via yfinance)",
            "anbima": "ANBIMA (IMA family, ETTJ, debêntures — public file downloads)",
        },
    }


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
        "sources": ["bcb", "cvm", "tesouro", "ibge", "ipea", "b3"],
        "rate_limits": {
            "enabled": limiter.enabled,
        },
    }
