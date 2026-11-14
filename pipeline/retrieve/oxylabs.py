"""Adapter `oxylabs`: Google exact-phrase search through the Oxylabs Web Scraper API (D7).

Google's index reaches back years and covers the small sites where copies of an article live,
so a quoted phrase finds the article's earlier versions and its copies on sister sites of a
network. Realtime endpoint, `source: google_search`, parsed results.

Credentials come from `OXYLABS_USERNAME` / `OXYLABS_PASSWORD` (HTTP basic auth, never in a URL
or a log line); without them the adapter is off. Answers are cached for a day: each query costs
plan credit.
"""

import asyncio
import json
import logging
import os
from dataclasses import asdict
from datetime import timedelta

import httpx

from pipeline.common import net
from pipeline.common.errors import StageError
from pipeline.extract.urls import outlet_host
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.feeds import FeedItem

log = logging.getLogger(__name__)

NAME = "oxylabs"
API_URL = "https://realtime.oxylabs.io/v1/queries"
USER_ENV = "OXYLABS_USERNAME"
PASSWORD_ENV = "OXYLABS_PASSWORD"
RESULTS = 10
TIMEOUT_S = 25.0  # realtime scraping is slower than a plain API
CACHE_MAX_AGE = timedelta(days=1)
_GOOGLE_HOSTS = ("google.", "youtube.com", "gstatic.com")


def credentials() -> tuple[str, str] | None:
    user, password = os.environ.get(USER_ENV), os.environ.get(PASSWORD_ENV)
    return (user, password) if user and password else None


def parse(body: bytes) -> list[FeedItem]:
    try:
        results = json.loads(body).get("results") or []
        organic = results[0]["content"]["results"]["organic"] or []
    except ValueError, AttributeError, LookupError, TypeError:
        return []
    items = []
    for entry in organic:
        url = entry.get("url") if isinstance(entry, dict) else None
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        host = outlet_host(url)
        if any(g in host for g in _GOOGLE_HOSTS):
            continue
        items.append(
            FeedItem(
                url=url,
                title=" ".join(str(entry.get("title") or "").split()),
                summary=" ".join(str(entry.get("desc") or "").split()),
                published_at=None,  # Google's snippet date is not reliable; the page's is used
                outlet=host,
                language="",
            )
        )
    return items


async def search(
    client: httpx.AsyncClient, cache: Cache | NoCache, phrase: str, auth: tuple[str, str]
) -> list[FeedItem]:
    cached = cache.get(NAME, phrase, CACHE_MAX_AGE)
    if cached is not None:
        return [FeedItem(**item) for item in cached]
    try:
        await asyncio.to_thread(net.assert_public_url, API_URL)
    except StageError:
        return []
    payload = {"source": "google_search", "query": f'"{phrase}"', "parse": True, "limit": RESULTS}
    try:
        response = await client.post(API_URL, json=payload, auth=auth, timeout=TIMEOUT_S)
    except httpx.HTTPError as e:
        log.info("Oxylabs unreachable (%s)", type(e).__name__)
        return []
    if response.status_code != 200:
        # 401: wrong credentials; 402/403: plan exhausted; 429: rate limit.
        log.warning("Oxylabs answered HTTP %s", response.status_code)
        return []
    items = parse(response.content)
    cache.put(NAME, phrase, [asdict(item) for item in items])
    return items
