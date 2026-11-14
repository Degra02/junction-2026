"""Exact-phrase search: phrase choice, GDELT and Oxylabs adapters, and the stage."""

import asyncio
import base64
import itertools
import json
import time

import httpx
import pytest

import pipeline.retrieve as retrieve
from pipeline.common.contracts import Document
from pipeline.retrieve import gdelt, oxylabs
from pipeline.retrieve.cache import NoCache
from pipeline.retrieve.phrases import WORDS, distinctive_phrases
from pipeline.retrieve.tests.conftest import AGENCY_ITEM, article_page
from pipeline.retrieve.tests.test_stage import analysis, run

GDELT_ROUTE = "api.gdeltproject.org/api/v2/doc/doc"
OXY_ROUTE = "realtime.oxylabs.io/v1/queries"
OWN = (
    "Il ministero ha confermato che dal primo gennaio 2027 i pozzi privati dovranno essere "
    "registrati presso gli uffici regionali competenti entro novanta giorni."
)
QUOTED = (
    "«Nessuno vieterà i pozzi, chiederemo soltanto una semplice registrazione online» ha detto."
)
COPY = "https://copy-site.example/2026/11/pozzi"


def doc(*paragraphs: str) -> Document:
    return Document(paragraphs=list(paragraphs), outbound_links=[], tracking_ids=[])


def test_phrases_are_verbatim_windows_from_the_middle_of_own_words_first():
    phrases = distinctive_phrases(doc(QUOTED + " " + OWN, "Troppo corta."))
    assert len(phrases) == 2
    first = phrases[0].split()
    assert len(first) == WORDS
    assert phrases[0] in " ".join(OWN.replace(",", "").replace(".", "").split())
    assert "Il" not in first[:1]  # the window sits in the middle, not at the opening
    assert "registrazione" in phrases[1]  # the quoted sentence only as a fallback


def test_phrases_drop_punctuation_keep_apostrophes_and_are_capped():
    text = " ".join(
        f"Frase numero {i}, con l'Ucraina e il pre-1997: parole diverse ancora {i} qui."
        for i in range(5)
    )
    phrases = distinctive_phrases(doc(text))
    assert len(phrases) == 3
    assert all("," not in p and ":" not in p for p in phrases)
    assert any("l'Ucraina" in p or "pre-1997" in p for p in phrases)
    assert distinctive_phrases(None) == [] and distinctive_phrases(doc("Breve.")) == []


GDELT_ANSWER = {
    "articles": [
        {
            "url": COPY,
            "title": "Pozzi  privati",
            "seendate": "20261113T081500Z",
            "domain": "copy-site.example",
            "language": "Italian",
        },
        {"url": "ftp://nope", "title": "x"},
        {
            "url": "https://other.example/a",
            "title": "Other",
            "seendate": "bad",
            "language": "Klingon",
        },
    ]
}


def test_gdelt_parse():
    copy, other = gdelt.parse(json.dumps(GDELT_ANSWER).encode())
    assert (copy.url, copy.title, copy.language, copy.outlet) == (
        COPY,
        "Pozzi privati",
        "it",
        "copy-site.example",
    )
    assert copy.published_at == "2026-11-13T08:15:00+00:00"
    assert (other.language, other.published_at) == ("", None)
    assert gdelt.parse(b"Please limit requests") == [] and gdelt.parse(b"{}") == []


def test_gdelt_requests_are_paced_and_quoted(server, monkeypatch):
    monkeypatch.setattr(gdelt, "INTERVAL_S", 0.3)
    monkeypatch.setattr(gdelt, "_last_call", 0.0)
    times: list[float] = []

    def route(request):
        times.append(time.monotonic())
        return httpx.Response(200, content=json.dumps(GDELT_ANSWER).encode())

    server.routes[GDELT_ROUTE] = route

    async def go():
        async with server.client() as client:
            return await asyncio.gather(
                *(gdelt.search(client, NoCache(), f"frase {i}") for i in range(3))
            )

    results = asyncio.run(go())
    assert all(len(r) == 2 for r in results)
    assert all(b - a >= 0.29 for a, b in itertools.pairwise(times))
    assert {r.url.params["query"] for r in server.requests} == {
        '"frase 0"',
        '"frase 1"',
        '"frase 2"',
    }


def test_gdelt_rate_limit_gives_nothing(server, monkeypatch):
    monkeypatch.setattr(gdelt, "INTERVAL_S", 0.0)
    server.routes[GDELT_ROUTE] = lambda request: httpx.Response(
        429, content=b"Please limit requests"
    )

    async def go():
        async with server.client() as client:
            return await gdelt.search(client, NoCache(), "una frase")

    assert asyncio.run(go()) == []


def oxy_answer(*urls: str) -> bytes:
    organic = [
        {"url": u, "title": f"T {u}", "desc": "snippet", "pos": i} for i, u in enumerate(urls)
    ]
    return json.dumps({"results": [{"content": {"results": {"organic": organic}}}]}).encode()


def test_oxylabs_parse_drops_google_links():
    items = oxylabs.parse(
        oxy_answer(COPY, "https://www.google.com/search?q=x", "https://youtube.com/w")
    )
    assert [i.url for i in items] == [COPY]
    assert oxylabs.parse(b"{}") == [] and oxylabs.parse(b"[]") == [] and oxylabs.parse(b"x") == []


def test_oxylabs_sends_basic_auth_and_a_quoted_query(server):
    server.routes[OXY_ROUTE] = lambda request: httpx.Response(200, content=oxy_answer(COPY))

    async def go():
        async with server.client() as client:
            return await oxylabs.search(client, NoCache(), "una frase esatta", ("user", "secret"))

    [item] = asyncio.run(go())
    assert item.url == COPY
    [request] = server.requests
    assert request.headers["authorization"] == "Basic " + base64.b64encode(b"user:secret").decode()
    assert "secret" not in str(request.url)
    assert json.loads(request.content)["query"] == '"una frase esatta"'
    assert json.loads(request.content)["source"] == "google_search"


def test_oxylabs_is_off_without_credentials(monkeypatch):
    monkeypatch.delenv(oxylabs.USER_ENV, raising=False)
    monkeypatch.setenv(oxylabs.PASSWORD_ENV, "x")
    assert oxylabs.credentials() is None


@pytest.fixture
def phrase_stage(stage, monkeypatch):
    monkeypatch.setattr(gdelt, "INTERVAL_S", 0.0)
    a = analysis()
    a.document.paragraphs = [OWN]
    stage.routes[GDELT_ROUTE] = lambda request: httpx.Response(
        200, content=json.dumps(GDELT_ANSWER).encode()
    )
    stage.pages[COPY] = (200, article_page("Pozzi privati", OWN))
    return stage, a


def test_a_copy_found_by_exact_phrase_enters_the_context(phrase_stage):
    _, a = phrase_stage
    patch = run(a)
    [copy] = [c for c in patch.context if c.retrieved_by == "gdelt"]
    assert copy.url == COPY and copy.outlet == "copy-site.example"
    assert OWN in copy.text  # read in full, not the search snippet
    assert "copy-site.example" in [s.domain for s in patch.sources]
    assert "(1 by exact phrase)" in patch.detail


def test_oxylabs_hits_join_when_credentials_are_set(phrase_stage, monkeypatch):
    stage, a = phrase_stage
    monkeypatch.setenv(oxylabs.USER_ENV, "user")
    monkeypatch.setenv(oxylabs.PASSWORD_ENV, "secret")
    old = "https://old-mirror.example/2025/03/pozzi"
    stage.routes[OXY_ROUTE] = lambda request: httpx.Response(200, content=oxy_answer(old))
    stage.pages[old] = (200, article_page("Pozzi", OWN))
    patch = run(a)
    by = {c.url: c.retrieved_by for c in patch.context}
    assert by[old] == "oxylabs" and by[COPY] == "gdelt"


def test_the_same_article_from_a_phrase_search_and_a_feed_counts_once(phrase_stage):
    stage, a = phrase_stage
    answer = {"articles": [{"url": AGENCY_ITEM, "title": "x", "language": "Italian"}]}
    stage.routes[GDELT_ROUTE] = lambda request: httpx.Response(
        200, content=json.dumps(answer).encode()
    )
    patch = run(a)
    assert [c.url for c in patch.context].count(AGENCY_ITEM) == 1
    assert next(c for c in patch.context if c.url == AGENCY_ITEM).retrieved_by == "gdelt"


def test_a_slow_phrase_search_is_dropped_at_its_budget(phrase_stage, monkeypatch):
    _, a = phrase_stage
    monkeypatch.setattr(retrieve, "PHRASES_TIMEOUT_S", 0.3)
    original = gdelt.search

    async def slow(*args, **kwargs):
        await asyncio.sleep(5)
        return await original(*args, **kwargs)

    monkeypatch.setattr(gdelt, "search", slow)
    patch = run(a)
    assert all(c.retrieved_by == "feeds" for c in patch.context)
