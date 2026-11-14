"""Adapter `feeds`: the curated outlets' own RSS/Atom feeds.

Feed links point straight at the outlet's article, so each hit can be fetched in full (unlike
Google News RSS, whose links are encoded redirects). Feeds hold only recent items, which suits
news analysis: the coverage that matters is from the same days.
"""

import asyncio
import calendar
import html
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

import feedparser

from pipeline.extract.fetch import FetchFailed
from pipeline.extract.urls import outlet_host
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.registry import Feed, Registry
from pipeline.retrieve.web import Web

log = logging.getLogger(__name__)

NAME = "feeds"
FEED_MAX_AGE = timedelta(minutes=10)
FEED_MAX_BYTES = 3_000_000
_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class FeedItem:
    url: str
    title: str
    summary: str  # plain text, used for matching only; never put in context
    published_at: str | None  # ISO 8601 UTC
    outlet: str  # host of the link, as `outlet_host` writes it
    language: str


def _plain(value: str) -> str:
    return " ".join(html.unescape(_TAG.sub(" ", value or "")).split())


def _published(entry) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), UTC).isoformat()


def parse_feed(body: bytes, feed: Feed) -> list[FeedItem]:
    items = []
    for entry in feedparser.parse(body).entries:
        url = (entry.get("link") or "").strip()
        title = _plain(entry.get("title", ""))
        if not url.startswith(("http://", "https://")) or not title:
            continue
        items.append(
            FeedItem(
                url=url,
                title=title,
                summary=_plain(entry.get("summary", "")),
                published_at=_published(entry),
                outlet=outlet_host(url),
                language=feed.language,
            )
        )
    return items


async def _read_feed(web: Web, cache: Cache | NoCache, feed: Feed) -> list[FeedItem]:
    cached = cache.get(NAME, feed.url, FEED_MAX_AGE)
    if cached is not None:
        return [FeedItem(**item) for item in cached]
    try:
        page = await web.get(feed.url, max_bytes=FEED_MAX_BYTES)
    except FetchFailed as e:
        log.info("feed %s: %s", feed.url, e.reason)
        return []
    if page.status != 200:
        log.info("feed %s: HTTP %s", feed.url, page.status)
        return []
    items = await asyncio.to_thread(parse_feed, page.body, feed)
    cache.put(NAME, feed.url, [asdict(item) for item in items])
    return items


async def read_feeds(
    web: Web, cache: Cache | NoCache, registry: Registry, timeout_s: float
) -> tuple[list[FeedItem], int]:
    """Items of every feed that answered within `timeout_s`, and how many feeds answered."""
    tasks = [asyncio.create_task(_read_feed(web, cache, feed)) for _, feed in registry.feeds()]
    done, pending = await asyncio.wait(tasks, timeout=timeout_s)
    for task in pending:
        task.cancel()
    items: list[FeedItem] = []
    answered = 0
    for task in done:
        if task.exception() is not None:
            log.warning("feed task failed", exc_info=task.exception())
            continue
        result = task.result()
        answered += bool(result)
        items.extend(result)
    return items, answered
