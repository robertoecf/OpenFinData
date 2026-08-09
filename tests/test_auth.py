"""Unit tests for findata.auth — OAuth2 token cache + missing-creds error."""

from __future__ import annotations

import time

import httpx
import pytest
import respx

from findata.auth import AuthError, MissingCredentialsError, OAuth2ClientCredentials, OAuth2Token


def test_token_is_expired_with_safety_margin() -> None:
    fresh = OAuth2Token(access_token="x", expires_at=time.time() + 3600)
    near_expiry = OAuth2Token(access_token="x", expires_at=time.time() + 30)
    expired = OAuth2Token(access_token="x", expires_at=time.time() - 10)
    assert fresh.is_expired() is False
    assert near_expiry.is_expired() is True  # 30s < 60s safety margin
    assert expired.is_expired() is True


def test_missing_credentials_error_message() -> None:
    err = MissingCredentialsError(source="ANBIMA", env_vars=["A_ID", "A_SEC"])
    msg = str(err)
    assert "ANBIMA" in msg
    assert "A_ID" in msg
    assert "A_SEC" in msg
    assert err.source == "ANBIMA"
    assert err.env_vars == ["A_ID", "A_SEC"]


class _ANBIMA(OAuth2ClientCredentials):
    _token_url = "https://upstream/oauth/access-token"
    header_name = "access_token"
    header_prefix = ""


@respx.mock
async def test_oauth_fetches_then_caches() -> None:
    route = respx.post("https://upstream/oauth/access-token").mock(
        return_value=httpx.Response(201, json={"access_token": "abc", "expires_in": 3600})
    )
    flow = _ANBIMA("cid", "sec")
    async with httpx.AsyncClient() as http:
        t1 = await flow.get_token(http)
        t2 = await flow.get_token(http)  # cache hit
    assert t1.access_token == "abc"
    assert t1 is t2
    assert route.call_count == 1


@respx.mock
async def test_oauth_refreshes_when_expired() -> None:
    route = respx.post("https://upstream/oauth/access-token").mock(
        side_effect=[
            httpx.Response(201, json={"access_token": "first", "expires_in": 0}),
            httpx.Response(201, json={"access_token": "second", "expires_in": 3600}),
        ]
    )
    flow = _ANBIMA("cid", "sec")
    async with httpx.AsyncClient() as http:
        t1 = await flow.get_token(http)
        t2 = await flow.get_token(http)  # first one immediately expired → refresh
    assert t1.access_token == "first"
    assert t2.access_token == "second"
    assert route.call_count == 2


@respx.mock
async def test_oauth_failed_token_request_raises() -> None:
    respx.post("https://upstream/oauth/access-token").mock(
        return_value=httpx.Response(401, json={"error": "invalid_client"})
    )
    flow = _ANBIMA("cid", "wrong")
    async with httpx.AsyncClient() as http:
        with pytest.raises(AuthError):
            await flow.get_token(http)


@respx.mock
async def test_oauth_auth_headers_uses_custom_header() -> None:
    respx.post("https://upstream/oauth/access-token").mock(
        return_value=httpx.Response(201, json={"access_token": "T", "expires_in": 3600})
    )
    flow = _ANBIMA("cid", "sec")
    async with httpx.AsyncClient() as http:
        headers = await flow.auth_headers(http)
    assert headers == {"access_token": "T"}
