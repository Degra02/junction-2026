"""Retrieve on the real web. Skipped unless RUN_LIVE=1 (CI must not depend on outside sites).

    RUN_LIVE=1 uv run pytest pipeline/retrieve/tests/test_live.py -v

Queries are built at run time from a current agency headline, so the tests do not rot as news
moves: the story is in the feeds by construction, and other outlets usually cover it too.
"""

import asyncio
import os

import pytest

import pipeline.retrieve as retrieve
from pipeline.common.contracts import Document, Language, LanguageSupport, OutletType, SearchQuery
from pipeline.common.fixtures import example_analysis
from pipeline.extract.fetch import new_client
from pipeline.retrieve.cache import NoCache
from pipeline.retrieve.feeds import read_feeds
from pipeline.retrieve.registry import load_registry
from pipeline.retrieve.sources import Profiler
from pipeline.retrieve.viginum import Listing
from pipeline.retrieve.web import Web

pytestmark = pytest.mark.skipif(not os.environ.get("RUN_LIVE"), reason="set RUN_LIVE=1")


def test_most_curated_feeds_answer():
    async def go():
        async with new_client() as client:
            return await read_feeds(Web(client), NoCache(), load_registry(), 20.0)

    items, answered = asyncio.run(go())
    feeds = len(load_registry().feeds())
    assert answered >= 0.8 * feeds, f"only {answered} of {feeds} feeds answered"
    assert len(items) > 500


def test_a_current_agency_story_gets_full_body_context_in_budget(monkeypatch):
    monkeypatch.setattr(retrieve, "default_cache", NoCache)

    async def headline() -> str:
        async with new_client() as client:
            items, _ = await read_feeds(Web(client), NoCache(), load_registry(), 20.0)
        agency = [i for i in items if i.outlet == "ansa.it" and i.language == "it"]
        return max(agency, key=lambda i: i.published_at or "").title

    title = asyncio.run(headline())
    a = example_analysis()
    a.language = Language(code="it", confidence=0.99, support=LanguageSupport.evaluated)
    a.document = Document(paragraphs=[title], outbound_links=[], tracking_ids=[])
    a.queries = [SearchQuery(text=title, language="it")]
    a.claims, a.context, a.sources = [], [], []

    loop_start = asyncio.new_event_loop()
    start = loop_start.time()
    patch = loop_start.run_until_complete(retrieve.run(a))
    elapsed = loop_start.time() - start
    loop_start.close()

    assert elapsed < 110, f"retrieve took {elapsed:.0f} s"
    assert patch.context, f"no context for {title!r}"
    assert len({c.id for c in patch.context}) == len(patch.context)
    for item in patch.context:
        assert len(item.text) >= 200, item.url  # full bodies, never feed summaries
        assert item.outlet and item.retrieved_by == "feeds"
    domains = [s.domain for s in patch.sources]
    assert len(domains) == len(set(domains))
    assert {c.outlet for c in patch.context} <= set(domains)
    typed = {s.domain: s.outlet_type for s in patch.sources}
    assert typed.get("ansa.it", OutletType.wire_service) == OutletType.wire_service


def test_rdap_gives_registration_dates():
    async def go():
        async with new_client() as client:
            profiler = Profiler(Web(client), NoCache(), load_registry(), Listing())
            return await profiler.profiles(["theguardian.com", "fullfact.org"], None, 25.0)

    guardian, fullfact = asyncio.run(go())
    assert guardian.registered_at is not None and guardian.registered_at.year < 2000
    assert fullfact.outlet_type == OutletType.fact_checker
