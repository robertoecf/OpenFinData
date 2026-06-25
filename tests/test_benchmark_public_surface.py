from __future__ import annotations

import importlib.util
import io
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_public_surface.py"
_SPEC = importlib.util.spec_from_file_location("benchmark_public_surface", _SCRIPT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
benchmark = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = benchmark
_SPEC.loader.exec_module(benchmark)


def test_slug_from_url_normalizes_hostname() -> None:
    assert benchmark.slug_from_url("https://www.dadosdemercado.com.br/") == "dadosdemercado_com_br"


def test_fetch_text_records_http_error_status_and_body(monkeypatch: Any) -> None:
    def raise_forbidden(_request: object, timeout: int) -> object:
        raise urllib.error.HTTPError(
            url="https://example.com/robots.txt",
            code=403,
            msg="Forbidden",
            hdrs={"content-type": "text/plain"},
            fp=io.BytesIO(b"blocked"),
        )

    monkeypatch.setattr(benchmark.urllib.request, "urlopen", raise_forbidden)

    result = benchmark.fetch_text("https://example.com/robots.txt")

    assert result.status == 403
    assert result.content_type == "text/plain"
    assert result.body == "blocked"
    assert "HTTPError" in str(result.error)


def test_normalize_url_accepts_page_relative_references() -> None:
    base = "https://www.dadosdemercado.com.br/acoes/petr4"

    assert benchmark.normalize_url("next/data.json", base) == (
        "https://www.dadosdemercado.com.br/acoes/next/data.json"
    )
    assert benchmark.normalize_url("./api/data", base) == (
        "https://www.dadosdemercado.com.br/acoes/api/data"
    )
    assert benchmark.normalize_url("?page=2", base) == (
        "https://www.dadosdemercado.com.br/acoes/petr4?page=2"
    )


def test_html_extraction_keeps_relative_links_without_meta_content_noise() -> None:
    result = benchmark.FetchResult(
        url="https://example.com/base/page",
        status=200,
        content_type="text/html",
        body=(
            '<meta name="viewport" content="width=device-width">'
            '<meta property="og:image" content="/card.png">'
            '<a href="next/data.json">data</a>'
        ),
    )

    assert benchmark.extract_html_urls(result, "https://example.com") == [
        "https://example.com/base/next/data.json",
        "https://example.com/card.png",
    ]


def test_parse_robots_uses_robotparser_allow_rules_and_specific_agent() -> None:
    robots = benchmark.parse_robots(
        """
        User-agent: *
        Disallow: /api/
        Allow: /api/docs

        User-agent: openfindata-public-benchmark
        Disallow: /private/
        Allow: /private/public
        """
    )

    base = "https://www.dadosdemercado.com.br"

    assert robots.blocks(f"{base}/private/data", base)
    assert not robots.blocks(f"{base}/private/public", base)
    assert not robots.blocks(f"{base}/api/search", base)


def test_parse_robots_keeps_group_across_blank_lines() -> None:
    robots = benchmark.parse_robots(
        """
        User-agent: *
        Disallow: /api/

        Allow: /api/public
        """
    )

    base = "https://www.dadosdemercado.com.br"

    assert robots.blocks(f"{base}/api/private", base)
    assert not robots.blocks(f"{base}/api/public", base)


def test_parse_robots_matches_against_product_token_only() -> None:
    robots = benchmark.parse_robots(
        """
        User-agent: *
        Allow: /

        User-agent: github.com
        Disallow: /
        """
    )

    assert not robots.blocks(
        "https://www.dadosdemercado.com.br/fundos",
        "https://www.dadosdemercado.com.br",
    )


def test_collect_sitemap_urls_expands_sitemap_indexes(monkeypatch: Any) -> None:
    root = benchmark.FetchResult(
        url="https://example.com/sitemap.xml",
        status=200,
        content_type="application/xml",
        body=(
            "<sitemapindex>"
            "<sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>"
            "</sitemapindex>"
        ),
    )

    def fake_fetch_text(url: str, timeout: int = 20) -> object:
        assert url == "https://example.com/sitemap-pages.xml"
        return benchmark.FetchResult(
            url=url,
            status=200,
            content_type="application/xml",
            body=(
                "<urlset>"
                "<url><loc>https://example.com/acoes/petr4</loc></url>"
                "<url><loc>https://example.com/indices/ibov</loc></url>"
                "</urlset>"
            ),
        )

    monkeypatch.setattr(benchmark, "fetch_text", fake_fetch_text)

    urls, nested = benchmark.collect_sitemap_urls(
        root,
        "https://example.com",
        benchmark.parse_robots("User-agent: *\nAllow: /\n"),
        sleep_seconds=0.0,
    )

    assert urls == [
        "https://example.com/acoes/petr4",
        "https://example.com/indices/ibov",
    ]
    assert [item.url for item in nested] == ["https://example.com/sitemap-pages.xml"]


def test_parse_sitemap_accepts_prettified_loc_values() -> None:
    assert benchmark.parse_sitemap(
        """
        <urlset>
          <url>
            <loc>
              https://example.com/acoes/petr4
            </loc>
          </url>
        </urlset>
        """
    ) == ["https://example.com/acoes/petr4"]


def test_extract_url_literals_ignores_html_closing_tags() -> None:
    assert benchmark.extract_url_literals(
        """
        <script>fetch('/api/public')</script>
        <div>content</div>
        </body>
        """,
        "https://example.com",
    ) == ["https://example.com/api/public"]


def test_collect_authorized_targets_uses_configured_prefixes_only() -> None:
    targets = benchmark.collect_authorized_targets(
        [
            "https://www.dadosdemercado.com.br/api/foo",
            "https://www.dadosdemercado.com.br/_next/data/build/page.json",
            "https://www.dadosdemercado.com.br/acoes",
            "https://example.com/api/foo",
        ],
        "https://www.dadosdemercado.com.br",
        ["/api/", "/_next/data/"],
    )

    assert targets == [
        "https://www.dadosdemercado.com.br/_next/data/build/page.json",
        "https://www.dadosdemercado.com.br/api/foo",
    ]


def test_build_payload_skips_passive_fetches_when_robots_is_unavailable(monkeypatch: Any) -> None:
    def fake_fetch_text(url: str, timeout: int = 20) -> object:
        if url.endswith("/robots.txt"):
            return benchmark.FetchResult(
                url=url,
                status=403,
                content_type="text/plain",
                body="blocked",
                error="HTTPError 403",
            )
        return benchmark.FetchResult(
            url=url,
            status=200,
            content_type="application/xml",
            body="<urlset><url><loc>https://example.com/acoes</loc></url></urlset>",
        )

    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("passive page/static fetch should be skipped")

    monkeypatch.setattr(benchmark, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(benchmark, "inspect_pages", fail_if_called)
    monkeypatch.setattr(benchmark, "collect_static_assets", fail_if_called)
    monkeypatch.setattr(benchmark, "browser_network_urls", fail_if_called)

    payload = benchmark.build_payload(
        SimpleNamespace(
            base_url="https://example.com/",
            sleep=0.0,
            probe_path_prefix=["/api/"],
            browser_network=True,
            browser_path=["/"],
            chrome=None,
            browser_timeout=1,
            authorized_probe=False,
            probe_max_bytes=benchmark.DEFAULT_API_MAX_BYTES,
            output="docs/snapshots/example_public_surface.json",
            markdown="docs/EXAMPLE_ENDPOINT_BENCHMARK.md",
        )
    )

    assert payload["robots"]["available"] is False
    assert payload["robots"]["disallow"] == []
    assert payload["inspected_pages"] == []
    assert payload["static_assets_fetched"] == []
    assert payload["browser_network"]["enabled"] is False
    assert payload["referenced_urls"]["same_origin_blocked_by_robots"] == []


def test_dadosdemercado_mapping_extends_default_surfaces() -> None:
    mapping = benchmark.infer_findata_mapping("https://www.dadosdemercado.com.br", {})
    surfaces = {item["surface"]: item for item in mapping}

    assert "/fundos" in surfaces
    assert "/tesouro-direto" in surfaces
    assert "/calendario-dividendos" in surfaces
    assert "/agenda-de-dividendos" not in surfaces
    assert surfaces["/boletim-focus"]["findata_routes"] == [
        "/bcb/focus/annual",
        "/bcb/focus/monthly",
        "/bcb/focus/selic",
    ]
