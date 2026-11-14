"""The Oxylabs AI Studio fallback: Markdown to article, the API calls, failures, and extract."""

import asyncio
import json

import httpx
import pytest

import pipeline.extract as extract
from pipeline.common import net
from pipeline.common.contracts import Input, InputKind
from pipeline.common.errors import StageError
from pipeline.common.fixtures import example_analysis
from pipeline.extract import scraper
from pipeline.extract.fetch import FetchFailed, new_client
from pipeline.extract.scraper import article_html, prose_blocks, scrape_page

URL = "https://guarded.example/2026/11/story"
PARAGRAPHS = [
    f"Paragraph {i}: the city council approved the new tram line after a debate of six hours."
    for i in range(4)
]
MARKDOWN = "\n\n".join(
    [
        "[Skip to content](#main) [Home](/) [World](/world)",
        "* [Politics](/politics)\n* [Sport](/sport)",
        "# Tram line approved",
        *PARAGRAPHS,
        "To watch this video you need to accept the audience measurement cookies.",
        "Read also: [another story with a long title](https://guarded.example/other) today.",
        "| table | row |",
        "Subscribe to our newsletter to get the best stories of the week in your inbox.",
    ]
)


def test_prose_blocks_keep_the_article_and_drop_the_rest():
    title, paragraphs = prose_blocks(MARKDOWN)
    assert title == "Tram line approved"
    assert paragraphs == PARAGRAPHS


def test_repeated_blocks_are_page_furniture():
    furniture = "This block repeats on the page, so it belongs to the template, not the article."
    _, paragraphs = prose_blocks("\n\n".join([furniture, *PARAGRAPHS, furniture]))
    assert paragraphs == PARAGRAPHS


def test_article_html_needs_enough_prose():
    page = article_html(MARKDOWN)
    assert page is not None and "<h1>Tram line approved</h1>" in page
    assert page.count("<p>") == 4
    assert article_html("\n\n".join(PARAGRAPHS[:2])) is None  # too little: unreadable
    assert "&lt;b&gt;" in article_html("\n\n".join(p + " <b>x</b>." for p in PARAGRAPHS))


class Api:
    """Fake AI Studio: `/scrape` creates a run; `/scrape/run/data` completes after `polls`."""

    def __init__(self, markdown=MARKDOWN, create_status=200, polls=1, final="completed"):
        self.markdown, self.create_status, self.polls, self.final = (
            markdown,
            create_status,
            polls,
            final,
        )
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/scrape":
            return httpx.Response(self.create_status, json={"run_id": "r1"})
        self.polls -= 1
        if self.polls > 0:
            return httpx.Response(200, json={"status": "processing", "data": None})
        return httpx.Response(200, json={"status": self.final, "data": self.markdown})


def scrape(api, **kwargs):
    async def go():
        async with new_client(httpx.MockTransport(api)) as client:
            return await scrape_page(URL, client=client, **kwargs)

    return asyncio.run(go())


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv(scraper.TOKEN_ENV, "test-key-not-real")
    monkeypatch.setattr(net, "assert_public_url", lambda url: None)
    monkeypatch.setattr(scraper, "POLL_S", 0.01)
    return monkeypatch


def test_a_scrape_is_created_polled_and_read(key):
    api = Api(polls=3)
    page = scrape(api)
    assert page.url == URL and page.status == 200
    assert b"<h1>Tram line approved</h1>" in page.body
    create, *polls = api.requests
    assert create.url == "https://api-aistudio.oxylabs.io/scrape"
    assert create.headers["x-api-key"] == "test-key-not-real"
    assert "test-key-not-real" not in str(create.url)
    assert json.loads(create.content) == {
        "url": URL,
        "output_format": "markdown",
        "render_javascript": False,
    }
    assert len(polls) == 3 and all(p.url.params["run_id"] == "r1" for p in polls)
    scrape(Api(), render=True)


@pytest.mark.parametrize("status", [401, 402, 403, 429, 500])
def test_provider_errors_give_a_plain_reason(key, status):
    with pytest.raises(FetchFailed, match="refused"):
        scrape(Api(create_status=status))


def test_a_failed_or_endless_run(key):
    with pytest.raises(FetchFailed, match="refused"):
        scrape(Api(final="failed"))
    key.setattr(scraper, "SCRAPE_TIMEOUT_S", 0.05)
    with pytest.raises(FetchFailed, match="too long"):
        scrape(Api(polls=10_000))


def test_a_page_without_enough_prose_is_unreadable(key):
    with pytest.raises(FetchFailed, match="article"):
        scrape(Api(markdown="# Video\n\nTo watch this you need cookies."))


def test_network_errors(key):
    def broken(request):
        raise httpx.ConnectError("down", request=request)

    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(FetchFailed, match="could not be reached"):
        scrape(broken)
    with pytest.raises(FetchFailed, match="too long"):
        scrape(slow)


def test_private_urls_are_refused_before_spending_credit(key):
    def refuse(url):
        raise StageError("The link does not point to a public website")

    key.setattr(net, "assert_public_url", refuse)
    api = Api()
    with pytest.raises(FetchFailed, match="public website"):
        scrape(api)
    assert api.requests == []


def test_without_a_key_nothing_is_sent(monkeypatch):
    monkeypatch.delenv(scraper.TOKEN_ENV, raising=False)
    assert not scraper.enabled()
    with pytest.raises(FetchFailed):
        scrape(lambda request: pytest.fail("no request expected"))


# extract with the fallback

ARTICLE = article_html(MARKDOWN)


def run_url(monkeypatch, plain_status, plain_body, scraped):
    """extract on URL: plain fetch answers `plain_status`; the scraper returns `scraped(render)`."""
    monkeypatch.setattr(net, "assert_public_url", lambda url: None)
    monkeypatch.setattr(scraper, "enabled", lambda: True)
    renders: list[bool] = []

    async def fake_scrape(url, *, render=False, client=None):
        renders.append(render)
        html = scraped(render)
        if html is None:
            raise FetchFailed("We could not find an article on that page")
        from pipeline.extract.fetch import Page

        return Page(url, 200, "text/html", html.encode(), False)

    monkeypatch.setattr(scraper, "scrape_page", fake_scrape)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            plain_status, headers={"content-type": "text/html"}, text=plain_body
        )
    )
    monkeypatch.setattr(extract, "new_client", lambda: new_client(transport))
    a = example_analysis()
    a.input = Input(kind=InputKind.url, value=URL)
    return asyncio.run(extract.run(a)), renders


def test_a_bot_check_is_read_through_the_scraper(monkeypatch):
    patch, renders = run_url(monkeypatch, 403, "Just a moment...", lambda render: ARTICLE)
    assert renders == [False]  # the cheap, unrendered read was enough
    assert patch.document.paragraphs == PARAGRAPHS
    assert patch.document.outlet == "guarded.example"


def test_an_unrendered_read_without_an_article_is_tried_rendered(monkeypatch):
    patch, renders = run_url(monkeypatch, 403, "", lambda render: ARTICLE if render else None)
    assert renders == [False, True]
    assert patch.document.paragraphs == PARAGRAPHS


def test_a_javascript_page_goes_straight_to_a_rendered_read(monkeypatch):
    shell = "<html><body><div id='app'></div><script>render()</script></body></html>"
    patch, renders = run_url(monkeypatch, 200, shell, lambda render: ARTICLE)
    assert renders == [True]
    assert patch.document.paragraphs == PARAGRAPHS


def test_no_article_even_rendered_gives_the_plain_reason(monkeypatch):
    # The site's own refusal is the honest reason, not "no article".
    with pytest.raises(StageError, match=r"refused to let us read the page \(HTTP 403\)"):
        run_url(monkeypatch, 403, "", lambda render: None)
    # A page that answered but holds no article even rendered: say so.
    with pytest.raises(StageError, match="paste its text"):
        run_url(monkeypatch, 200, "<html><body>Menu</body></html>", lambda render: None)


# --- scrape_raw: feeds and API endpoints, passed through unchanged ---------------------------

FEED = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry/></feed>'


def raw(api, url=URL):
    async def go():
        async with new_client(httpx.MockTransport(api)) as client:
            return await scraper.scrape_raw(url, client=client)

    return asyncio.run(go())


def test_a_raw_scrape_returns_the_answer_unchanged(key):
    api = Api(markdown=FEED)
    page = raw(api)
    assert page.body == FEED.encode() and page.status == 200 and page.url == URL
    create = api.requests[0]
    assert json.loads(create.content) == {
        "url": URL,
        "output_format": "markdown",
        "render_javascript": False,
    }
    assert create.headers["x-api-key"] == "test-key-not-real"


def test_a_raw_scrape_fails_with_plain_reasons(key):
    with pytest.raises(FetchFailed, match="refused"):
        raw(Api(create_status=402))

    def down(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(FetchFailed, match="could not be reached"):
        raw(down)

    def slow(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(FetchFailed, match="took too long"):
        raw(slow)


def test_a_raw_scrape_refuses_private_addresses_and_needs_a_key(key, monkeypatch):
    def guard(url):
        raise StageError("The link does not point to a public website")

    api = Api()
    monkeypatch.setattr(net, "assert_public_url", guard)
    with pytest.raises(FetchFailed, match="public website"):
        raw(api)
    monkeypatch.delenv(scraper.TOKEN_ENV)
    with pytest.raises(FetchFailed, match="refused"):
        raw(api)
    assert api.requests == []
