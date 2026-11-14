"""The stage as the worker calls it, offline: fake feeds and pages (conftest `server`)."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

import pipeline.retrieve as retrieve
from pipeline.common import progress
from pipeline.common.contracts import (
    Claim,
    Document,
    Language,
    LanguageSupport,
    OutletType,
    RetrievePatch,
    SearchQuery,
    Span,
)
from pipeline.common.fixtures import example_analysis
from pipeline.retrieve.cache import NoCache
from pipeline.retrieve.registry import parse
from pipeline.retrieve.tests.conftest import article_page, rss
from pipeline.retrieve.viginum import parse as parse_viginum

AGENCY_FEED = "https://agency.example/rss"
PAPER_FEED = "https://paper.example/rss"
CHECKER_FEED = "https://checker.example/rss"
AGENCY_ITEM = "https://agency.example/meta"
PAPER_ITEM = "https://paper.example/meta?utm_source=rss"

CLAIM_REVIEW = json.dumps(
    {
        "@context": "https://schema.org",
        "@type": "ClaimReview",
        "claimReviewed": "Meta was fined 805 billion euros",
        "reviewRating": {"@type": "Rating", "alternateName": "False"},
        "author": {"@type": "Organization", "name": "Checker"},
    }
)
HEADER = "domain,create date,first seen,type\n"
PAYWALL = (
    '<script type="application/ld+json">'
    '{"@type": "NewsArticle", "isAccessibleForFree": false}</script>'
)


def _feed(url: str) -> dict:
    return {"url": url, "language": "it"}


@pytest.fixture
def stage(server, monkeypatch):
    """Three curated outlets (agency, newspaper, fact-checker); one matching item each for the
    agency and the newspaper."""
    monkeypatch.setattr(retrieve, "new_client", server.client)
    monkeypatch.setattr(retrieve, "default_cache", NoCache)
    registry = {
        "wire_service": [{"domain": "agency.example", "feeds": [_feed(AGENCY_FEED)]}],
        "national": [{"domain": "paper.example", "feeds": [_feed(PAPER_FEED)]}],
        "fact_checker": [{"domain": "checker.example", "feeds": [_feed(CHECKER_FEED)]}],
    }
    for entries in registry.values():
        entries[0]["country"] = "IT"
    monkeypatch.setattr(retrieve, "_REGISTRY", parse(registry))
    # A configured (non-empty) list, so no download is attempted; see test_viginum_download_*.
    monkeypatch.setattr(
        retrieve, "_LISTING", parse_viginum(HEADER + "unrelated[.]example,,,domain\n")
    )
    server.pages[AGENCY_FEED] = (
        200,
        rss(
            ("Garante privacy, multa da 805 milioni a Meta", AGENCY_ITEM),
            ("Calcio, vince la Roma", "https://agency.example/calcio"),
        ),
    )
    server.pages[PAPER_FEED] = (
        200,
        rss(
            ("Multa del Garante privacy a Meta", PAPER_ITEM),
            ("Il documento analizzato", "https://paper.example/own-article"),
        ),
    )
    server.pages[CHECKER_FEED] = (200, rss())
    server.pages[AGENCY_ITEM] = (
        200,
        article_page(
            "Garante privacy, multa a Meta", "Il Garante ha multato Meta.", "G-AGENCY0001"
        ),
    )
    server.pages[PAPER_ITEM] = (
        200,
        article_page("Multa a Meta", "Meta dovrà pagare 805 milioni al Garante.", "G-PAPER00001"),
    )
    server.pages["https://paper.example/own-article"] = (200, article_page("x", "y"))
    return server


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


def run(a=None) -> RetrievePatch:
    return asyncio.run(retrieve.run(a or analysis()))


def test_related_reports_come_with_full_bodies_and_typed_outlets(stage):
    patch = run()

    assert [c.id for c in patch.context] == ["ctx1", "ctx2"]
    agency, paper = patch.context
    # The agency original comes first: the syndication guard needs it.
    assert agency.outlet == "agency.example"
    assert agency.url == AGENCY_ITEM
    assert agency.retrieved_by == "feeds"
    assert agency.tracking_ids == ["G-AGENCY0001"]
    assert "Il Garante ha multato Meta." in agency.text
    assert agency.text.count("Paragraph") == 4  # the whole body, not a summary
    assert agency.published_at.isoformat() == "2026-11-14T09:30:00+00:00"
    assert agency.language == "it"
    assert agency.fact_check is None
    # Story's fields stay empty.
    assert (agency.similarity, agency.in_story, agency.story_reason) == (None, None, None)
    assert paper.outlet == "paper.example"

    sources = {s.domain: s for s in patch.sources}
    assert list(sources) == ["blog.example", "agency.example", "paper.example"]
    assert sources["agency.example"].outlet_type == OutletType.wire_service
    assert sources["agency.example"].country == "IT"
    assert sources["paper.example"].outlet_type == OutletType.national
    assert sources["blog.example"].outlet_type is None  # unknown: not guessed
    assert patch.detail == "2 related reports from 2 outlets (2 feeds read)"


def test_the_document_itself_its_outlet_and_unrelated_items_are_not_fetched(stage):
    a = analysis()
    a.document.url = "https://paper.example/own-article"
    a.document.outlet = "www.paper.example"
    patch = run(a)
    assert [c.outlet for c in patch.context] == ["agency.example"]
    assert "https://paper.example/own-article" not in stage.seen
    assert PAPER_ITEM not in stage.seen  # same outlet as the document
    assert "https://agency.example/calcio" not in stage.seen


def test_a_fact_check_page_becomes_a_fact_check_item(stage):
    item = "https://checker.example/meta-fine"
    stage.pages[CHECKER_FEED] = (200, rss(("Multa Garante privacy a Meta da 805 miliardi?", item)))
    head = f'<script type="application/ld+json">{CLAIM_REVIEW}</script>'
    stage.pages[item] = (
        200,
        article_page("Verifica", "La multa è di 805 milioni, non miliardi.", head=head),
    )
    checks = [c for c in run().context if c.fact_check is not None]
    assert len(checks) == 1
    check = checks[0]
    assert check.fact_check.model_dump() == {
        "claim": "Meta was fined 805 billion euros",
        "rating": "False",
        "publisher": "Checker",
    }
    # The contract: the reviewed claim, then the verdict text.
    assert check.text.startswith("Meta was fined 805 billion euros\n\nLa multa è di 805 milioni")


def test_a_paywalled_page_is_left_out(stage):
    stage.pages[PAPER_ITEM] = (200, article_page("Multa a Meta", "Solo abbonati.", head=PAYWALL))
    assert [c.outlet for c in run().context] == ["agency.example"]


def test_two_links_to_the_same_article_give_one_item(stage):
    final = "https://www.paper.example/meta"
    stage.pages[PAPER_FEED] = (
        200,
        rss(
            ("Multa del Garante privacy a Meta", PAPER_ITEM),
            ("Garante privacy: multa a Meta", "https://paper.example/short-link"),
        ),
    )
    stage.pages[final] = stage.pages[PAPER_ITEM]
    stage.pages[PAPER_ITEM] = (301, "", {"location": final})
    stage.pages["https://paper.example/short-link"] = (301, "", {"location": final})
    patch = run()
    assert [c.url for c in patch.context] == [AGENCY_ITEM, final]
    assert [c.id for c in patch.context] == ["ctx1", "ctx2"]


def test_at_most_three_hits_per_outlet_and_max_hits_overall(stage, monkeypatch):
    links = [f"https://paper.example/meta-{i}" for i in range(5)]
    stage.pages[PAPER_FEED] = (
        200,
        rss(*[(f"Garante privacy multa Meta {i}", link) for i, link in enumerate(links)]),
    )
    for i, link in enumerate(links):
        stage.pages[link] = (200, article_page(f"Multa {i}", f"Versione {i} della notizia."))
    patch = run()
    assert sum(c.outlet == "paper.example" for c in patch.context) == retrieve.PER_OUTLET
    monkeypatch.setattr(retrieve, "MAX_HITS", 2)
    assert len(run().context) == 2


def test_slow_pages_are_dropped_at_the_budget(stage, monkeypatch):
    monkeypatch.setattr(retrieve, "ARTICLES_TIMEOUT_S", 0.5)
    stage.delays[PAPER_ITEM] = 5
    patch = run()
    assert [c.outlet for c in patch.context] == ["agency.example"]


def test_slow_feeds_are_dropped_at_the_budget(stage, monkeypatch):
    monkeypatch.setattr(retrieve, "FEEDS_TIMEOUT_S", 0.5)
    stage.delays[AGENCY_FEED] = 5
    patch = run()
    assert [c.outlet for c in patch.context] == ["paper.example"]
    assert patch.detail == "1 related reports from 1 outlets (1 feeds read)"


def test_a_dead_source_does_not_fail_the_stage(stage):
    stage.pages[AGENCY_FEED] = (503, "")
    stage.pages[PAPER_ITEM] = (500, "")
    patch = run()
    assert patch.context == []
    assert [s.domain for s in patch.sources] == ["blog.example"]


def test_a_crashing_reader_does_not_fail_the_stage(stage, monkeypatch):
    from pipeline.retrieve import articles

    async def broken(self, url, fallback_published=None):
        raise RuntimeError("bug")

    monkeypatch.setattr(articles.Reader, "read", broken)
    assert run().context == []


def test_no_queries_means_no_search(stage):
    a = analysis()
    a.queries = []
    patch = run(a)
    assert patch.context == [] and stage.seen == []
    assert patch.detail == "No search queries, so no related coverage was looked up"


def test_pasted_text_without_outlet_still_searches(stage):
    a = analysis()
    a.document = Document(
        paragraphs=["Il Garante della privacy ha multato Meta."], outbound_links=[], tracking_ids=[]
    )
    patch = run(a)
    assert len(patch.context) == 2
    assert [s.domain for s in patch.sources] == ["agency.example", "paper.example"]


def test_claims_and_title_also_find_coverage(stage):
    a = analysis()
    a.queries = []
    a.document.title = "Garante privacy, multa a Meta"
    a.claims = [
        Claim(id="cl1", text="Meta multa Garante privacy", span=Span(paragraph=0, start=0, end=1))
    ]
    assert len(run(a).context) == 2


def test_progress_notes(stage, monkeypatch):
    notes: list[str] = []
    monkeypatch.setattr(progress, "report", notes.append)
    run()
    assert notes[0] == "Reading news feeds"
    assert "2 possibly related reports in 2 feeds" in notes
    assert "Reading related reports: 2 of 2" in notes
    assert notes[-1] == "2 related reports; checking the outlets"
    assert not any("http" in n for n in notes)  # notes are public: no URLs


def test_rdap_crtsh_and_viginum_fill_the_document_outlet(stage, monkeypatch):
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
    stage.pages["https://rdap.org/domain/pravda-it.com"] = (200, json.dumps(rdap))
    certs = [{"not_before": "2024-03-01T08:00:00"}]
    stage.pages["https://crt.sh/?q=pravda-it.com&output=json"] = (200, json.dumps(certs))
    [profile] = run(a).sources
    assert profile.domain == "news.pravda-it.com"  # as the document writes it
    assert profile.known_network == "portal_kombat"
    assert profile.registered_at.isoformat() == "2024-02-29T10:00:00+00:00"
    assert profile.first_cert_at.isoformat() == "2024-03-01T08:00:00+00:00"


def test_through_the_worker_endpoint(stage):
    from worker.app import app

    response = TestClient(app).post("/stages/retrieve", json=analysis().model_dump(mode="json"))
    assert response.status_code == 200, response.text
    patch = RetrievePatch.model_validate(response.json())
    assert len(patch.context) == 2


def test_viginum_download_when_no_file_is_configured(stage, monkeypatch):
    from pipeline.retrieve import viginum

    monkeypatch.setattr(retrieve, "_LISTING", parse_viginum(HEADER))
    stage.pages[viginum.SOURCE_URL] = (
        200,
        "\ufeff" + HEADER + "blog[.]example,01/03/2024,,domain\n",
    )
    [blog, *_] = run().sources
    assert blog.domain == "blog.example" and blog.known_network == "portal_kombat"
    assert viginum.SOURCE_URL in stage.seen


def test_viginum_download_failure_or_timeout_leaves_networks_empty(stage, monkeypatch):
    from pipeline.retrieve import viginum

    monkeypatch.setattr(retrieve, "_LISTING", parse_viginum(HEADER))
    stage.pages[viginum.SOURCE_URL] = (503, "")
    patch = run()
    assert len(patch.context) == 2 and all(s.known_network is None for s in patch.sources)

    monkeypatch.setattr(retrieve, "VIGINUM_TIMEOUT_S", 0.3)
    stage.pages[viginum.SOURCE_URL] = (200, HEADER + "blog[.]example,,,domain\n")
    stage.delays[viginum.SOURCE_URL] = 5
    patch = run()
    assert len(patch.context) == 2 and all(s.known_network is None for s in patch.sources)


def test_a_listed_site_that_moved_is_caught_through_the_submitted_url(stage, monkeypatch):
    from pipeline.common.contracts import Input, InputKind

    monkeypatch.setattr(
        retrieve, "_LISTING", parse_viginum(HEADER + "pravda-xx[.]com,22/02/2023,,domain\n")
    )
    a = analysis()
    a.queries = []
    a.input = Input(kind=InputKind.url, value="https://pravda-xx.com/2026/11/post")
    a.document.url = "https://brand-new-mirror.example/2026/11/post"  # where it redirected
    a.document.outlet = "brand-new-mirror.example"
    [profile] = run(a).sources
    assert profile.domain == "brand-new-mirror.example"
    assert profile.known_network == "portal_kombat"
    assert profile.registered_at is None  # the listed domain's date is not this domain's


def test_no_redirect_no_borrowed_listing(stage, monkeypatch):
    from pipeline.common.contracts import Input, InputKind

    monkeypatch.setattr(
        retrieve, "_LISTING", parse_viginum(HEADER + "pravda-xx[.]com,22/02/2023,,domain\n")
    )
    a = analysis()
    a.queries = []
    a.input = Input(kind=InputKind.text, value="Pasted text")
    [profile] = run(a).sources
    assert profile.known_network is None
