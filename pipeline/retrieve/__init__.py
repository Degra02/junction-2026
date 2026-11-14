"""Stage 4, retrieve: other coverage of the same story, and what is known about every outlet.

`run` reads the curated outlets' feeds (`feeds`), keeps the items that share enough words with
the analysis's queries and claims (`match`), looks up published fact-checks of the claims
(`factcheck_api`, when a key is configured), reads each hit in full (`articles`), collects the
public social media posts that repeat the document's wording (`social`) and profiles every outlet
domain (`sources`). Signals compute from this output only, so:
- a social media post is in `context[]` only when it repeats the document's words; it is marked by
  `retrieved_by` (the platform) and `story` never counts it as coverage;
- `context[].text` is always a full article body, never a feed summary;
- `sources[]` covers the document's outlet and every context outlet, typed from the registry.

The stage never fails because a source is down: a feed or page that does not answer in time is
skipped, and an analysis with no related coverage gets an empty context (score then abstains).
Phases run under fixed budgets that sum below the worker's 120 s stage timeout.
"""

import asyncio
import logging
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import replace

from pipeline.common import progress
from pipeline.common.contracts import (
    Analysis,
    ContextItem,
    FactCheck,
    InputKind,
    OutletType,
    RetrievePatch,
)
from pipeline.extract import scraper
from pipeline.extract.document import published_utc
from pipeline.extract.fetch import new_client
from pipeline.extract.urls import canonical_url, outlet_host
from pipeline.retrieve import factcheck_api, feeds, gdelt, oxylabs, social
from pipeline.retrieve.articles import Reader, Record, context_item
from pipeline.retrieve.cache import default_cache
from pipeline.retrieve.feeds import FeedItem
from pipeline.retrieve.match import Hit, Query, rank
from pipeline.retrieve.phrases import contains, distinctive_phrases
from pipeline.retrieve.registry import Registry, load_registry
from pipeline.retrieve.sources import Profiler, registrable
from pipeline.retrieve.viginum import Listing, fetch_listing, load_listing
from pipeline.retrieve.web import Web

log = logging.getLogger(__name__)

FEEDS_TIMEOUT_S = 20.0
ARTICLES_TIMEOUT_S = 50.0
SOURCES_TIMEOUT_S = 25.0
VIGINUM_TIMEOUT_S = 10.0  # runs alongside the feeds, so it adds no time
FACTCHECK_TIMEOUT_S = 15.0  # likewise
# Exact-phrase searches start with the feeds; they may run 5 s longer (GDELT's pacing, Oxylabs'
# realtime scraping), so the phases still total 100 s, under the 120 s stage timeout.
PHRASES_TIMEOUT_S = 25.0
GDELT_PHRASES = 2  # 5.5 s apart: two fit in the budget
NEWS_QUERIES = 4  # Google News searches per analysis (each costs Oxylabs credit)
MAX_HITS = 30  # pages fetched per analysis
PER_OUTLET = 3  # hits per outlet, so one prolific site does not fill the context
WIRE_BONUS = 0.1  # agency originals let the signals tell syndication from copying

# Loaded at import so the worker pays for it once, at startup.
_REGISTRY = load_registry()
_LISTING = load_listing()


def search_queries(analysis: Analysis) -> list[Query]:
    """`understand`'s queries, plus the claims and the title (in the document's language)."""
    own = analysis.language.code if analysis.language else None
    queries = [Query(q.text.strip(), q.language or None) for q in analysis.queries]
    queries += [Query(c.text.strip(), own) for c in analysis.claims]
    if analysis.document and analysis.document.title:
        queries.append(Query(analysis.document.title.strip(), own))
    return [q for q in dict.fromkeys(queries) if q.text]


def _site(host: str | None) -> str:
    """The outlet a host belongs to: its registrable domain (`bologna.repubblica.it` ->
    `repubblica.it`), or the host without `www.` when it has no public suffix."""
    if not host:
        return ""
    return registrable(host) or host.lower().removeprefix("www.")


def select(hits: list[Hit], analysis: Analysis, reg: Registry) -> list[Hit]:
    """The hits worth reading: not the document itself nor its outlet, at most PER_OUTLET per
    outlet, agency items slightly preferred, up to MAX_HITS."""
    document = analysis.document
    own_url = canonical_url(document.url) if document and document.url else None
    own_site = _site(document.outlet) if document else ""

    def priority(hit: Hit) -> float:
        outlet = reg.lookup(hit.item.outlet)
        wire = outlet is not None and outlet.outlet_type == OutletType.wire_service
        return hit.score + (WIRE_BONUS if wire else 0.0)

    chosen: list[Hit] = []
    per_site: Counter[str] = Counter()
    for hit in sorted(hits, key=priority, reverse=True):
        site = _site(hit.item.outlet)
        if canonical_url(hit.item.url) == own_url or (own_site and site == own_site):
            continue
        if per_site[site] >= PER_OUTLET:
            continue
        per_site[site] += 1
        chosen.append(hit)
        if len(chosen) == MAX_HITS:
            break
    return chosen


async def _until(
    jobs: list[Awaitable], timeout_s: float, on_progress: Callable[[int], None]
) -> list:
    """Run `jobs` concurrently for at most `timeout_s`; results in input order, None for jobs
    that failed or did not finish."""
    tasks = [asyncio.ensure_future(job) for job in jobs]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    pending = set(tasks)
    while pending:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        _, pending = await asyncio.wait(
            pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
        )
        on_progress(len(tasks) - len(pending))
    for task in pending:
        task.cancel()
    results = []
    for task in tasks:
        if task.done() and not task.cancelled() and task.exception() is None:
            results.append(task.result())
        else:
            if task.done() and not task.cancelled():
                log.warning("retrieve job failed", exc_info=task.exception())
            results.append(None)
    return results


PHRASE_ADAPTERS = (gdelt.NAME, oxylabs.NAME)


def _context(
    hits: list[Hit], records: list[Record | None], phrases: list[str] = ()
) -> list[ContextItem]:
    """Context items for the hits that were read. A phrase-search hit stays only if the page
    really repeats one of the phrases: search engines loosen quoted queries."""
    context: list[ContextItem] = []
    seen: set[str] = set()
    for hit, record in zip(hits, records, strict=True):
        if record is None:
            continue
        retrieved_by = hit.retrieved_by
        if retrieved_by in PHRASE_ADAPTERS and not any(contains(record.text, p) for p in phrases):
            if hit.fallback is None:
                continue
            retrieved_by = hit.fallback
        key = canonical_url(record.url)
        if key in seen:
            continue
        seen.add(key)
        context.append(
            context_item(f"ctx{len(context) + 1}", record, retrieved_by, hit.item.language)
        )
    return context


def fact_check_item(
    item_id: str, review: factcheck_api.Review, record: Record | None
) -> ContextItem:
    """A published review as a context item: the reviewed claim, the rating, then the review
    article when it could be read (the contract's "claim followed by the verdict text")."""
    url = record.url if record else review.url
    body = record.text if record else ""
    text = "\n\n".join(part for part in (review.claim, f"Rating: {review.rating}", body) if part)
    language = (review.language or (record.language if record else None) or "").split("-")[0]
    return ContextItem(
        id=item_id,
        url=url,
        outlet=outlet_host(url) or None,
        published_at=published_utc(review.published_at)
        or (published_utc(record.published_at) if record else None),
        title=review.title or (record.title if record else None),
        text=text,
        language=language.lower() or None,
        retrieved_by=factcheck_api.NAME,
        tracking_ids=record.tracking_ids if record else [],
        fact_check=FactCheck(claim=review.claim, rating=review.rating, publisher=review.publisher),
    )


def _with_fact_checks(
    context: list[ContextItem],
    reviews: list[factcheck_api.Review],
    records: list[Record | None],
) -> list[ContextItem]:
    """`context` plus one item per review whose article is not in it already."""
    seen = {canonical_url(item.url) for item in context}
    out = list(context)
    for review, record in zip(reviews, records, strict=True):
        url = record.url if record else review.url
        if canonical_url(url) in seen:
            continue
        seen.add(canonical_url(url))
        out.append(fact_check_item(f"ctx{len(out) + 1}", review, record))
    return out


async def _search_hits(
    client, cache, phrases: list[str], queries: list[Query]
) -> tuple[list[Hit], list[FeedItem]]:
    """Searches beyond the feeds, run together under PHRASES_TIMEOUT_S:
    - hits that repeat one of the document's phrases verbatim (GDELT, Oxylabs), which skip the
      word matching: an exact phrase is relevant by construction;
    - web results for understand's topic queries (Oxylabs), returned for the same word matching
      as feed items."""
    searches, names = [], []
    for phrase in phrases[:GDELT_PHRASES]:
        searches.append(gdelt.search(client, cache, phrase))
        names.append(gdelt.NAME)
    if scraper.enabled():
        for phrase in phrases:
            searches.append(oxylabs.search(client, cache, phrase))
            names.append(oxylabs.NAME)
        for query in queries[:NEWS_QUERIES]:
            searches.append(oxylabs.news_search(client, cache, query.text, query.language))
            names.append(oxylabs.NEWS_NAME)
    if not searches:
        return [], []
    tasks = [asyncio.ensure_future(s) for s in searches]
    done, pending = await asyncio.wait(tasks, timeout=PHRASES_TIMEOUT_S)
    for task in pending:
        task.cancel()
    hits: dict[str, Hit] = {}
    news: list[FeedItem] = []
    for name, task in zip(names, tasks, strict=True):
        if task not in done or task.exception() is not None:
            continue
        if name == oxylabs.NEWS_NAME:
            news.extend(task.result())
            continue
        for item in task.result():
            hits.setdefault(canonical_url(item.url), Hit(item, 1.0, name))
    return list(hits.values()), news


def _merge(phrase_hits: list[Hit], feed_hits: list[Hit]) -> list[Hit]:
    """Phrase hits first; a word-matched hit for the same article becomes its fallback."""
    matched = {canonical_url(h.item.url): h for h in feed_hits}
    merged = [
        replace(h, fallback=matched[key].retrieved_by)
        if (key := canonical_url(h.item.url)) in matched
        else h
        for h in phrase_hits
    ]
    seen = {canonical_url(h.item.url) for h in phrase_hits}
    return merged + [h for h in feed_hits if canonical_url(h.item.url) not in seen]


def _fact_check_queries(analysis: Analysis) -> list[tuple[str, str | None]]:
    """The claims first (most specific), then understand's queries."""
    own = analysis.language.code if analysis.language else None
    queries = [(c.text.strip(), own) for c in analysis.claims]
    queries += [(q.text.strip(), q.language or None) for q in analysis.queries]
    return [q for q in dict.fromkeys(queries) if q[0]]


async def _reviews(client, cache, analysis: Analysis) -> list[factcheck_api.Review]:
    key = factcheck_api.api_key()
    queries = _fact_check_queries(analysis)
    if not key or not queries:
        return []
    try:
        async with asyncio.timeout(FACTCHECK_TIMEOUT_S):
            return await factcheck_api.find_reviews(client, cache, queries, key)
    except TimeoutError:
        log.warning("fact check API search timed out")
        return []


def _redirects(analysis: Analysis) -> dict[str, str]:
    """{document outlet: submitted host} when the submitted URL redirected to another host."""
    document = analysis.document
    if analysis.input.kind != InputKind.url or not document or not document.outlet:
        return {}
    submitted = outlet_host(analysis.input.value)
    return {document.outlet: submitted} if submitted and submitted != document.outlet else {}


async def _listing(web: Web, cache) -> Listing:
    """The configured VIGINUM file when there is one, else the downloaded list (cached)."""
    if len(_LISTING):
        return _LISTING
    try:
        async with asyncio.timeout(VIGINUM_TIMEOUT_S):
            return await fetch_listing(web, cache)
    except TimeoutError:
        log.warning("VIGINUM list download timed out: known_network stays empty")
        return Listing()


async def run(analysis: Analysis) -> RetrievePatch:
    queries = search_queries(analysis)
    # Only understand's queries go to paid news search; claims and title are matched locally.
    user_queries = [Query(q.text.strip(), q.language or None) for q in analysis.queries]
    document_outlet = analysis.document.outlet if analysis.document else None
    cache = default_cache()
    async with new_client() as client:
        web = Web(client)
        # Both run while the feeds are read (see `viginum`, `factcheck_api`).
        listing = asyncio.create_task(_listing(web, cache))
        reviews_task = asyncio.create_task(_reviews(client, cache, analysis))
        phrases = distinctive_phrases(analysis.document)
        search_task = asyncio.create_task(_search_hits(client, cache, phrases, user_queries))
        # Runs beside the feeds and the article reads, under its own budget (see `social`).
        own_url = analysis.document.url if analysis.document else None
        posts_task = asyncio.create_task(social.find_posts(web, cache, phrases, own_url))
        context: list[ContextItem] = []
        feeds_read = 0
        if queries or phrases:
            progress.report("Reading news feeds")
            items, feeds_read = await feeds.read_feeds(web, cache, _REGISTRY, FEEDS_TIMEOUT_S)
            phrase_hits, news = await search_task
            # One ranking, so news results get the same word weights as feed items.
            news_urls = {item.url for item in news}
            ranked = [
                replace(h, retrieved_by=oxylabs.NEWS_NAME) if h.item.url in news_urls else h
                for h in rank(items + news, queries)
            ]
            found = _merge(phrase_hits, ranked)
            hits = select(found, analysis, _REGISTRY)
            reviews = await reviews_task
            progress.report(
                f"{len(hits)} possibly related reports"
                + (f" ({len(phrase_hits)} by exact phrase)" if phrase_hits else "")
                + f" in {feeds_read} feeds"
                + (f", {len(reviews)} fact-checks" if reviews else "")
            )
            reader = Reader(web, cache)
            jobs = [reader.read(h.item.url, h.item.published_at) for h in hits]
            jobs += [reader.read(r.url, r.published_at) for r in reviews]
            records = await _until(
                jobs,
                ARTICLES_TIMEOUT_S,
                lambda n: progress.report(f"Reading related reports: {n} of {len(jobs)}"),
            )
            context = _context(hits, records[: len(hits)], phrases)
            context = _with_fact_checks(context, reviews, records[len(hits) :])
            posts = await posts_task
            if posts:
                progress.report(f"{len(posts)} social media posts repeat its wording")
            context += [
                social.post_item(f"ctx{len(context) + n}", post) for n, post in enumerate(posts, 1)
            ]
        else:
            reviews_task.cancel()
            search_task.cancel()
            posts_task.cancel()
        progress.report(f"{len(context)} related reports; checking the outlets")
        domains = [document_outlet or ""] + [item.outlet or "" for item in context]
        # Publishing in Google's fact-check index is what makes an outlet a fact-checker.
        checkers = {
            item.outlet: OutletType.fact_checker
            for item in context
            if item.retrieved_by == factcheck_api.NAME and item.outlet
        }
        profiler = Profiler(
            web,
            cache,
            _REGISTRY,
            await listing,
            redirected_from=_redirects(analysis),
            fallback_types=checkers,
        )
        sources = await profiler.profiles(domains, document_outlet, SOURCES_TIMEOUT_S)
    posts_found = sum(item.retrieved_by in social.ADAPTERS for item in context)
    checks = sum(item.retrieved_by == factcheck_api.NAME for item in context)
    reports = [
        item
        for item in context
        if item.retrieved_by != factcheck_api.NAME and item.retrieved_by not in social.ADAPTERS
    ]
    outlets = len({item.outlet for item in reports})
    by_phrase = sum(item.retrieved_by in PHRASE_ADAPTERS for item in reports)
    by_news = sum(item.retrieved_by == oxylabs.NEWS_NAME for item in reports)
    detail = (
        f"{len(reports)} related reports from {outlets} outlets"
        + (f" ({by_phrase} by exact phrase)" if by_phrase else "")
        + (f" ({by_news} from news search)" if by_news else "")
        + (f", {checks} fact-checks" if checks else "")
        + (f", {posts_found} social media posts repeating its wording" if posts_found else "")
        + f" ({feeds_read} feeds read)"
        if queries or phrases
        else "No search queries, so no related coverage was looked up"
    )
    return RetrievePatch(context=context, sources=sources, detail=detail)
