"""Adapter `fact_check_api`: published fact-checks of the document's claims (D8).

Google Fact Check Tools API, `claims:search`: full-text search over the ClaimReview items that
fact-checkers publish (IFCN signatories and others). Each review becomes a context item with
`fact_check` set; the fact-check signal then decides whether the reviewed claim is one of the
document's claims (NLI or word overlap), so a loosely related review costs nothing.

The key (`GOOGLE_FACTCHECK_API_KEY`) is sent in the `X-Goog-Api-Key` header, never in the URL, so
it cannot appear in request logs or error messages. Without a key the adapter is off.
"""

import asyncio
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import timedelta

import httpx

from pipeline.common import net
from pipeline.common.errors import StageError
from pipeline.extract.document import published_utc
from pipeline.retrieve.cache import Cache, NoCache

log = logging.getLogger(__name__)

NAME = "fact_check_api"
API_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
KEY_ENV = "GOOGLE_FACTCHECK_API_KEY"
MAX_QUERIES = 6
PAGE_SIZE = 5
MAX_REVIEWS = 10
CACHE_MAX_AGE = timedelta(days=1)
_PARALLEL = 3


@dataclass(frozen=True)
class Review:
    url: str  # the fact-check article
    title: str | None
    claim: str  # the claim as the fact-checker states it
    rating: str  # textual rating as published, e.g. "False"
    publisher: str | None
    publisher_site: str | None
    published_at: str | None  # ISO 8601 UTC
    language: str | None


def api_key() -> str | None:
    return os.environ.get(KEY_ENV) or None


def parse(body: bytes) -> list[Review]:
    """Reviews in an API answer; entries without a claim, a rating or a URL are skipped."""
    try:
        claims = json.loads(body).get("claims") or []
    except ValueError, AttributeError:
        return []
    reviews = []
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("text"), str):
            continue
        for review in claim.get("claimReview") or []:
            if not isinstance(review, dict):
                continue
            url, rating = review.get("url"), review.get("textualRating")
            if not (isinstance(url, str) and url.startswith(("http://", "https://")) and rating):
                continue
            publisher = review.get("publisher") if isinstance(review.get("publisher"), dict) else {}
            published = published_utc(review.get("reviewDate"))
            reviews.append(
                Review(
                    url=url,
                    title=review.get("title") if isinstance(review.get("title"), str) else None,
                    claim=" ".join(claim["text"].split()),
                    rating=" ".join(str(rating).split()),
                    publisher=publisher.get("name"),
                    publisher_site=publisher.get("site"),
                    published_at=published.isoformat() if published else None,
                    language=review.get("languageCode"),
                )
            )
    return reviews


async def _search(
    client: httpx.AsyncClient, key: str, cache: Cache | NoCache, text: str, language: str | None
) -> list[Review]:
    cache_key = f"{language or ''}|{text}"
    cached = cache.get(NAME, cache_key, CACHE_MAX_AGE)
    if cached is not None:
        return [Review(**r) for r in cached]
    params = {"query": text, "pageSize": str(PAGE_SIZE)}
    if language:
        params["languageCode"] = language
    try:
        response = await client.get(API_URL, params=params, headers={"X-Goog-Api-Key": key})
    except httpx.HTTPError as e:
        log.info("fact check API unreachable (%s)", type(e).__name__)
        return []
    if response.status_code != 200:
        # 400: bad key or query; 403: API not enabled for the key; 429: quota.
        log.warning("fact check API answered HTTP %s", response.status_code)
        return []
    reviews = parse(response.content)
    cache.put(NAME, cache_key, [asdict(r) for r in reviews])
    return reviews


async def find_reviews(
    client: httpx.AsyncClient,
    cache: Cache | NoCache,
    queries: list[tuple[str, str | None]],
    key: str,
) -> list[Review]:
    """Reviews for up to MAX_QUERIES `(text, language)` queries, unique by URL, best first."""
    try:
        await asyncio.to_thread(net.assert_public_url, API_URL)
    except StageError:
        return []
    slots = asyncio.Semaphore(_PARALLEL)

    async def one(text: str, language: str | None) -> list[Review]:
        async with slots:
            return await _search(client, key, cache, text, language)

    results = await asyncio.gather(*(one(t, lang) for t, lang in queries[:MAX_QUERIES]))
    unique: dict[str, Review] = {}
    for reviews in results:  # query order: the claims first, so their reviews come first
        for review in reviews:
            unique.setdefault(review.url, review)
    return list(unique.values())[:MAX_REVIEWS]
