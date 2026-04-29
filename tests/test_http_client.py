"""Unit tests for the shared HTTP client — cache, retry, OData URL builder."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from findata import http_client


def test_build_url_preserves_odata_syntax() -> None:
    url = http_client._build_url(
        "https://example/api",
        {"$top": "10", "$filter": "Name eq 'X'", "@x": "'y'"},
    )
    assert "$top=10" in url
    assert "$filter=Name%20eq%20'X'" in url
    assert "@x='y'" in url
    assert "%24" not in url  # $ should not be percent-encoded


def test_build_url_returns_unchanged_for_regular_params() -> None:
    url = http_client._build_url("https://example/api", {"formato": "json"})
    assert url == "https://example/api"


def test_cache_key_is_stable_across_dict_order() -> None:
    k1 = http_client._cache_key("json", "u", {"a": 1, "b": 2})
    k2 = http_client._cache_key("json", "u", {"b": 2, "a": 1})
    assert k1 == k2
    assert k1 != http_client._cache_key("bytes", "u", {"a": 1, "b": 2})


def test_cache_set_get_roundtrip() -> None:
    http_client.clear_cache()
    http_client._cache_set("k", [1, 2, 3], ttl=10)
    assert http_client._cache_get("k") == [1, 2, 3]


def test_cache_evicts_expired_entries() -> None:
    http_client.clear_cache()
    http_client._cache_set("k", "v", ttl=0)
    # Sleep a hair to cross the ttl boundary
    import time

    time.sleep(0.01)
    assert http_client._cache_get("k") is None


def test_cache_eviction_on_overflow() -> None:
    http_client.clear_cache()
    original = http_client.MAX_CACHE_SIZE
    http_client.MAX_CACHE_SIZE = 3
    try:
        for i in range(5):
            http_client._cache_set(f"k{i}", i, ttl=60)
        # Only the 3 most recent should remain.
        assert http_client._cache_get("k0") is None
        assert http_client._cache_get("k1") is None
        assert http_client._cache_get("k4") == 4
    finally:
        http_client.MAX_CACHE_SIZE = original


def test_should_retry_classifies_errors() -> None:
    assert http_client._should_retry(httpx.TransportError("boom")) is True

    resp = httpx.Response(status_code=500)
    exc = httpx.HTTPStatusError("x", request=httpx.Request("GET", "http://x"), response=resp)
    assert http_client._should_retry(exc) is True

    resp_404 = httpx.Response(status_code=404)
    exc_404 = httpx.HTTPStatusError(
        "x",
        request=httpx.Request("GET", "http://x"),
        response=resp_404,
    )
    assert http_client._should_retry(exc_404) is False

    assert http_client._should_retry(ValueError("x")) is False


async def test_retry_loop_succeeds_on_second_attempt() -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise httpx.TransportError("nope")
        return "ok"

    # Monkeypatch sleep to keep test fast
    original_sleep = asyncio.sleep
    asyncio.sleep = lambda _s: original_sleep(0)  # type: ignore[assignment]
    try:
        result = await http_client._retry_loop(flaky, retries=3)
    finally:
        asyncio.sleep = original_sleep  # type: ignore[assignment]
    assert result == "ok"
    assert calls == 2


async def test_retry_loop_raises_after_max_attempts() -> None:
    async def always_fail() -> str:
        raise httpx.TransportError("down")

    original_sleep = asyncio.sleep
    asyncio.sleep = lambda _s: original_sleep(0)  # type: ignore[assignment]
    try:
        with pytest.raises(httpx.TransportError):
            await http_client._retry_loop(always_fail, retries=2)
    finally:
        asyncio.sleep = original_sleep  # type: ignore[assignment]


async def test_retry_loop_does_not_retry_non_retryable() -> None:
    calls = 0

    async def value_error() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("bad")

    with pytest.raises(ValueError):
        await http_client._retry_loop(value_error, retries=5)
    assert calls == 1
