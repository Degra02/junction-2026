"""Reading one hit: fetch, extract, cache, scraping fallback, and the contract item."""

import asyncio
from datetime import timedelta

import pytest

from pipeline.extract import scraper
from pipeline.extract.fetch import FetchFailed, Page
from pipeline.extract.urls import canonical_url
from pipeline.retrieve.articles import Reader, Record, context_item
from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.tests.conftest import article_page

URL = "https://paper.example/story?utm_source=rss"


def read(server, url=URL, cache=None, **kwargs):
    async def go():
        async with server.client() as client:
            from pipeline.retrieve.web import Web

            reader = Reader(Web(client, guard=lambda u: None), cache or NoCache(), **kwargs)
            return await reader.read(url, "2026-11-13T09:00:00+00:00")

    return asyncio.run(go())


def test_a_readable_page_gives_a_record(server):
    server.pages[URL] = (200, article_page("Tram approvato", "Il consiglio ha approvato il tram."))
    record = read(server)
    assert record.url == URL
    assert record.title == "Tram approvato"
    assert record.text.count("Il consiglio ha approvato il tram.") == 4
    assert record.published_at == "2026-11-14T09:30:00+00:00"  # the page's own date wins
    assert record.language == "it"
    assert record.tracking_ids == ["G-AB12CD34EF"]


@pytest.mark.parametrize(
    "status, body, headers",
    [
        (404, "", None),
        (403, "Forbidden", None),
        (200, "%PDF-1.7", {"content-type": "application/pdf"}),
        (200, "<html><body><nav>Menu only</nav></body></html>", None),
    ],
)
def test_unreadable_pages_give_nothing(server, status, body, headers):
    server.pages[URL] = (status, body, headers) if headers else (status, body)
    assert read(server) is None


def test_records_and_misses_are_cached_for_a_day(server, tmp_path):
    cache = Cache(tmp_path / "r.sqlite")
    server.pages[URL] = (200, article_page("Tram", "Il consiglio ha approvato il tram."))
    first = read(server, cache=cache)
    server.seen.clear()
    assert read(server, cache=cache) == first
    assert server.seen == []

    other = "https://paper.example/menu"
    server.pages[other] = (200, "<html><body><nav>Menu only</nav></body></html>")
    assert read(server, other, cache=cache) is None
    assert cache.get("article", canonical_url(other), timedelta(days=1)) == {}
    server.seen.clear()
    assert read(server, other, cache=cache) is None
    assert server.seen == []  # the miss is remembered


def test_a_network_failure_is_not_cached(server, tmp_path):
    cache = Cache(tmp_path / "r.sqlite")
    server.pages[URL] = (503, "")
    assert read(server, cache=cache) is None
    assert cache.get("article", canonical_url(URL), timedelta(days=1)) is None


def _scraped(url: str, html: str) -> Page:
    return Page(url=url, status=200, content_type="text/html", body=html.encode(), truncated=False)


def test_a_bot_check_falls_back_to_the_scraper_at_most_max_scrapes_times(server, monkeypatch):
    scraped: list[str] = []

    async def scrape(url, *, render=False, client=None):
        scraped.append(url)
        return _scraped(url, article_page("Letto", "Pagina letta dal servizio di scraping."))

    monkeypatch.setattr(scraper, "enabled", lambda: True)
    monkeypatch.setattr(scraper, "scrape_page", scrape)
    urls = [f"https://guarded.example/{i}" for i in range(3)]
    for url in urls:
        server.pages[url] = (403, "Just a moment...")

    async def go():
        async with server.client() as client:
            from pipeline.retrieve.web import Web

            reader = Reader(Web(client, guard=lambda u: None), NoCache(), max_scrapes=2)
            return [await reader.read(u) for u in urls]

    records = asyncio.run(go())
    assert [r is not None for r in records] == [True, True, False]
    assert scraped == urls[:2]
    assert "Pagina letta dal servizio di scraping." in records[0].text


def test_a_page_the_scraper_cannot_read_either_gives_nothing(server, monkeypatch):
    async def scrape(url, *, render=False, client=None):
        raise FetchFailed("The site took too long to answer")

    monkeypatch.setattr(scraper, "enabled", lambda: True)
    monkeypatch.setattr(scraper, "scrape_page", scrape)
    server.pages[URL] = (429, "")
    assert read(server) is None


def test_no_scraping_without_credentials_or_for_plain_failures(server, monkeypatch):
    called = []

    async def scrape(url, *, render=False, client=None):
        called.append(url)

    monkeypatch.setattr(scraper, "scrape_page", scrape)
    server.pages[URL] = (403, "")
    assert read(server) is None  # conftest switched the scraper off
    monkeypatch.setattr(scraper, "enabled", lambda: True)
    server.pages[URL] = (404, "")
    assert read(server) is None  # a missing page is not a bot check: no credit spent
    assert called == []


def test_context_item_maps_the_record():
    record = Record(
        url="https://www.paper.example/story",
        title="Tram",
        text="Body.",
        published_at="2026-11-14T09:30:00+00:00",
        language=None,
        tracking_ids=["G-1"],
        fact_check={"claim": "C", "rating": "False", "publisher": None},
    )
    item = context_item("ctx3", record, "feeds", "it")
    assert item.id == "ctx3"
    assert item.outlet == "paper.example"
    assert item.language == "it"  # the feed's language when the page does not say
    assert item.published_at.isoformat() == "2026-11-14T09:30:00+00:00"
    assert item.fact_check.claim == "C" and item.fact_check.publisher is None
    assert item.retrieved_by == "feeds"
