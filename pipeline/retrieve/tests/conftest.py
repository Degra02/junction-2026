"""A fake web for retrieve's offline tests: canned responses, optional delays, a request log."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
import pytest

import pipeline.retrieve as retrieve
from pipeline.common import net
from pipeline.extract import scraper
from pipeline.extract.fetch import new_client
from pipeline.retrieve.cache import NoCache
from pipeline.retrieve.registry import parse
from pipeline.retrieve.viginum import parse as parse_viginum
from pipeline.retrieve.web import Web


@dataclass
class Server:
    """`pages[url] = (status, body)` or `(status, body, headers)`; unknown URLs answer 404."""

    pages: dict[str, tuple] = field(default_factory=dict)
    delays: dict[str, float] = field(default_factory=dict)  # seconds before answering
    seen: list[str] = field(default_factory=list)
    in_flight: dict[str, int] = field(default_factory=dict)  # per host, now
    peak: dict[str, int] = field(default_factory=dict)  # per host, highest
    # "host/path" -> handler, for APIs whose query strings vary (checked before `pages`).
    routes: dict[str, Callable[[httpx.Request], httpx.Response]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    async def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        host = request.url.host
        self.seen.append(url)
        self.requests.append(request)
        self.in_flight[host] = self.in_flight.get(host, 0) + 1
        self.peak[host] = max(self.peak.get(host, 0), self.in_flight[host])
        try:
            if url in self.delays:
                await asyncio.sleep(self.delays[url])
            route = self.routes.get(f"{host}{request.url.path}")
            if route is not None:
                return route(request)
            status, body, *rest = self.pages.get(url, (404, ""))
            headers = rest[0] if rest else {"content-type": _kind(request.url)}
            return httpx.Response(status, headers=headers, text=body)
        finally:
            self.in_flight[host] -= 1

    def client(self) -> httpx.AsyncClient:
        return new_client(httpx.MockTransport(self.handle))

    def web(self, **kwargs) -> Web:
        return Web(self.client(), guard=lambda url: None, **kwargs)


def _kind(url: httpx.URL) -> str:
    if url.path.endswith("/rss"):
        return "application/rss+xml"
    if url.host in ("rdap.org", "crt.sh"):
        return "application/json"
    return "text/html; charset=utf-8"


@pytest.fixture
def server(monkeypatch) -> Server:
    """Also allows every host in the URL guard and turns the scraping fallback off."""
    monkeypatch.setattr(net, "assert_public_url", lambda url: None)
    monkeypatch.setattr(scraper, "enabled", lambda: False)
    # Offline tests never use real keys from `.env` (mise loads it): no paid calls by accident.
    for name in (scraper.TOKEN_ENV, "GOOGLE_FACTCHECK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    return Server()


def rss(*items: tuple[str, str], summary: str = "") -> str:
    """A minimal RSS 2.0 feed with `(title, link)` items."""
    body = "".join(
        f"<item><title>{title}</title><link>{link}</link><description>{summary}</description>"
        "<pubDate>Sat, 14 Nov 2026 10:00:00 +0000</pubDate></item>"
        for title, link in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


def article_page(title: str, sentence: str, ga: str = "G-AB12CD34EF", head: str = "") -> str:
    """A news page with a four-paragraph body trafilatura extracts."""
    paragraphs = "".join(f"<p>{sentence} Paragraph {i} adds detail on it.</p>" for i in range(4))
    return f"""<html lang="it"><head><title>{title}</title>
<meta property="article:published_time" content="2026-11-14T09:30:00+00:00">
<script>gtag('config', '{ga}');</script>{head}</head>
<body><article><h1>{title}</h1>{paragraphs}</article></body></html>"""


# The stage fixture: three curated outlets and their feeds (used by test_stage, test_factcheck_api).
AGENCY_FEED = "https://agency.example/rss"
PAPER_FEED = "https://paper.example/rss"
CHECKER_FEED = "https://checker.example/rss"
AGENCY_ITEM = "https://agency.example/meta"
PAPER_ITEM = "https://paper.example/meta?utm_source=rss"

CLAIM_REVIEW = json.dumps(
    {
        "@context": "https://schema.org",
        "@type": "ClaimReview",
        "claimReviewed": "Meta was fined 805 billion euros",
        "reviewRating": {"@type": "Rating", "alternateName": "False"},
        "author": {"@type": "Organization", "name": "Checker"},
    }
)
HEADER = "domain,create date,first seen,type\n"
PAYWALL = (
    '<script type="application/ld+json">'
    '{"@type": "NewsArticle", "isAccessibleForFree": false}</script>'
)


def _feed(url: str) -> dict:
    return {"url": url, "language": "it"}


@pytest.fixture
def stage(server, monkeypatch):
    """Three curated outlets (agency, newspaper, fact-checker); one matching item each for the
    agency and the newspaper."""
    monkeypatch.setattr(retrieve, "new_client", server.client)
    monkeypatch.setattr(retrieve, "default_cache", NoCache)
    registry = {
        "wire_service": [{"domain": "agency.example", "feeds": [_feed(AGENCY_FEED)]}],
        "national": [{"domain": "paper.example", "feeds": [_feed(PAPER_FEED)]}],
        "fact_checker": [{"domain": "checker.example", "feeds": [_feed(CHECKER_FEED)]}],
    }
    for entries in registry.values():
        entries[0]["country"] = "IT"
    monkeypatch.setattr(retrieve, "_REGISTRY", parse(registry))
    # A configured (non-empty) list, so no download is attempted; see test_viginum_download_*.
    monkeypatch.setattr(
        retrieve, "_LISTING", parse_viginum(HEADER + "unrelated[.]example,,,domain\n")
    )
    server.pages[AGENCY_FEED] = (
        200,
        rss(
            ("Garante privacy, multa da 805 milioni a Meta", AGENCY_ITEM),
            ("Calcio, vince la Roma", "https://agency.example/calcio"),
        ),
    )
    server.pages[PAPER_FEED] = (
        200,
        rss(
            ("Multa del Garante privacy a Meta", PAPER_ITEM),
            ("Il documento analizzato", "https://paper.example/own-article"),
        ),
    )
    server.pages[CHECKER_FEED] = (200, rss())
    server.pages[AGENCY_ITEM] = (
        200,
        article_page(
            "Garante privacy, multa a Meta", "Il Garante ha multato Meta.", "G-AGENCY0001"
        ),
    )
    server.pages[PAPER_ITEM] = (
        200,
        article_page("Multa a Meta", "Meta dovrà pagare 805 milioni al Garante.", "G-PAPER00001"),
    )
    server.pages["https://paper.example/own-article"] = (200, article_page("x", "y"))
    return server
