#!/usr/bin/env python3
"""Smoke test for a live deployment or the offline ASGI meta surface."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

import httpx

META_PATHS = ("/health", "/stats", "/meta", "/", "/docs", "/charts", "/openapi.json")
LIVE_PATHS = (*META_PATHS, "/bcb/series/name/selic?n=1", "/mcp")
_HTTP_OK_LT = 300
_HTTP_SERVER_ERR_LT = 500


@dataclass(frozen=True)
class Result:
    path: str
    status: int | None
    color: str
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Live deployment base URL (default: http://127.0.0.1:8000)",
    )
    parser.add_argument(
        "--asgi",
        action="store_true",
        help="Run only offline-safe meta routes against findata.api.app:app",
    )
    return parser.parse_args()


def classify(path: str, status: int | None, error: str | None = None) -> Result:
    if error is not None:
        return Result(path, status, "vermelho", error)
    assert status is not None
    if status < _HTTP_OK_LT:
        color = "verde"
    elif status < _HTTP_SERVER_ERR_LT:
        color = "amarelo"
    else:
        color = "vermelho"
    return Result(path, status, color, "ok" if color == "verde" else "verificar")


def run_requests(paths: tuple[str, ...], get: Callable[[str], httpx.Response]) -> list[Result]:
    results: list[Result] = []
    for path in paths:
        try:
            response = get(path)
        except httpx.HTTPError as exc:
            results.append(classify(path, None, str(exc)))
        else:
            results.append(classify(path, response.status_code))
    return results


def run_asgi() -> list[Result]:
    from fastapi.testclient import TestClient

    from findata.api.app import app

    with TestClient(app) as client:
        return run_requests(META_PATHS, client.get)


def run_live(base_url: str) -> list[Result]:
    with httpx.Client(base_url=base_url.rstrip("/"), timeout=15, follow_redirects=False) as client:
        return run_requests(LIVE_PATHS, client.get)


def print_table(results: list[Result]) -> None:
    print("| rota | status | resultado | detalhe |")
    print("|---|---:|---|---|")
    for result in results:
        status = result.status if result.status is not None else "erro"
        detail = result.detail.replace("|", "\\|").replace("\n", " ")
        print(f"| `{result.path}` | {status} | {result.color} | {detail} |")


def main() -> int:
    args = parse_args()
    results = run_asgi() if args.asgi else run_live(args.base_url)
    print_table(results)
    scoped = [result for result in results if result.path in META_PATHS] if args.asgi else results
    return int(any(result.color == "vermelho" for result in scoped))


if __name__ == "__main__":
    raise SystemExit(main())
