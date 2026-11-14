"""Read a retrieved hit in full and turn it into a contract `ContextItem`.

Signals compare full bodies (claim support, copy detection), so an item enters the context only
when its article body was extracted; a paywalled teaser or an RSS summary never does. A page that
publishes `ClaimReview` data becomes a fact-check item: `fact_check` is set and its text is the
reviewed claim followed by the article (the verdict text).
"""

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from pipeline.common.contracts import ContextItem, FactCheck
from pipeline.extract import scraper
from pipeline.extract.article import Article, extract_article
from pipeline.extract.document import published_utc
from pipeline.extract.fetch import FetchFailed, Page, ensure_html, html_text
from pipeline.extract.urls import canonical_url, outlet_host
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.web import Web

log = logging.getLogger(__name__)

ARTICLE_MAX_AGE = timedelta(days=1)
_NS = "article"


@dataclass
class Record:
    """What retrieval keeps of one article (also the cached form)."""

    url: str  # final URL after redirects
    title: str | None
    text: str
    published_at: str | None  # ISO 8601 UTC
    language: str | None
    tracking_ids: list[str] = field(default_factory=list)
    fact_check: dict | None = None  # FactCheck fields


def _fact_check(article: Article) -> FactCheck | None:
    for review in article.meta.claim_reviews:
        if review.claim_reviewed and review.rating:
            return FactCheck(
                claim=review.claim_reviewed, rating=review.rating, publisher=review.reviewer
            )
    return None


def record_from(article: Article, url: str, fallback_published: str | None) -> Record | None:
    """The record for an extracted page, or None when it holds no full body."""
    if article.meta.paywalled or not article.paragraphs:
        return None
    published = published_utc(article.published_at) or published_utc(fallback_published)
    check = _fact_check(article)
    text = article.text if check is None else f"{check.claim}\n\n{article.text}"
    return Record(
        url=url,
        title=article.title,
        text=text,
        published_at=published.isoformat() if published else None,
        language=article.language,
        tracking_ids=sorted({tid for ids in article.meta.tracking_ids.values() for tid in ids}),
        fact_check=check.model_dump() if check else None,
    )


async def _extract(page: Page) -> Article | None:
    return await asyncio.to_thread(extract_article, html_text(page), page.url)


class Reader:
    """Fetches and extracts hits. A site that turns away a plain client is fetched through
    Oxylabs (`pipeline.extract.scraper`), at most `max_scrapes` pages per analysis: each costs
    plan credit."""

    def __init__(self, web: Web, cache: Cache | NoCache, *, max_scrapes: int = 5):
        self._web = web
        self._cache = cache
        self._scrapes_left = max_scrapes if scraper.enabled() else 0

    async def read(self, url: str, fallback_published: str | None = None) -> Record | None:
        key = canonical_url(url)
        cached = self._cache.get(_NS, key, ARTICLE_MAX_AGE)
        if cached is not None:
            return Record(**cached) if cached else None
        try:
            page = await self._web.get(url)
            ensure_html(page)
        except FetchFailed as e:
            # Not cached: a refusal or an outage may be over by the next analysis.
            scraped = await self._scrape(url) if e.fallback_may_help else None
            if scraped is None:
                log.info("hit not readable (%s)", e.reason)
                return None
            page = scraped
        article = await _extract(page)
        record = record_from(article, page.url, fallback_published) if article else None
        # A page that loaded without a full body is remembered too, so it is not fetched again
        # today.
        self._cache.put(_NS, key, asdict(record) if record else {})
        return record

    async def _scrape(self, url: str) -> Page | None:
        if self._scrapes_left <= 0:
            return None
        self._scrapes_left -= 1
        try:
            page = await scraper.scrape_page(url, client=self._web.client)
            ensure_html(page)
        except FetchFailed as e:
            log.info("hit not readable through the scraper either (%s)", e.reason)
            return None
        return page


def context_item(item_id: str, record: Record, retrieved_by: str, language: str) -> ContextItem:
    return ContextItem(
        id=item_id,
        url=record.url,
        outlet=outlet_host(record.url) or None,
        published_at=published_utc(record.published_at),
        title=record.title,
        text=record.text,
        language=record.language or language,
        retrieved_by=retrieved_by,
        tracking_ids=record.tracking_ids,
        fact_check=FactCheck(**record.fact_check) if record.fact_check else None,
    )
