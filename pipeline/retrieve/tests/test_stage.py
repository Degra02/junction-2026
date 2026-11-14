"""The stage as the worker calls it, offline: fake feeds and pages, permissive URL guard."""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import pipeline.retrieve as retrieve
from pipeline.common import net
from pipeline.common.contracts import (
    Document,
    Language,
    LanguageSupport,
    OutletType,
    RetrievePatch,
    SearchQuery,
)
from pipeline.common.fixtures import example_analysis
from pipeline.extract import browser
from pipeline.extract.fetch import new_client
from pipeline.retrieve.cache import NoCache
from pipeline.retrieve.registry import parse
from pipeline.retrieve.viginum import parse as parse_viginum

AGENCY_FEED = "https://agency.example/rss"
PAPER_FEED = "https://paper.example/rss"


def rss(*items: tuple[str, str]) -> str:
    body = "".join(
        f"<item><title>{title}</title><link>{link}</link>"
        "<pubDate>Sat, 14 Nov 2026 10:00:00 +0000</pubDate></item>"
        for title, link in items
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel>{body}</channel></rss>'


def page(title: str, sentence: str, ga: str) -> str:
    paragraphs = "".join(f"<p>{sentence} Paragraph {i} adds detail on it.</p>" for i in range(4))
    return f"""<html lang="it"><head><title>{title}</title>
<meta property="article:published_time" content="2026-11-14T09:30:00+00:00">
<script>gtag('config', '{ga}');</script></head>
<body><article><h1>{title}</h1>{paragraphs}</article></body></html>"""


@pytest.fixture
def web(monkeypatch):
    """Serve `pages[url] = (status, body)`; unknown URLs answer 404."""
    pages: dict[str, tuple[int, str]] = {}
    seen: list[str] = []

    def handler(request):
        seen.append(str(request.url))
        status, body = pages.get(str(request.url), (404, ""))
        kind = "application/rss+xml" if request.url.path == "/rss" else "text/html"
        return httpx.Response(status, headers={"content-type": kind}, text=body)

    monkeypatch.setattr(net, "assert_public_url", lambda url: None)
    monkeypatch.setattr(browser, "enabled", lambda: False)
    monkeypatch.setattr(retrieve, "new_client", lambda: new_client(httpx.MockTransport(handler)))
    monkeypatch.setattr(retrieve, "default_cache", NoCache)
    monkeypatch.setattr(
        retrieve,
        "_REGISTRY",
        parse(
            {
                "wire_service": [
                    {
                        "domain": "agency.example",
                        "country": "IT",
                        "feeds": [{"url": AGENCY_FEED, "language": "it"}],
                    }
                ],
                "national": [
                    {
                        "domain": "paper.example",
                        "country": "IT",
                        "feeds": [{"url": PAPER_FEED, "language": "it"}],
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(retrieve, "_LISTING", parse_viginum("domain,create date,first seen,type\n"))
    pages[AGENCY_FEED] = (
        200,
        rss(
            ("Garante privacy, multa da 805 milioni a Meta", "https://agency.example/meta"),
            ("Calcio, vince la Roma", "https://agency.example/calcio"),
        ),
    )
    pages[PAPER_FEED] = (
        200,
        rss(
            ("Multa del Garante privacy a Meta", "https://paper.example/meta?utm_source=rss"),
            ("Il documento analizzato", "https://paper.example/own-article"),
        ),
    )
    pages["https://agency.example/meta"] = (
        200,
        page("Garante privacy, multa a Meta", "Il Garante ha multato Meta.", "G-AGENCY0001"),
    )
    pages["https://paper.example/meta?utm_source=rss"] = (
        200,
        page("Multa a Meta", "Meta dovrà pagare 805 milioni al Garante.", "G-PAPER00001"),
    )
    pages["https://paper.example/own-article"] = (200, page("x", "y", "G-OWN0000001"))
    return pages, seen


def analysis():
    a = example_analysis()
    a.language = Language(code="it", confidence=0.99, support=LanguageSupport.evaluated)
    a.document = Document(
        url="https://blog.example/post",
        outlet="blog.example",
        title=None,
        paragraphs=["Il Garante della privacy ha multato Meta."],
        outbound_links=[],
        tracking_ids=[],
    )
    a.queries = [SearchQuery(text="Garante privacy multa Meta", language="it")]
    a.claims = []
    a.context = []
    a.sources = []
    return a


def test_related_reports_come_with_full_bodies_and_typed_outlets(web):
    patch = asyncio.run(retrieve.run(analysis()))

    assert [c.id for c in patch.context] == ["ctx1", "ctx2"]
    agency, paper = patch.context
    # The agency original comes first: the syndication guard needs it.
    assert agency.outlet == "agency.example"
    assert agency.retrieved_by == "feeds"
    assert agency.tracking_ids == ["G-AGENCY0001"]
    assert "Il Garante ha multato Meta." in agency.text
    assert agency.text.count("Paragraph") == 4  # the whole body, not a summary
    assert agency.published_at is not None and agency.published_at.isoformat().startswith(
        "2026-11-14T09:30"
    )
    assert agency.language == "it"
    assert agency.fact_check is None and agency.in_story is None  # in_story is story's job
    assert paper.outlet == "paper.example"

    sources = {s.domain: s for s in patch.sources}
    assert list(sources) == ["blog.example", "agency.example", "paper.example"]
    assert sources["agency.example"].outlet_type == OutletType.wire_service
    assert sources["paper.example"].outlet_type == OutletType.national
    assert sources["blog.example"].outlet_type is None  # unknown: not guessed
    assert patch.detail == "2 related reports from 2 outlets (2 feeds read)"


def test_the_document_itself_and_unrelated_items_are_not_fetched(web):
    _, seen = web
    a = analysis()
    a.document.url = "https://paper.example/own-article"
    a.document.outlet = "paper.example"
    patch = asyncio.run(retrieve.run(a))
    assert [c.outlet for c in patch.context] == ["agency.example"]
    assert "https://paper.example/own-article" not in seen
    assert "https://agency.example/calcio" not in seen


def test_a_dead_source_does_not_fail_the_stage(web):
    pages, _ = web
    pages[AGENCY_FEED] = (503, "")
    pages["https://paper.example/meta?utm_source=rss"] = (500, "")
    patch = asyncio.run(retrieve.run(analysis()))
    assert patch.context == []
    assert [s.domain for s in patch.sources] == ["blog.example"]


def test_no_queries_means_no_search(web):
    _, seen = web
    a = analysis()
    a.queries = []
    patch = asyncio.run(retrieve.run(a))
    assert patch.context == [] and seen == []
    assert patch.detail == "No search queries, so no related coverage was looked up"


def test_rdap_fills_the_registration_date(web, monkeypatch):
    pages, _ = web
    monkeypatch.setattr(
        retrieve,
        "_LISTING",
        parse_viginum("domain,create date,first seen,type\npravda-it[.]com,01/03/2024,,domain\n"),
    )
    a = analysis()
    a.queries = []
    a.document.url = "https://news.pravda-it.com/post"
    a.document.outlet = "news.pravda-it.com"
    rdap = {"events": [{"eventAction": "registration", "eventDate": "2024-02-29T10:00:00Z"}]}
    pages["https://rdap.org/domain/pravda-it.com"] = (200, json.dumps(rdap))
    [profile] = asyncio.run(retrieve.run(a)).sources
    assert profile.domain == "news.pravda-it.com"
    assert profile.known_network == "portal_kombat"
    assert profile.registered_at.isoformat() == "2024-02-29T10:00:00+00:00"
    assert profile.first_cert_at is None  # crt.sh answered 404


def test_through_the_worker_endpoint(web):
    from worker.app import app

    body = analysis().model_dump(mode="json")
    response = TestClient(app).post("/stages/retrieve", json=body)
    assert response.status_code == 200, response.text
    patch = RetrievePatch.model_validate(response.json())
    assert len(patch.context) == 2
