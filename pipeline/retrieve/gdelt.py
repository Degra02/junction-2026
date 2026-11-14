"""Adapter `gdelt`: exact-phrase search in the GDELT DOC 2.0 API (free, last 3 months).

GDELT monitors news sites worldwide; a quoted phrase finds reports that repeat it verbatim,
including small and foreign-language sites the curated feeds do not cover. It allows one request
every 5 seconds per IP, so every call in the process waits its turn (`_pace`) and answers are
cached for a day. A 429 or an error just gives no hits.
"""

import asyncio
import json
import logging
import time
import weakref
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

import httpx

from pipeline.common import net
from pipeline.common.errors import StageError
from pipeline.extract.urls import outlet_host
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.feeds import FeedItem

log = logging.getLogger(__name__)

NAME = "gdelt"
API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
INTERVAL_S = 5.5  # GDELT asks for at most one request every 5 seconds
MAX_RECORDS = 25
CACHE_MAX_AGE = timedelta(days=1)

# GDELT names languages in English; ISO 639-1 for the ones the pipeline meets most.
LANGUAGES = {
    "English": "en", "Italian": "it", "German": "de", "French": "fr", "Spanish": "es",
    "Dutch": "nl", "Portuguese": "pt", "Polish": "pl", "Russian": "ru", "Ukrainian": "uk",
    "Romanian": "ro", "Czech": "cs", "Slovak": "sk", "Swedish": "sv", "Finnish": "fi",
    "Danish": "da", "Norwegian": "no", "Greek": "el", "Hungarian": "hu", "Bulgarian": "bg",
    "Croatian": "hr", "Serbian": "sr", "Slovenian": "sl", "Lithuanian": "lt", "Latvian": "lv",
    "Estonian": "et", "Arabic": "ar", "Turkish": "tr", "Chinese": "zh", "Japanese": "ja",
}  # fmt: skip

# One lock per event loop (a lock is bound to the loop that first waits on it); the worker has
# one loop, tests start a new one per run.
_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)
_last_call = 0.0


def _lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    if loop not in _locks:
        _locks[loop] = asyncio.Lock()
    return _locks[loop]


async def _pace() -> None:
    """Wait until INTERVAL_S has passed since the previous GDELT request of this process."""
    global _last_call
    wait = _last_call + INTERVAL_S - time.monotonic()
    if wait > 0:
        await asyncio.sleep(wait)
    _last_call = time.monotonic()


def _seen(value: str | None) -> str | None:
    try:
        return datetime.strptime(value or "", "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).isoformat()
    except ValueError:
        return None


def parse(body: bytes) -> list[FeedItem]:
    try:
        articles = json.loads(body).get("articles") or []
    except ValueError, AttributeError:
        return []
    items = []
    for a in articles:
        url = a.get("url") if isinstance(a, dict) else None
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        items.append(
            FeedItem(
                url=url,
                title=" ".join(str(a.get("title") or "").split()),
                summary="",
                published_at=_seen(a.get("seendate")),
                outlet=outlet_host(url),
                language=LANGUAGES.get(a.get("language") or "", ""),
            )
        )
    return items


async def search(client: httpx.AsyncClient, cache: Cache | NoCache, phrase: str) -> list[FeedItem]:
    cached = cache.get(NAME, phrase, CACHE_MAX_AGE)
    if cached is not None:
        return [FeedItem(**item) for item in cached]
    try:
        await asyncio.to_thread(net.assert_public_url, API_URL)
    except StageError:
        return []
    params = {
        "query": f'"{phrase}"',
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(MAX_RECORDS),
        "timespan": "3months",
        "sort": "hybridrel",
    }
    async with _lock():
        await _pace()
        try:
            response = await client.get(API_URL, params=params)
        except httpx.HTTPError as e:
            log.info("GDELT unreachable (%s)", type(e).__name__)
            return []
    if response.status_code != 200:
        log.info("GDELT answered HTTP %s", response.status_code)
        return []
    items = parse(response.content)
    cache.put(NAME, phrase, [asdict(item) for item in items])
    return items
