"""Stage 4, retrieve: other coverage of the same story, and what is known about every outlet.

`run` reads the curated outlets' feeds (`feeds`), keeps the items that share enough words with
the analysis's queries and claims (`match`), reads each hit in full (`articles`) and profiles every
outlet domain (`sources`). Signals compute from this output only, so:
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

from pipeline.common import progress
from pipeline.common.contracts import Analysis, ContextItem, OutletType, RetrievePatch
from pipeline.extract.fetch import new_client
from pipeline.extract.urls import canonical_url
from pipeline.retrieve import feeds
from pipeline.retrieve.articles import Reader, Record, context_item
from pipeline.retrieve.cache import default_cache
from pipeline.retrieve.match import Hit, Query, rank
from pipeline.retrieve.registry import Registry, load_registry
from pipeline.retrieve.sources import Profiler, registrable
from pipeline.retrieve.viginum import load_listing
from pipeline.retrieve.web import Web

log = logging.getLogger(__name__)

FEEDS_TIMEOUT_S = 20.0
ARTICLES_TIMEOUT_S = 50.0
SOURCES_TIMEOUT_S = 25.0
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
    return (registrable(host) or host or "") if host else ""


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


def _context(hits: list[Hit], records: list[Record | None]) -> list[ContextItem]:
    context: list[ContextItem] = []
    seen: set[str] = set()
    for hit, record in zip(hits, records, strict=True):
        if record is None:
            continue
        key = canonical_url(record.url)
        if key in seen:
            continue
        seen.add(key)
        context.append(
            context_item(f"ctx{len(context) + 1}", record, feeds.NAME, hit.item.language)
        )
    return context


async def run(analysis: Analysis) -> RetrievePatch:
    queries = search_queries(analysis)
    document_outlet = analysis.document.outlet if analysis.document else None
    cache = default_cache()
    async with new_client() as client:
        web = Web(client)
        profiler = Profiler(web, cache, _REGISTRY, _LISTING)
        context: list[ContextItem] = []
        feeds_read = 0
        if queries:
            progress.report("Reading news feeds")
            items, feeds_read = await feeds.read_feeds(web, cache, _REGISTRY, FEEDS_TIMEOUT_S)
            hits = select(rank(items, queries), analysis, _REGISTRY)
            progress.report(f"{len(hits)} possibly related reports in {feeds_read} feeds")
            reader = Reader(web, cache)
            records = await _until(
                [reader.read(h.item.url, h.item.published_at) for h in hits],
                ARTICLES_TIMEOUT_S,
                lambda n: progress.report(f"Reading related reports: {n} of {len(hits)}"),
            )
            context = _context(hits, records)
        progress.report(f"{len(context)} related reports; checking the outlets")
        domains = [document_outlet or ""] + [item.outlet or "" for item in context]
        sources = await profiler.profiles(domains, document_outlet, SOURCES_TIMEOUT_S)
    outlets = len({item.outlet for item in context})
    detail = (
        f"{len(context)} related reports from {outlets} outlets ({feeds_read} feeds read)"
        if queries
        else "No search queries, so no related coverage was looked up"
    )
    return RetrievePatch(context=context, sources=sources, detail=detail)
