"""Oxylabs AI Studio (D7): the scraping fallback for sites that turn away a plain HTTP client,
and the shared client that `retrieve` uses for web search.

Some sites answer our fetcher with 403/429 or a JavaScript check page (France24, TASS) but serve
Oxylabs, which fetches from its own network. It replaces the headless Chromium fallback: no
browser in the worker image, so no memory spike on the 2 vCPU / 8 GB VPS.

AI Studio returns a page as Markdown (`POST /scrape`, then poll `GET /scrape/run/data`), not
HTML. `article_html` keeps only its prose blocks (no menus, link lists, headings, consent or
player notices, nor blocks repeated on the page) and wraps them in minimal HTML, so the page goes
through the same `extract_article` as any other. A scraped page has no HTML metadata: no tracking
IDs, no publication time from the page. When fewer than `MIN_PARAGRAPHS` prose blocks are left
the page counts as unreadable, so scraped text is the article, not its boilerplate.

The key is `OXYLABS_TOKEN` (AI Studio API key), sent in the `x-api-key` header, never in a URL
or a log line; without it the fallback and the searches are off. Each call costs credit, so
callers cap how many pages they send here. A URL passes `net.assert_public_url` first: a private
address is refused before anything is spent on it.
"""

import asyncio
import html
import json
import logging
import os
import re

import httpx

from pipeline.common import net
from pipeline.common.errors import StageError
from pipeline.extract.fetch import FetchFailed, Page

log = logging.getLogger(__name__)

API_URL = "https://api-aistudio.oxylabs.io"
TOKEN_ENV = "OXYLABS_TOKEN"
SCRAPE_TIMEOUT_S = 45.0
POLL_S = 1.5
MIN_PARAGRAPHS = 3
MIN_CHARS = 80
_PARALLEL = 4
_slots: dict[asyncio.AbstractEventLoop, asyncio.Semaphore] = {}

_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_NOT_PROSE = re.compile(r"(#{1,6}\s|[*+-]\s|\d+\.\s|\||>|!\[|```)")
_SENTENCE_END = re.compile(r"[.!?…»\"”’)]$")
# Notices that sites put around the article, in the pipeline's main languages.
_BOILERPLATE = re.compile(
    r"cookie|javascript|consent|newsletter|subscribe|abbonat|abbonamento|abonne|suscrib|"
    r"abonnier|navigateur|browser|navigator|adblock|ad blocker|bloqueur|werbung|"
    r"lettore video|lecteur vid|reproductor|videoplayer|registrati|inscrivez|regístrate",
    re.IGNORECASE,
)


def api_key() -> str | None:
    return os.environ.get(TOKEN_ENV) or None


def enabled() -> bool:
    return api_key() is not None


def _slot() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _slots:
        _slots[loop] = asyncio.Semaphore(_PARALLEL)
    return _slots[loop]


def prose_blocks(markdown: str) -> tuple[str | None, list[str]]:
    """The title (first `# ` heading) and the article's prose paragraphs, link syntax removed."""
    title = None
    paragraphs: list[str] = []
    seen: set[str] = set()
    repeated: set[str] = set()
    for block in re.split(r"\n\s*\n", markdown):
        lines = [line.strip() for line in block.strip().splitlines() if line.strip()]
        if not lines:
            continue
        if title is None and (m := re.match(r"#\s+(.*)", lines[0])):
            title = " ".join(_LINK.sub(r"\1", m.group(1)).split()) or None
        if _NOT_PROSE.match(lines[0]):
            continue
        raw = " ".join(lines)
        text = " ".join(_LINK.sub(r"\1", raw).split())
        linked = sum(len(m.group(1)) for m in _LINK.finditer(raw))
        if len(text) < MIN_CHARS or linked > 0.3 * len(text) or not _SENTENCE_END.search(text):
            continue
        if _BOILERPLATE.search(text):
            continue
        if text in seen:
            repeated.add(text)
        seen.add(text)
        paragraphs.append(text)
    return title, [p for p in dict.fromkeys(paragraphs) if p not in repeated]


def article_html(markdown: str) -> str | None:
    """Minimal HTML of the article in `markdown`, or None when it has too little prose."""
    title, paragraphs = prose_blocks(markdown)
    if len(paragraphs) < MIN_PARAGRAPHS:
        return None
    head = f"<title>{html.escape(title)}</title>" if title else ""
    h1 = f"<h1>{html.escape(title)}</h1>" if title else ""
    body = "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)
    return f"<html><head>{head}</head><body><article>{h1}{body}</article></body></html>"


def _client(client: httpx.AsyncClient | None) -> tuple[httpx.AsyncClient, bool]:
    return (client, False) if client is not None else (httpx.AsyncClient(), True)


async def call(
    client: httpx.AsyncClient | None,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    params: dict | None = None,
    timeout_s: float = 30.0,
) -> httpx.Response:
    """One AI Studio request with the key in the header. Raises `httpx.HTTPError`."""
    key = api_key()
    if key is None:
        raise FetchFailed("The scraping service is not configured")
    http, own = _client(client)
    try:
        return await http.request(
            method,
            API_URL + path,
            json=body,
            params=params,
            headers={"x-api-key": key},
            timeout=timeout_s,
        )
    finally:
        if own:
            await http.aclose()


async def _markdown(url: str, render: bool, client: httpx.AsyncClient | None) -> str:
    body = {"url": url, "output_format": "markdown", "render_javascript": render}
    created = await call(client, "POST", "/scrape", body=body)
    if created.status_code != 200:
        # 401: bad key; 402/403: credit exhausted; 429: rate limit. Logged, not shown.
        log.warning("Oxylabs scrape answered HTTP %s", created.status_code)
        raise FetchFailed("The site refused to let us read the page")
    run_id = created.json().get("run_id")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SCRAPE_TIMEOUT_S
    while loop.time() < deadline:
        polled = await call(client, "GET", "/scrape/run/data", params={"run_id": run_id})
        if polled.status_code == 200:
            data = polled.json()
            if data.get("status") == "completed" and isinstance(data.get("data"), str):
                return data["data"]
            if data.get("status") == "failed":
                log.info("Oxylabs scrape failed (%s)", data.get("error_code"))
                raise FetchFailed("The site refused to let us read the page")
        await asyncio.sleep(POLL_S)
    raise FetchFailed("The site took too long to answer")


async def scrape_page(
    url: str, *, render: bool = False, client: httpx.AsyncClient | None = None
) -> Page:
    """The article at `url` as Oxylabs reads it (`render`: run its JavaScript first), as a
    `fetch.Page` of minimal HTML. Raises `FetchFailed` with a plain reason."""
    if not enabled():
        raise FetchFailed("The site refused to let us read the page")
    try:
        await asyncio.to_thread(net.assert_public_url, url)
    except StageError as e:
        raise FetchFailed(str(e)) from e
    async with _slot():
        try:
            markdown = await _markdown(url, render, client)
        except httpx.TimeoutException as e:
            raise FetchFailed("The site took too long to answer") from e
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            raise FetchFailed("The site could not be reached") from e
    page_html = article_html(markdown)
    if page_html is None:
        raise FetchFailed("We could not find an article on that page")
    data = page_html.encode("utf-8")
    return Page(url=url, status=200, content_type="text/html", body=data, truncated=False)
