"""Shared async HTTP client with retry, LRU cache, and connection pooling."""

from __future__ import annotations

import asyncio
import hashlib
import ssl
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from urllib.parse import quote

import httpx

# ── LRU Cache with per-entry TTL ─────────────────────────────────

MAX_CACHE_SIZE = 2048
CACHE_TTL = 900  # 15 min default

_cache: OrderedDict[str, tuple[float, float, Any]] = OrderedDict()  # key → (ts, ttl, data)
_locks: dict[tuple[int | None, str], asyncio.Lock] = {}


def _cache_key(kind: str, url: str, params: dict[str, Any] | None) -> str:
    raw = f"{kind}:{url}:{sorted(params.items()) if params else ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> Any | None:
    if key not in _cache:
        return None
    cached_at, ttl, data = _cache[key]
    if time.time() - cached_at < ttl:
        _cache.move_to_end(key)
        return data
    del _cache[key]
    return None


def _cache_set(key: str, data: Any, ttl: float = CACHE_TTL) -> None:
    if ttl <= 0:
        return
    _cache[key] = (time.time(), ttl, data)
    _cache.move_to_end(key)
    while len(_cache) > MAX_CACHE_SIZE:
        _cache.popitem(last=False)


def clear_cache() -> None:
    """Clear the entire in-memory cache. Useful in tests."""
    _cache.clear()
    _locks.clear()


def _loop_id() -> int | None:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return None


def _lock_for(key: str) -> asyncio.Lock:
    scoped_key = (_loop_id(), key)
    lock = _locks.get(scoped_key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[scoped_key] = lock
    return lock


# ── OData URL Builder ─────────────────────────────────────────────

_ODATA_SAFE = "$'@/,()"


def _build_url(url: str, params: dict[str, Any] | None) -> str:
    """Build URL preserving literal $ and @ for OData APIs.

    httpx encodes $ as %24, which BCB Olinda rejects.
    """
    if not params:
        return url
    if not any(k[0] in "$@" for k in params):
        return url
    qs = "&".join(f"{k}={quote(str(v), safe=_ODATA_SAFE)}" for k, v in params.items())
    return f"{url}{'?' if '?' not in url else '&'}{qs}"


# ── Retry ─────────────────────────────────────────────────────────

_HTTP_INTERNAL_ERROR = 500  # lowest 5xx status code
_HTTP_TOO_MANY_REQUESTS = 429


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= _HTTP_INTERNAL_ERROR or status == _HTTP_TOO_MANY_REQUESTS
    return isinstance(exc, httpx.TransportError)


T = TypeVar("T")


async def _retry_loop(fn: Callable[[], Awaitable[T]], retries: int = 3) -> T:
    """Call async `fn()` with exponential backoff on retryable errors."""
    attempts = max(retries, 1)
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if not _should_retry(exc) or attempt >= attempts - 1:
                break
            await asyncio.sleep(2**attempt)
    assert last_exc is not None  # loop always runs at least once
    raise last_exc


# ── Shared Client (event-loop-aware) ──────────────────────────────

_client: httpx.AsyncClient | None = None
_client_loop_id: int | None = None


def _ssl_context() -> Any:
    """SSL context that trusts the OS keystore in addition to certifi.

    Some Brazilian government sites (SUSEP, parts of Receita) sign their
    certs with the ICP-Brasil chain, which isn't in certifi's bundle but
    *is* in macOS / Linux / WSL system keystores. Using ``truststore``
    when available falls through to the system trust store; otherwise we
    use Python's stdlib default (which on most systems also reads the
    OS bundle via ssl.create_default_context()).
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def _get_client() -> httpx.AsyncClient:
    global _client, _client_loop_id
    try:
        loop_id: int | None = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None

    if _client is None or _client.is_closed or _client_loop_id != loop_id:
        _client = httpx.AsyncClient(
            timeout=30,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            headers={"User-Agent": "findata-br/0.1 (+https://github.com/robertoecf/findata-br)"},
            verify=_ssl_context(),
        )
        _client_loop_id = loop_id
    return _client


async def close_client() -> None:
    global _client, _client_loop_id
    if _client and not _client.is_closed:
        await _client.aclose()
    _client = None
    _client_loop_id = None


# ── Public API ────────────────────────────────────────────────────


async def get_json(
    url: str,
    params: dict[str, Any] | None = None,
    cache_ttl: int = CACHE_TTL,
    retries: int = 3,
) -> Any:
    """GET JSON with LRU cache, connection pooling, and smart retry."""
    key = _cache_key("json", url, params)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    async with _lock_for(key):
        cached = _cache_get(key)
        if cached is not None:
            return cached

        full_url = _build_url(url, params)
        use_params = None if full_url != url else params
        client = _get_client()

        async def _do() -> Any:
            resp = await client.get(full_url, params=use_params)
            resp.raise_for_status()
            return resp.json()

        data = await _retry_loop(_do, retries)
        _cache_set(key, data, cache_ttl)
        return data


async def get_bytes(
    url: str,
    retries: int = 3,
    cache_ttl: int = CACHE_TTL,
    max_bytes: int | None = None,
) -> bytes:
    """GET raw bytes (large downloads use a dedicated longer-timeout client)."""
    key = _cache_key("bytes", url, None)
    cached = _cache_get(key)
    if cached is not None:
        if not isinstance(cached, bytes):
            raise TypeError("cached value is not bytes")
        return cached

    async with _lock_for(key):
        cached = _cache_get(key)
        if cached is not None:
            if not isinstance(cached, bytes):
                raise TypeError("cached value is not bytes")
            return cached

        async with httpx.AsyncClient(
            timeout=120,
            headers={"User-Agent": "findata-br/0.1 (+https://github.com/robertoecf/findata-br)"},
            verify=_ssl_context(),
        ) as dl_client:

            async def _do() -> bytes:
                async with dl_client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    length = resp.headers.get("content-length")
                    if max_bytes is not None and length is not None and int(length) > max_bytes:
                        raise ValueError(f"download exceeds max_bytes={max_bytes}")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if max_bytes is not None and total > max_bytes:
                            raise ValueError(f"download exceeds max_bytes={max_bytes}")
                        chunks.append(chunk)
                    return b"".join(chunks)

            data: bytes = await _retry_loop(_do, retries)

        _cache_set(key, data, cache_ttl)
        return data
