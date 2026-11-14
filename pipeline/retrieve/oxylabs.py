"""Adapters `oxylabs` and `oxylabs_news`: web search through Oxylabs AI Studio (D7).

`POST /search/instant` returns up to 10 search-engine results synchronously (2-12 s measured on
Sat 14.11). Two uses:
- `search` (exact phrase, adapter `oxylabs`): a quoted run of the document's words finds its
  earlier versions and its copies on sister sites of a network, reaching back years;
- `news_search` (topic query, adapter `oxylabs_news`): coverage of the event by outlets whose
  feeds we do not read, and coverage older than the feeds' few days.
Results are only links: every page is then read by retrieve's own fetcher. Links to search
engines, reference works and social networks are dropped. The key comes from
`pipeline.extract.scraper` (`OXYLABS_TOKEN`, in a header, never in a URL or a log line); without
it both adapters are off. Answers are cached for a day: each search costs credit.
"""

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import timedelta

import httpx

from pipeline.common import net
from pipeline.common.errors import StageError
from pipeline.extract import scraper
from pipeline.extract.fetch import FetchFailed
from pipeline.extract.urls import outlet_host
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.feeds import FeedItem

log = logging.getLogger(__name__)

NAME = "oxylabs"
NEWS_NAME = "oxylabs_news"
RESULTS = 10  # the instant endpoint's maximum
TIMEOUT_S = 25.0
CACHE_MAX_AGE = timedelta(days=1)
# Search engines' own pages, reference works and social networks: not news coverage.
_SKIP_DOMAINS = (
    "google.com", "bing.com", "youtube.com", "gstatic.com", "wikipedia.org", "wikimedia.org",
    "wiktionary.org", "facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com",
    "reddit.com", "linkedin.com", "pinterest.com", "amazon.com",
)  # fmt: skip


def _skipped(host: str) -> bool:
    return host.startswith("google.") or any(
        host == d or host.endswith("." + d) for d in _SKIP_DOMAINS
    )


def parse(body: bytes, language: str = "") -> list[FeedItem]:
    """Result links of an instant-search answer (`data[]` of url, title, description)."""
    try:
        entries = json.loads(body).get("data") or []
    except ValueError, AttributeError:
        return []
    items = []
    for entry in entries if isinstance(entries, list) else []:
        url = entry.get("url") if isinstance(entry, dict) else None
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        host = outlet_host(url)
        if _skipped(host):
            continue
        items.append(
            FeedItem(
                url=url,
                title=" ".join(str(entry.get("title") or "").split()),
                summary=" ".join(str(entry.get("description") or "").split()),
                published_at=None,  # the page's own date is used once it is read
                outlet=host,
                language=language,
            )
        )
    return items


async def _instant(
    client: httpx.AsyncClient, cache: Cache | NoCache, namespace: str, query: str, language: str
) -> list[FeedItem]:
    cached = cache.get(namespace, query, CACHE_MAX_AGE)
    if cached is not None:
        return [FeedItem(**item) for item in cached]
    try:
        await asyncio.to_thread(net.assert_public_url, scraper.API_URL)
        response = await scraper.call(
            client,
            "POST",
            "/search/instant",
            body={"query": query, "limit": RESULTS},
            timeout_s=TIMEOUT_S,
        )
    except StageError, FetchFailed:
        return []
    except httpx.HTTPError as e:
        log.info("Oxylabs search unreachable (%s)", type(e).__name__)
        return []
    if response.status_code != 200:
        # 401: bad key; 402/403: credit exhausted; 429: rate limit.
        log.warning("Oxylabs search answered HTTP %s", response.status_code)
        return []
    items = parse(response.content, language)
    cache.put(namespace, query, [asdict(item) for item in items])
    return items


async def search(client: httpx.AsyncClient, cache: Cache | NoCache, phrase: str) -> list[FeedItem]:
    """Pages that contain `phrase` verbatim."""
    return await _instant(client, cache, NAME, f'"{phrase}"', "")


async def news_search(
    client: httpx.AsyncClient, cache: Cache | NoCache, query: str, language: str | None
) -> list[FeedItem]:
    """Pages about a topic query, tagged with its language for retrieve's word matching."""
    return await _instant(client, cache, NEWS_NAME, query, language or "")
