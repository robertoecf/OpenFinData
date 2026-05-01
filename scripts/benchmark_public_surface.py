#!/usr/bin/env python3
"""Audit a public financial-data website as a benchmark for Dados Financeiros Abertos.

Default mode is conservative: read public pages, public static assets,
robots.txt, and sitemap.xml. Same-origin paths blocked by robots.txt are
recorded when referenced but fetched only with explicit authorization flags.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html.parser
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://www.dadosdemercado.com.br"
USER_AGENT = (
    "findata-br-public-benchmark/0.2 "
    "(+https://github.com/robertoecf/findata-br)"
)
HTTP_OK = 200
DEFAULT_API_MAX_BYTES = 256 * 1024
MAX_JSON_SHAPE_DEPTH = 3
DEFAULT_MAX_SITEMAPS = 50
DEFAULT_PROBE_PATH_PREFIXES = ["/api/", "/_next/data/"]
CORE_PATHS = [
    "/",
    "/fundos",
    "/tesouro-direto",
    "/tesouro-direto/curva",
    "/debentures",
    "/acoes",
    "/bdr",
    "/etfs",
    "/fiis",
    "/indices",
    "/comparar",
    "/comparar-ativos",
    "/calendario-dividendos",
    "/blog",
    "/glossario",
    "/metodologia",
    "/status",
]
IGNORED_BROWSER_HOSTS = {
    "accounts.google.com",
    "android.clients.google.com",
    "clients2.google.com",
    "content-autofill.googleapis.com",
    "google.com",
    "safebrowsingohttpgateway.googleapis.com",
    "www.google.com",
}
DEFAULT_FINDATA_MAPPING = [
    {
        "surface": "/fundos",
        "findata_routes": [
            "/cvm/funds",
            "/cvm/funds/daily",
            "/cvm/funds/holdings",
            "/cvm/funds/lamina",
            "/cvm/funds/profile",
        ],
        "status": "covered_raw_routes",
    },
    {
        "surface": "/tesouro-direto",
        "findata_routes": ["/tesouro/bonds", "/tesouro/bonds/search", "/tesouro/bonds/history"],
        "status": "covered_raw_routes",
    },
    {
        "surface": "/tesouro-direto/curva",
        "findata_routes": ["/tesouro/bonds"],
        "status": "derive_from_existing",
    },
    {
        "surface": "/debentures",
        "findata_routes": ["/anbima/debentures"],
        "status": "partial_verify_events_ratings",
    },
    {
        "surface": "/acoes",
        "findata_routes": [
            "/b3/quote/{ticker}",
            "/b3/cotahist/day/{year}/{month}/{day}",
            "/cvm/companies/fca/securities",
            "/registry/lookup",
        ],
        "status": "covered_needs_product_view",
    },
    {
        "surface": "/fiis",
        "findata_routes": ["/cvm/funds/fii/geral", "/cvm/funds/fii/complemento"],
        "status": "covered_raw_routes",
    },
    {
        "surface": "/indices",
        "findata_routes": ["/b3/indices", "/b3/indices/{symbol}"],
        "status": "composition_covered_values_need_audit",
    },
    {
        "surface": "/calendario-dividendos",
        "findata_routes": [],
        "status": "gap_b3_corporate_events",
    },
    {
        "surface": "/etfs and /bdr",
        "findata_routes": ["/b3/cotahist/*", "/registry/lookup"],
        "status": "gap_official_product_taxonomy",
    },
]


@dataclass
class FetchResult:
    url: str
    status: int | None
    content_type: str | None
    body: str
    error: str | None = None


@dataclass
class UrlBucket:
    urls: set[str] = field(default_factory=set)

    def add(self, url: str, base: str) -> None:
        normalized = normalize_url(url, base)
        if normalized:
            self.urls.add(normalized)

    def sorted(self) -> list[str]:
        return sorted(self.urls)


@dataclass
class LimitedFetch:
    url: str
    status: int | None
    content_type: str | None
    headers: dict[str, str]
    body: bytes
    truncated: bool
    error: str | None = None


@dataclass
class RobotsDirective:
    kind: str
    pattern: str

    @property
    def specificity(self) -> int:
        return len(self.pattern.rstrip("$").replace("*", ""))


@dataclass
class RobotsGroup:
    agents: list[str]
    directives: list[RobotsDirective]


class LinkParser(html.parser.HTMLParser):
    """Small HTML URL extractor for public href/src/content attributes."""

    def __init__(self, base: str) -> None:
        super().__init__()
        self.base = base
        self.urls = UrlBucket()

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            name_lower = name.lower()
            if value and (
                name_lower in {"href", "src"}
                or (name_lower == "content" and is_likely_content_url(value))
            ):
                self.urls.add(value, self.base)


class RobotsRules:
    def __init__(
        self,
        disallow: list[str],
        groups: list[RobotsGroup] | None = None,
    ) -> None:
        self.disallow = [rule for rule in disallow if rule]
        self.groups = groups or [
            RobotsGroup(
                agents=["*"],
                directives=[RobotsDirective("disallow", rule) for rule in self.disallow],
            )
        ]

    def blocks(self, url: str, base_url: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        base_host = urllib.parse.urlparse(base_url).netloc
        if parsed.netloc and parsed.netloc != base_host:
            return False
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return robots_path_blocked(path, self.groups, USER_AGENT)


def fetch_text(url: str, timeout: int = 20) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", "replace")
            return FetchResult(
                url=url,
                status=response.status,
                content_type=response.headers.get("content-type"),
                body=body,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return FetchResult(
            url=url,
            status=exc.code,
            content_type=exc.headers.get("content-type"),
            body=body,
            error=repr(exc),
        )
    except Exception as exc:  # public benchmark should keep going on 404/timeout
        return FetchResult(url=url, status=None, content_type=None, body="", error=repr(exc))


def fetch_limited_bytes(
    url: str, max_bytes: int = DEFAULT_API_MAX_BYTES, timeout: int = 20
) -> LimitedFetch:
    """GET a URL but retain only a bounded prefix of the response body."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
            "Range": f"bytes=0-{max_bytes - 1}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            return LimitedFetch(
                url=url,
                status=response.status,
                content_type=response.headers.get("content-type"),
                headers=safe_headers(dict(response.headers.items())),
                body=body[:max_bytes],
                truncated=len(body) > max_bytes,
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(max_bytes + 1)
        return LimitedFetch(
            url=url,
            status=exc.code,
            content_type=exc.headers.get("content-type"),
            headers=safe_headers(dict(exc.headers.items())),
            body=body[:max_bytes],
            truncated=len(body) > max_bytes,
            error=exc.reason,
        )
    except Exception as exc:
        return LimitedFetch(
            url=url,
            status=None,
            content_type=None,
            headers={},
            body=b"",
            truncated=False,
            error=repr(exc),
        )


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    keep = {
        "cache-control",
        "content-type",
        "etag",
        "last-modified",
        "vary",
        "x-nextjs-cache",
    }
    return {key.lower(): value for key, value in headers.items() if key.lower() in keep}


def normalize_url(value: str, base: str) -> str | None:
    value = value.strip()
    if not value or value.startswith(("mailto:", "tel:", "data:", "javascript:", "#")):
        return None
    if value.startswith("//"):
        value = "https:" + value
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    return urllib.parse.urljoin(base, value)


def is_likely_content_url(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith(("http://", "https://", "//", "/", "./", "../", "?"))


def parse_robots(body: str) -> RobotsRules:
    return RobotsRules(collect_disallow_rules(body), parse_robots_groups(body))


def parse_robots_groups(body: str) -> list[RobotsGroup]:
    groups: list[RobotsGroup] = []
    agents: list[str] = []
    directives: list[RobotsDirective] = []
    seen_directive = False
    for raw_line in body.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        key_lower = key.lower()
        if key_lower == "user-agent":
            if seen_directive:
                agents, directives, seen_directive = flush_robots_group(
                    groups, agents, directives
                )
            agents.append(value.lower())
        elif key_lower in {"allow", "disallow"} and agents:
            seen_directive = True
            if value:
                directives.append(RobotsDirective(key_lower, value))
    flush_robots_group(groups, agents, directives)
    return groups


def flush_robots_group(
    groups: list[RobotsGroup],
    agents: list[str],
    directives: list[RobotsDirective],
) -> tuple[list[str], list[RobotsDirective], bool]:
    if agents:
        groups.append(RobotsGroup(agents=agents, directives=directives))
    return [], [], False


def robots_path_blocked(path: str, groups: list[RobotsGroup], user_agent: str) -> bool:
    directives = matching_robots_directives(groups, user_agent)
    matching = [rule for rule in directives if robots_pattern_matches(rule.pattern, path)]
    if not matching:
        return False
    winner = max(matching, key=lambda rule: (rule.specificity, rule.kind == "allow"))
    return winner.kind == "disallow"


def matching_robots_directives(
    groups: list[RobotsGroup], user_agent: str
) -> list[RobotsDirective]:
    best_specificity = -1
    selected: list[RobotsDirective] = []
    for group in groups:
        specificity = max(
            (agent_specificity(agent, user_agent) for agent in group.agents),
            default=-1,
        )
        if specificity > best_specificity:
            best_specificity = specificity
            selected = group.directives.copy()
        elif specificity == best_specificity:
            selected.extend(group.directives)
    return selected if best_specificity >= 0 else []


def agent_specificity(agent: str, user_agent: str) -> int:
    if agent == "*":
        return 0
    product_token = user_agent_product_token(user_agent)
    return len(agent) if agent in product_token else -1


def user_agent_product_token(user_agent: str) -> str:
    token = user_agent.strip().split(maxsplit=1)[0]
    return token.split("/", 1)[0].lower()


def robots_pattern_matches(pattern: str, path: str) -> bool:
    if not pattern:
        return False
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = re.escape(body).replace(r"\*", ".*")
    if anchored:
        regex = f"{regex}$"
    return re.match(regex, path) is not None


def collect_disallow_rules(body: str) -> list[str]:
    disallow: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = [part.strip() for part in line.split(":", 1)]
        if key.lower() == "disallow" and value and value not in disallow:
            disallow.append(value)
    return disallow


def parse_sitemap(body: str) -> list[str]:
    return [match.strip() for match in re.findall(r"<loc>\s*(.*?)\s*</loc>", body, re.DOTALL)]


def is_sitemap_index(body: str) -> bool:
    return "<sitemapindex" in body.lower()


def collect_sitemap_urls(
    root_result: FetchResult,
    base_url: str,
    robots: RobotsRules,
    sleep_seconds: float,
    max_sitemaps: int = DEFAULT_MAX_SITEMAPS,
) -> tuple[list[str], list[FetchResult]]:
    root_locs = parse_sitemap(root_result.body)
    if not is_sitemap_index(root_result.body):
        return root_locs, []

    page_urls: set[str] = set()
    fetched_sitemaps: list[FetchResult] = []
    seen = {root_result.url}
    pending = root_locs[:max_sitemaps]
    while pending and len(fetched_sitemaps) < max_sitemaps:
        raw_url = pending.pop(0)
        sitemap_url = normalize_url(raw_url, root_result.url or base_url)
        if not sitemap_url or sitemap_url in seen or robots.blocks(sitemap_url, base_url):
            continue
        seen.add(sitemap_url)
        time.sleep(sleep_seconds)
        result = fetch_text(sitemap_url)
        fetched_sitemaps.append(result)
        locs = parse_sitemap(result.body)
        if is_sitemap_index(result.body):
            pending.extend(locs)
        else:
            page_urls.update(locs)
    return sorted(page_urls), fetched_sitemaps


def route_bucket(url: str, base_url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    base_host = urllib.parse.urlparse(base_url).netloc
    if parsed.netloc != base_host:
        return f"external:{parsed.netloc}"
    parts = [part for part in parsed.path.split("/") if part]
    return "/" + parts[0] if parts else "/"


def summarize_counts(urls: list[str], base_url: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for url in urls:
        bucket = route_bucket(url, base_url)
        counts[bucket] = counts.get(bucket, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def extract_html_urls(result: FetchResult, base_url: str) -> list[str]:
    parser = LinkParser(result.url or base_url)
    parser.feed(result.body)
    return parser.urls.sorted()


def extract_url_literals(text: str, base_url: str) -> list[str]:
    candidates = UrlBucket()
    for match in re.finditer(r"https?://[^\s'\"\\)<>]+|/[A-Za-z0-9_./?=&:%~-]+", text):
        if match.start() > 0 and text[match.start() - 1] == "<":
            continue
        value = match.group(0).rstrip(".,;]")
        candidates.add(value, base_url)
    return candidates.sorted()


def split_url_inventory(
    urls: list[str], base_url: str, robots: RobotsRules
) -> dict[str, list[str]]:
    base_host = urllib.parse.urlparse(base_url).netloc
    buckets: dict[str, set[str]] = {
        "same_origin_public": set(),
        "same_origin_blocked_by_robots": set(),
        "third_party": set(),
    }
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc == base_host:
            key = (
                "same_origin_blocked_by_robots"
                if robots.blocks(url, base_url)
                else "same_origin_public"
            )
            buckets[key].add(redact_url(url))
        else:
            buckets["third_party"].add(redact_url(url))
    return {key: sorted(value) for key, value in buckets.items()}


def collect_authorized_targets(
    urls: list[str], base_url: str, path_prefixes: list[str]
) -> list[str]:
    """Return same-origin API-like URLs that were referenced publicly."""
    base = urllib.parse.urlparse(base_url)
    targets: set[str] = set()
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc == base.netloc and any(
            parsed.path.startswith(prefix) for prefix in path_prefixes
        ):
            targets.add(url)
    return sorted(targets)


def probe_authorized_targets(
    targets: list[str], sleep_seconds: float, max_bytes: int
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for url in targets:
        time.sleep(sleep_seconds)
        result = fetch_limited_bytes(url, max_bytes=max_bytes)
        results.append(authorized_probe_summary(result, max_bytes))
    return results


def authorized_probe_summary(result: LimitedFetch, max_bytes: int) -> dict[str, object]:
    body_hash = hashlib.sha256(result.body).hexdigest() if result.body else None
    summary: dict[str, object] = {
        "url": redact_url(result.url),
        "status": result.status,
        "content_type": result.content_type,
        "headers": result.headers,
        "bytes_read": len(result.body),
        "max_bytes": max_bytes,
        "truncated": result.truncated,
        "sha256": body_hash,
        "error": result.error,
    }
    summary.update(summarize_body(result.body, result.content_type, result.truncated))
    return summary


def summarize_body(
    body: bytes, content_type: str | None, truncated: bool
) -> dict[str, object]:
    if not body:
        return {"body_kind": "empty"}
    text = body.decode("utf-8", "replace")
    if content_type and "json" in content_type:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            return {
                "body_kind": "json_unparsed",
                "parse_error": str(exc),
                "truncated": truncated,
            }
        return {"body_kind": "json", "json_shape": json_shape(parsed)}
    return {
        "body_kind": "text",
        "preview": re.sub(r"\s+", " ", text[:300]).strip(),
    }


def json_shape(value: object, depth: int = 0) -> dict[str, object]:
    if depth >= MAX_JSON_SHAPE_DEPTH:
        return {"type": type(value).__name__}
    if isinstance(value, dict):
        keys = sorted(str(key) for key in value)
        properties = {
            str(key): json_shape(item, depth + 1)
            for key, item in list(value.items())[:25]
        }
        return {
            "type": "object",
            "keys": keys[:50],
            "key_count": len(keys),
            "properties": properties,
        }
    if isinstance(value, list):
        first_item = next((item for item in value if item is not None), None)
        return {
            "type": "array",
            "observed_length": len(value),
            "item_shape": json_shape(first_item, depth + 1) if first_item is not None else None,
        }
    if value is None:
        return {"type": "null"}
    return {"type": type(value).__name__}


def collect_static_assets(
    pages: list[FetchResult], base_url: str, robots: RobotsRules, sleep_seconds: float
) -> tuple[list[FetchResult], list[str]]:
    asset_urls: set[str] = set()
    base_host = urllib.parse.urlparse(base_url).netloc
    for page in pages:
        for url in extract_html_urls(page, base_url):
            parsed = urllib.parse.urlparse(url)
            if (
                parsed.netloc == base_host
                and is_static_asset(parsed.path)
                and not robots.blocks(url, base_url)
            ):
                asset_urls.add(url)
    results = []
    literals: set[str] = set()
    for url in sorted(asset_urls):
        time.sleep(sleep_seconds)
        result = fetch_text(url)
        results.append(result)
        if result.body and is_text_asset(result.content_type):
            literals.update(
                url
                for url in extract_url_literals(result.body, base_url)
                if keep_referenced_literal(url, base_url)
            )
    return results, sorted(literals)




def keep_referenced_literal(url: str, base_url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    base_host = urllib.parse.urlparse(base_url).netloc
    source_hosts = {
        "dados.cvm.gov.br",
        "www.b3.com.br",
        "www.tesourotransparente.gov.br",
    }
    return parsed.netloc == base_host or "posthog" in parsed.netloc or parsed.netloc in source_hosts


def is_static_asset(path: str) -> bool:
    return path.startswith("/_next/static/") or path in {
        "/manifest.webmanifest",
        "/icon.svg",
        "/icon1",
        "/icon2",
        "/apple-icon",
    }


def is_text_asset(content_type: str | None) -> bool:
    if not content_type:
        return False
    return any(kind in content_type for kind in ("javascript", "css", "json", "text"))


def inspect_pages(base_url: str, robots: RobotsRules, sleep_seconds: float) -> list[FetchResult]:
    results: list[FetchResult] = []
    for path in CORE_PATHS:
        url = urllib.parse.urljoin(base_url, path)
        if robots.blocks(url, base_url):
            continue
        time.sleep(sleep_seconds)
        results.append(fetch_text(url))
    return results


def find_chrome(explicit_path: str | None) -> str | None:
    candidates = [
        explicit_path,
        os.environ.get("CHROME"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    return next(
        (str(candidate) for candidate in candidates if candidate and Path(candidate).exists()),
        None,
    )


def browser_network_urls(
    base_url: str,
    paths: list[str],
    chrome_path: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    chrome = find_chrome(chrome_path)
    if not chrome:
        return {"enabled": False, "error": "Chrome executable not found", "urls": []}
    urls: set[str] = set()
    runs: list[dict[str, object]] = []
    for path in paths:
        url = urllib.parse.urljoin(base_url, path)
        with tempfile.TemporaryDirectory(prefix="findata-benchmark-chrome-") as tmp:
            netlog = Path(tmp) / "netlog.json"
            profile = Path(tmp) / "profile"
            command = chrome_command(chrome, profile, netlog, url)
            status = run_chrome(command, timeout_seconds)
            page_urls = parse_netlog_urls(netlog)
            urls.update(page_urls)
            runs.append({"url": url, "status": status, "captured_url_count": len(page_urls)})
    filtered = sorted({redact_url(url) for url in urls if keep_browser_url(url, base_url)})
    return {"enabled": True, "runs": runs, "urls": filtered}


def chrome_command(chrome: str, profile: Path, netlog: Path, url: str) -> list[str]:
    return [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--disable-sync",
        "--disable-extensions",
        "--disable-default-apps",
        "--disable-background-networking",
        f"--user-data-dir={profile}",
        f"--log-net-log={netlog}",
        "--net-log-capture-mode=Default",
        "--virtual-time-budget=5000",
        "--dump-dom",
        url,
    ]


def run_chrome(command: list[str], timeout_seconds: int) -> str:
    process = subprocess.Popen(  # noqa: S603 - operator-provided local Chrome command
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        process.wait(timeout=timeout_seconds)
        return "completed" if process.returncode == 0 else f"exit_{process.returncode}"
    except subprocess.TimeoutExpired:
        # Terminating the browser process (rather than immediately killing the
        # full group) gives Chrome a chance to flush a complete netlog.
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)
        return "timeout_killed_after_capture"


def parse_netlog_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        with path.open() as fh:
            payload = json.load(fh)
    except json.JSONDecodeError:
        text = path.read_text(errors="ignore")
        return {
            match.group(0).rstrip("\\,")
            for match in re.finditer(r"https?://[^\s'\"<>]+", text)
        }
    urls: set[str] = set()
    for event in payload.get("events", []):
        walk_netlog(event.get("params", {}), urls)
    return urls


def walk_netlog(value: object, urls: set[str]) -> None:
    if isinstance(value, str) and value.startswith("http"):
        urls.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            walk_netlog(item, urls)
    elif isinstance(value, list):
        for item in value:
            walk_netlog(item, urls)


def keep_browser_url(url: str, base_url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc in IGNORED_BROWSER_HOSTS:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    return parsed.netloc == urllib.parse.urlparse(base_url).netloc or "posthog" in parsed.netloc


def redact_url(url: str) -> str:
    url = re.sub(r"phc_[A-Za-z0-9]+", "phc_REDACTED_PUBLIC_PROJECT_KEY", url)
    parsed = urllib.parse.urlparse(url)
    if parsed.query:
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        safe_query = [(key, "<token>" if key == "_rsc" else value) for key, value in query]
        return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(safe_query)))
    return url


def build_report(payload: dict[str, Any]) -> str:
    sitemap = payload["sitemap"]
    browser = payload["browser_network"]
    authorized_probe = payload["authorized_probe"]
    robots = payload["robots"]
    blocked_label = "Blocked by robots"
    if authorized_probe.get("enabled"):
        blocked_label = "Blocked by robots unless authorized"
    lines = [
        "# Public endpoint benchmark",
        "",
        f"Consulta: {payload['consulted_at']}",
        f"Referência pública: {payload['base_url']}",
        "",
        "## Policy boundary",
        "",
        "This benchmark uses public pages, public static assets, `robots.txt`, ",
        "and `sitemap.xml`. Same-origin paths blocked by robots are recorded. ",
        "They are fetched only when `--authorized-probe` is explicitly passed. ",
        "The current robots policy includes:",
        "",
    ]
    for rule in robots["disallow"] or ["(none)"]:
        lines.append(f"- `{rule}`")
    lines.extend(robots_status_report_lines(robots))
    lines.extend(
        [
            "",
            "## Public route inventory",
            "",
            f"Total sitemap URLs: {sitemap['url_count']}",
            "",
            "| Section | URLs |",
            "|---|---:|",
        ]
    )
    for section, count in sitemap["by_section"].items():
        lines.append(f"| `{section}` | {count} |")
    lines.extend(nested_sitemap_report_lines(sitemap))
    lines.extend(
        [
            "",
            "## Browser-observed fetches",
            "",
        ]
    )
    if browser.get("enabled"):
        lines.append("Headless Chrome was used to load selected public pages.")
        lines.append("")
        lines.append(f"Captured filtered URLs: {len(browser['urls'])}")
        lines.append("")
        lines.append("Key same-origin request families observed:")
        lines.append("")
        for family in payload["browser_network_summary"].items():
            lines.append(f"- `{family[0]}`: {family[1]}")
    else:
        lines.append(f"Browser capture was skipped: {browser.get('error', 'not requested')}.")
    lines.extend(
        [
            "",
            "## Same-origin endpoints referenced by inspected public pages/assets",
            "",
            "| Type | Count |",
            "|---|---:|",
        ]
    )
    public_count = len(payload["referenced_urls"]["same_origin_public"])
    blocked_count = len(payload["referenced_urls"]["same_origin_blocked_by_robots"])
    third_count = len(payload["referenced_urls"]["third_party"])
    lines.append(f"| Public same-origin | {public_count} |")
    lines.append(f"| {blocked_label} | {blocked_count} |")
    lines.append(f"| Third-party | {third_count} |")
    blocked = payload["referenced_urls"]["same_origin_blocked_by_robots"]
    if blocked:
        blocked_heading = "### Referenced paths governed by robots policy"
        if not authorized_probe.get("enabled"):
            blocked_heading = "### Referenced but not fetched due robots policy"
        lines.extend(
            [
                "",
                blocked_heading,
                "",
            ]
        )
        for url in blocked:
            parsed = urllib.parse.urlparse(url)
            path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
            lines.append(f"- `{path}`")
    lines.extend(authorized_probe_report_lines(authorized_probe))
    lines.extend(
        [
            "",
            "## Product benchmark mapping",
            "",
            "| Benchmark surface | Dados Financeiros Abertos route(s) | Status |",
            "|---|---|---|",
        ]
    )
    for item in payload["findata_mapping"]:
        routes = ", ".join(f"`{route}`" for route in item["findata_routes"]) or "—"
        lines.append(f"| `{item['surface']}` | {routes} | {item['status']} |")
    lines.extend(
        [
            "",
            "## Recommended next implementation order",
            "",
            "1. Add a first-class status/freshness route using existing `/health` "
            "and `/stats` as base.",
            "2. Add productized views over existing raw routes: funds, Tesouro, equities, indices.",
            "3. Add official B3 corporate-events/dividend source before building a calendar UI.",
            "4. Generate static docs snapshots rather than adding a frontend dependency stack.",
            "",
            f"Full machine-readable inventory: `{payload['artifact_paths']['json']}`.",
            "",
        ]
    )
    return "\n".join(lines)


def robots_status_report_lines(robots: dict[str, object]) -> list[str]:
    if robots["available"]:
        return []
    return [
        "",
        f"Robots status: `{robots['status']}`. Passive page/static/browser "
        "inspection was skipped because robots policy could not be confirmed.",
    ]


def nested_sitemap_report_lines(sitemap: dict[str, object]) -> list[str]:
    nested_sitemaps = sitemap.get("nested_sitemaps", [])
    if not nested_sitemaps:
        return []
    return ["", f"Nested sitemap files fetched: {len(nested_sitemaps)}"]


def authorized_probe_report_lines(authorized_probe: dict[str, object]) -> list[str]:
    lines = ["", "## Authorized API probe", ""]
    if not authorized_probe.get("enabled"):
        return [*lines, "Not run. Pass `--authorized-probe` only with owner permission."]

    results = authorized_probe.get("results")
    assert isinstance(results, list)
    lines.extend(
        [
            "Owner-authorized mode was enabled. Scope: GET-only, referenced "
            "same-origin API-like paths only, no fuzzing, no auth bypass, no mutation, "
            f"max body retained per response: {authorized_probe.get('max_bytes')} bytes.",
            "",
            f"Targets probed: {len(results)}",
            "",
            "| Path | Status | Bytes | Truncated | Body kind | Schema summary |",
            "|---|---:|---:|---|---|---|",
        ]
    )
    for item in results:
        assert isinstance(item, dict)
        parsed = urllib.parse.urlparse(str(item["url"]))
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        schema = compact_schema_summary(item)
        lines.append(
            "| "
            f"`{path}` | {item.get('status')} | {item.get('bytes_read')} | "
            f"{item.get('truncated')} | {item.get('body_kind')} | {schema} |"
        )
    return lines


def compact_schema_summary(item: dict[str, object]) -> str:
    shape = item.get("json_shape")
    if not isinstance(shape, dict):
        return "—"
    top_type = shape.get("type")
    if top_type == "array":
        item_shape = shape.get("item_shape")
        if isinstance(item_shape, dict) and item_shape.get("type") == "object":
            keys = item_shape.get("keys", [])
            return f"array<object: {', '.join(str(key) for key in keys[:8])}>"
        return f"array<{item_shape}>"
    if top_type == "object":
        properties = shape.get("properties")
        if isinstance(properties, dict):
            for collection_key in ("items", "points"):
                collection = properties.get(collection_key)
                if isinstance(collection, dict) and collection.get("type") == "array":
                    item_shape = collection.get("item_shape")
                    if isinstance(item_shape, dict) and item_shape.get("type") == "object":
                        keys = item_shape.get("keys", [])
                        return (
                            f"object<{collection_key}: "
                            f"{', '.join(str(key) for key in keys[:10])}>"
                        )
        keys = shape.get("keys", [])
        return f"object: {', '.join(str(key) for key in keys[:10])}"
    return str(top_type)


def browser_summary(urls: list[str], base_url: str) -> dict[str, int]:
    base_host = urllib.parse.urlparse(base_url).netloc
    summary: dict[str, int] = {}
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc == base_host:
            key = parsed.path or "/"
            if parsed.query.startswith("_rsc="):
                key = f"{parsed.path}?_rsc"
            elif parsed.path.startswith("/_next/static/chunks"):
                key = "/_next/static/chunks/*"
            elif parsed.path.startswith("/_next/static/media"):
                key = "/_next/static/media/*"
        else:
            key = f"external:{parsed.netloc}"
        summary[key] = summary.get(key, 0) + 1
    return dict(sorted(summary.items(), key=lambda item: (-item[1], item[0])))


def infer_findata_mapping(base_url: str, sitemap_counts: dict[str, int]) -> list[dict[str, object]]:
    if "dadosdemercado.com.br" in urllib.parse.urlparse(base_url).netloc:
        return [
            *DEFAULT_FINDATA_MAPPING,
            {
                "surface": "/boletim-focus",
                "findata_routes": ["/bcb/focus/annual", "/bcb/focus/monthly", "/bcb/focus/selic"],
                "status": "covered_raw_routes",
            },
            {
                "surface": "/bitcoin",
                "findata_routes": [],
                "status": "out_of_scope_or_future_crypto",
            },
        ]
    mapped = []
    for section in sitemap_counts:
        if section in {"/acoes", "/indices", "/fundos"}:
            mapped.append({"surface": section, "findata_routes": [], "status": "needs_mapping"})
    return mapped or DEFAULT_FINDATA_MAPPING


def consulted_at_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()  # noqa: UP017


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    robots_result = fetch_text(urllib.parse.urljoin(base_url, "/robots.txt"))
    robots_available = robots_result.status == HTTP_OK
    robots = parse_robots(robots_result.body) if robots_available else RobotsRules([])
    sitemap_result = fetch_text(urllib.parse.urljoin(base_url, "/sitemap.xml"))
    sitemap_urls, nested_sitemaps = (
        collect_sitemap_urls(sitemap_result, base_url, robots, args.sleep)
        if robots_available
        else (parse_sitemap(sitemap_result.body), [])
    )
    pages = inspect_pages(base_url, robots, args.sleep) if robots_available else []
    asset_results, asset_literals = (
        collect_static_assets(pages, base_url, robots, args.sleep)
        if robots_available
        else ([], [])
    )
    referenced: set[str] = set(asset_literals)
    for page in pages:
        referenced.update(extract_html_urls(page, base_url))
        referenced.update(extract_url_literals(page.body, base_url))
    authorized_targets = collect_authorized_targets(
        sorted(referenced), base_url, args.probe_path_prefix
    )
    browser = {"enabled": False, "error": "not requested", "urls": []}
    if args.browser_network and robots_available:
        browser = browser_network_urls(
            base_url, args.browser_path, args.chrome, args.browser_timeout
        )
    elif args.browser_network:
        browser = {
            "enabled": False,
            "error": "skipped because robots.txt could not be fetched with HTTP 200",
            "urls": [],
        }
    browser_urls = browser.get("urls", []) if isinstance(browser.get("urls"), list) else []
    authorized_probe = {
        "enabled": False,
        "scope": "not run; API-like paths recorded only",
        "targets": [redact_url(url) for url in authorized_targets],
        "results": [],
        "max_bytes": args.probe_max_bytes,
    }
    if args.authorized_probe:
        authorized_probe = {
            "enabled": True,
            "scope": (
                "owner-authorized GET-only sampling of publicly referenced "
                "same-origin API-like paths; no fuzzing, no auth bypass, no mutation"
            ),
            "targets": [redact_url(url) for url in authorized_targets],
            "results": probe_authorized_targets(
                authorized_targets,
                sleep_seconds=args.probe_sleep,
                max_bytes=args.probe_max_bytes,
            ),
            "max_bytes": args.probe_max_bytes,
            "sleep_seconds": args.probe_sleep,
        }
    sitemap_counts = summarize_counts(sitemap_urls, base_url)
    return {
        "consulted_at": consulted_at_iso(),
        "base_url": base_url,
        "artifact_paths": {
            "json": args.output,
            "markdown": args.markdown,
        },
        "policy": {
            "intent": (
                "benchmark public product behavior; API probing only in explicit "
                "owner-authorized GET-only mode"
            ),
            "api_routes_fetched": (
                [item["url"] for item in authorized_probe["results"]]
                if authorized_probe["enabled"]
                else []
            ),
        },
        "robots": {
            "url": robots_result.url,
            "status": robots_result.status,
            "available": robots_available,
            "disallow": robots.disallow if robots_available else [],
            "error": robots_result.error,
        },
        "sitemap": {
            "url": sitemap_result.url,
            "status": sitemap_result.status,
            "url_count": len(sitemap_urls),
            "by_section": sitemap_counts,
            "urls": sitemap_urls,
            "nested_sitemaps": [page_summary(sitemap) for sitemap in nested_sitemaps],
        },
        "inspected_pages": [page_summary(page) for page in pages],
        "static_assets_fetched": [page_summary(asset) for asset in asset_results],
        "referenced_urls": split_url_inventory(sorted(referenced), base_url, robots),
        "browser_network": browser,
        "browser_network_summary": browser_summary(browser_urls, base_url),
        "authorized_probe": authorized_probe,
        "findata_mapping": infer_findata_mapping(base_url, sitemap_counts),
    }


def page_summary(result: FetchResult) -> dict[str, object]:
    return {
        "url": redact_url(result.url),
        "status": result.status,
        "content_type": result.content_type,
        "bytes": len(result.body.encode()),
        "error": result.error,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output", default=None)
    parser.add_argument("--markdown", default=None)
    parser.add_argument("--slug", default=None, help="artifact slug; defaults to hostname")
    parser.add_argument("--sleep", type=float, default=0.2, help="polite delay between HTTP GETs")
    parser.add_argument("--browser-network", action="store_true")
    parser.add_argument("--browser-timeout", type=int, default=12)
    parser.add_argument("--chrome", default=None, help="optional Chrome executable path")
    parser.add_argument("--browser-path", action="append", default=None)
    parser.add_argument(
        "--authorized-probe",
        action="store_true",
        help="owner-authorized GET-only probe of publicly referenced API-like paths",
    )
    parser.add_argument(
        "--probe-sleep",
        type=float,
        default=1.0,
        help="polite delay between authorized API GETs",
    )
    parser.add_argument(
        "--probe-max-bytes",
        type=int,
        default=DEFAULT_API_MAX_BYTES,
        help="maximum response bytes retained per authorized API target",
    )
    parser.add_argument(
        "--probe-path-prefix",
        action="append",
        default=None,
        help="same-origin path prefix allowed in authorized probe mode",
    )
    args = parser.parse_args()
    if args.probe_path_prefix is None:
        args.probe_path_prefix = DEFAULT_PROBE_PATH_PREFIXES
    if args.slug is None:
        args.slug = slug_from_url(args.base_url)
    if args.output is None:
        args.output = f"docs/snapshots/{args.slug}_public_surface.json"
    if args.markdown is None:
        args.markdown = f"docs/{args.slug.upper()}_ENDPOINT_BENCHMARK.md"
    if args.browser_path is None:
        # The homepage prefetches the main app routes via Next RSC requests;
        # additional --browser-path values can be passed for deeper local runs.
        args.browser_path = ["/"]
    return args


def slug_from_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc or url
    host = host.lower().removeprefix("www.")
    slug = re.sub(r"[^a-z0-9]+", "_", host).strip("_")
    return slug or "benchmark"


def main() -> None:
    args = parse_args()
    payload = build_payload(args)
    output = Path(args.output)
    markdown = Path(args.markdown)
    output.parent.mkdir(parents=True, exist_ok=True)
    markdown.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    markdown.write_text(build_report(payload))
    print(f"Wrote {output}")
    print(f"Wrote {markdown}")


if __name__ == "__main__":
    main()
