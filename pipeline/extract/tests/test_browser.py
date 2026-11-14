"""Browser fallback, offline: the guard proxy's refusals and when the stage uses the fallback."""

import asyncio

import httpx
import pytest

import pipeline.extract as extract
from pipeline.common import net
from pipeline.common.contracts import Input, InputKind
from pipeline.common.errors import StageError
from pipeline.common.fixtures import example_analysis
from pipeline.extract import browser
from pipeline.extract.browser import GuardProxy
from pipeline.extract.fetch import FetchFailed, Page, new_client

from .test_stage import BODY, article_page


async def _ask(proxy: GuardProxy, request: bytes) -> bytes:
    port = int(proxy.url.rsplit(":", 1)[1])
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(request)
    await writer.drain()
    answer = await asyncio.wait_for(reader.read(200), timeout=5)
    writer.close()
    return answer


@pytest.mark.parametrize(
    "request_bytes",
    [
        b"CONNECT 127.0.0.1:443 HTTP/1.1\r\nHost: 127.0.0.1:443\r\n\r\n",  # loopback
        b"CONNECT 10.0.0.5:443 HTTP/1.1\r\n\r\n",  # private network
        b"CONNECT [::1]:443 HTTP/1.1\r\n\r\n",  # IPv6 loopback
        b"CONNECT example.com:8443 HTTP/1.1\r\n\r\n",  # only port 443
        b"CONNECT no-such-host.invalid:443 HTTP/1.1\r\n\r\n",  # does not resolve
        b"GET http://169.254.169.254/latest/meta-data/ HTTP/1.1\r\n\r\n",  # plain HTTP
    ],
)
def test_guard_proxy_refuses_non_public_destinations(request_bytes):
    async def go():
        async with GuardProxy() as proxy:
            answer = await _ask(proxy, request_bytes)
            return answer, proxy.blocked

    answer, blocked = asyncio.run(go())
    assert answer.startswith(b"HTTP/1.1 403")
    assert len(blocked) == 1


def _analysis(url: str):
    a = example_analysis()
    a.input = Input(kind=InputKind.url, value=url)
    return a


@pytest.fixture
def site(monkeypatch):
    """Plain HTTP answers from `plain[url]`; the browser answers from `rendered[url]`."""
    plain: dict[str, tuple[int, str]] = {}
    rendered: dict[str, Page | FetchFailed] = {}
    calls: list[str] = []

    def handler(request):
        status, body = plain[str(request.url)]
        return httpx.Response(status, headers={"content-type": "text/html"}, text=body)

    async def render_page(url):
        calls.append(url)
        result = rendered[url]
        if isinstance(result, FetchFailed):
            raise result
        return result

    monkeypatch.setattr(net, "assert_public_url", lambda url: None)
    monkeypatch.setattr(extract, "new_client", lambda: new_client(httpx.MockTransport(handler)))
    monkeypatch.setattr(browser, "enabled", lambda: True)
    monkeypatch.setattr(browser, "render_page", render_page)
    return plain, rendered, calls


def _rendered(url: str, html: str) -> Page:
    return Page(url=url, status=200, content_type="text/html", body=html.encode(), truncated=False)


URL = "https://news.example/a"


def test_bot_check_403_falls_back_to_the_browser(site):
    plain, rendered, calls = site
    plain[URL] = (403, "Just a moment...")
    rendered[URL] = _rendered(URL, article_page())
    patch = asyncio.run(extract.run(_analysis(URL)))
    assert calls == [URL]
    assert patch.document.paragraphs == BODY


def test_page_without_article_falls_back_to_the_browser(site):
    plain, rendered, calls = site
    plain[URL] = (200, "<html><body><div id=app></div><script src=app.js></script></body></html>")
    rendered[URL] = _rendered(URL, article_page())
    patch = asyncio.run(extract.run(_analysis(URL)))
    assert calls == [URL]
    assert patch.document.title == "Tram line approved"


@pytest.mark.parametrize(("status", "reason"), [(404, "not found"), (402, "subscription")])
def test_no_fallback_when_a_browser_cannot_help(site, status, reason):
    plain, _, calls = site
    plain[URL] = (status, "no")
    with pytest.raises(StageError, match=reason):
        asyncio.run(extract.run(_analysis(URL)))
    assert calls == []


def test_failed_fallback_keeps_the_plain_reason(site):
    plain, rendered, _ = site
    plain[URL] = (403, "denied")
    rendered[URL] = FetchFailed("The site could not be reached")
    with pytest.raises(StageError, match="refused"):
        asyncio.run(extract.run(_analysis(URL)))


def test_fallback_that_hits_a_private_address_says_so(site):
    plain, rendered, _ = site
    plain[URL] = (403, "denied")
    rendered[URL] = FetchFailed("The link does not point to a public website")
    with pytest.raises(StageError, match="public website"):
        asyncio.run(extract.run(_analysis(URL)))


def test_rendered_page_without_article(site):
    plain, rendered, _ = site
    plain[URL] = (403, "denied")
    rendered[URL] = _rendered(URL, "<html><body><div>Checking your browser</div></body></html>")
    with pytest.raises(StageError, match="paste its text"):
        asyncio.run(extract.run(_analysis(URL)))
