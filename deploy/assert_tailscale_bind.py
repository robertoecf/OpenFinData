#!/usr/bin/env python3
"""Refuse FastAPI publish addresses that are not Tailscale CGNAT.

Compose interpolates TAILSCALE_IP into a host bind. A typo like 0.0.0.0
would publish unauthenticated REST on the public interface.
"""

from __future__ import annotations

import ipaddress
import os
import sys

TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_IPV4 = 4


def allowed_tailscale_bind(raw: str) -> bool:
    try:
        address = ipaddress.ip_address(raw.strip())
    except ValueError:
        return False
    if address.version != _IPV4:
        return False
    if address.is_unspecified or address.is_loopback or address.is_multicast:
        return False
    return address in TAILSCALE_CGNAT


def main() -> int:
    raw = os.environ.get("TAILSCALE_IP", "100.90.45.18")
    if allowed_tailscale_bind(raw):
        return 0
    sys.stderr.write(
        f"TAILSCALE_IP={raw!r} is not a Tailscale CGNAT IPv4 (100.64.0.0/10). "
        "Refusing to bind. Set TAILSCALE_IP to the VPS tailnet address, never 0.0.0.0.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
