"""Authentication helpers for sources that require credentials.

The Dados Financeiros Abertos public API (BCB, CVM, B3, IBGE, IPEA, Tesouro) is 100% free
and never needs credentials. Some adjacent Brazilian financial data sources
(ANBIMA, SUSEP, BNDES, etc.) gate behind OAuth2 / API keys / bearer tokens
that *the operator* has to bring themselves. This module is the generic
framework those sources plug into.

Design contract
---------------
- The library never embeds, ships, or shares credentials.
- Every auth-gated source reads its credentials from environment variables.
- If the env vars are missing, the source surfaces a clear 503 to API
  callers (or `RuntimeError` to library callers) — never a silent 401.
- Tokens are cached in-process with a safety margin so we never present
  an expired token to the upstream.
"""

from findata.auth.base import AuthError, MissingCredentialsError
from findata.auth.oauth2 import OAuth2ClientCredentials, OAuth2Token

__all__ = [
    "AuthError",
    "MissingCredentialsError",
    "OAuth2ClientCredentials",
    "OAuth2Token",
]
