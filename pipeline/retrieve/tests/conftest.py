"""A fake web for retrieve's offline tests: canned responses, optional delays, a request log."""

import asyncio
from dataclasses import dataclass, field

import httpx
import pytest

from pipeline.common import net
from pipeline.extract import browser
from pipeline.extract.fetch import new_client
from pipeline.retrieve.web import Web


@dataclass
class Server:
    """`pages[url] = (status, body)` or `(status, body, headers)`; unknown URLs answer 404."""

    pages: dict[str, tuple] = field(default_factory=dict)
    delays: dict[str, float] = field(default_factory=dict)  # seconds before answering
    seen: list[str] = field(default_factory=list)
    in_flight: dict[str, int] = field(default_factory=dict)  # per host, now
    peak: dict[str, int] = field(default_factory=dict)  # per host, highest

    async def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        host = request.url.host
        self.seen.append(url)
        self.in_flight[host] = self.in_flight.get(host, 0) + 1
        self.peak[host] = max(self.peak.get(host, 0), self.in_flight[host])
        try:
            if url in self.delays:
                await asyncio.sleep(self.delays[url])
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
    """Also allows every host in the URL guard and turns the browser fallback off."""
    monkeypatch.setattr(net, "assert_public_url", lambda url: None)
    monkeypatch.setattr(browser, "enabled", lambda: False)
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
