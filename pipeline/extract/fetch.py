"""Download one web page safely. Used by `extract` for URL input and by `retrieve` for every hit.

Redirects are followed by hand so the integrator's guard (`pipeline.common.net.assert_public_url`)
checks every hop: a public link that redirects to `http://worker:8001/` or a cloud metadata address
is refused, not fetched (server-side request forgery). Failures raise `FetchFailed` with a reason in
plain words that is safe to show the user; it never contains the URL.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from trafilatura.utils import decode_file

from pipeline.common import net
from pipeline.common.errors import StageError

# Browser-like: many news sites refuse clients that do not look like a browser.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
MAX_REDIRECTS = 5
MAX_BYTES = 5_000_000
TIMEOUT_S = 15.0
_HTML_TYPES = ("text/html", "application/xhtml+xml")
_REFUSED = {401, 403, 429, 451}
_GONE = {404, 410}
# Statuses bot-protection services answer with (Cloudflare and similar challenge pages).
_BOT_CHECK = {403, 429, 503}


class FetchFailed(Exception):
    """The page could not be read; `reason` is plain language and safe to show publicly."""

    def __init__(self, reason: str, *, fallback_may_help: bool = False):
        super().__init__(reason)
        self.reason = reason
        # The site turned away a plain HTTP client (bot check); the scraping service
        # (`scraper`) may still be served.
        self.fallback_may_help = fallback_may_help


@dataclass
class Page:
    url: str  # final URL, after redirects
    status: int
    content_type: str
    body: bytes
    truncated: bool  # the body hit MAX_BYTES and was cut


def new_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    """HTTP client for `fetch_page`; redirects stay off because `fetch_page` checks each hop."""
    return httpx.AsyncClient(
        follow_redirects=False,
        timeout=TIMEOUT_S,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "en;q=0.8, *;q=0.5",
        },
        transport=transport,
    )


async def _check(url: str, guard: Callable[[str], None]) -> None:
    try:
        # The guard resolves the host name (blocking DNS), so it runs off the event loop.
        await asyncio.to_thread(guard, url)
    except StageError as e:
        raise FetchFailed(str(e)) from e


async def fetch_page(
    url: str,
    client: httpx.AsyncClient,
    *,
    guard: Callable[[str], None] | None = None,
    max_bytes: int = MAX_BYTES,
) -> Page:
    """GET `url`, following up to MAX_REDIRECTS redirects, each checked by `guard`.

    Non-2xx answers are returned, not raised: `ensure_html` decides what is readable.
    """
    guard = guard or net.assert_public_url
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await _check(current, guard)
        try:
            async with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise FetchFailed("The site sent a redirect without a destination")
                    current = urljoin(current, location)
                    continue
                body = bytearray()
                truncated = False
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > max_bytes:
                        del body[max_bytes:]
                        truncated = True
                        break
                return Page(
                    url=current,
                    status=resp.status_code,
                    content_type=resp.headers.get("content-type", ""),
                    body=bytes(body),
                    truncated=truncated,
                )
        except httpx.TimeoutException as e:
            raise FetchFailed("The site took too long to answer") from e
        except httpx.HTTPError as e:
            raise FetchFailed("The site could not be reached") from e
    raise FetchFailed("The link redirects too many times")


def ensure_html(page: Page) -> None:
    """Raise `FetchFailed` unless the page is a readable HTML document."""
    if page.status == 402:
        raise FetchFailed("The site asks for a subscription to read this page (HTTP 402)")
    if page.status in _REFUSED:
        raise FetchFailed(
            f"The site refused to let us read the page (HTTP {page.status})",
            fallback_may_help=page.status in _BOT_CHECK,
        )
    if page.status in _GONE:
        raise FetchFailed(f"The page was not found (HTTP {page.status})")
    if not 200 <= page.status < 300:
        raise FetchFailed(
            f"The site answered with an error (HTTP {page.status})",
            fallback_may_help=page.status in _BOT_CHECK,
        )
    media_type = page.content_type.split(";")[0].strip().lower()
    if media_type and media_type not in _HTML_TYPES:
        raise FetchFailed(f"The link is not a web page ({media_type})")
    if not page.body.strip():
        raise FetchFailed("The page is empty")


def html_text(page: Page) -> str:
    """The body as text; trafilatura's decoder reads the charset from the headers or the page."""
    return decode_file(page.body)
