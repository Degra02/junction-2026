"""Adapters for social media posts, offline: fake Bluesky search, fake Oxylabs search, fake
platform endpoints (conftest `server`). Payloads are hand-written in each platform's shape."""

import asyncio
import json

import httpx
import pytest

import pipeline.retrieve as retrieve
from pipeline.common.contracts import Document, Language, LanguageSupport, RetrievePatch
from pipeline.common.fixtures import example_analysis
from pipeline.extract import scraper
from pipeline.extract import social as posts
from pipeline.extract.social import Post
from pipeline.retrieve import social
from pipeline.retrieve.cache import Cache, NoCache

SENTENCE = (
    "The council secretly sold the harbour to a foreign investment fund during a closed "
    "session held last night."
)
# The ten-word window `distinctive_phrases` takes from the middle of SENTENCE.
PHRASE = "secretly sold the harbour to a foreign investment fund during"
BSKY_ROUTE = "api.bsky.app/xrpc/app.bsky.feed.searchPosts"
OXY_ROUTE = "api-aistudio.oxylabs.io/search/instant"
X_ROUTE = "publish.twitter.com/oembed"


def bsky(text: str, handle: str, rkey: str = "3kabc2defgh2x", at: str = "2026-11-14T10:00:00Z"):
    return {
        "uri": f"at://did:plc:{handle.split('.')[0]}/app.bsky.feed.post/{rkey}",
        "author": {"handle": handle},
        "record": {"createdAt": at, "langs": ["en"], "text": text},
    }


def bsky_answer(*entries: dict) -> httpx.Response:
    return httpx.Response(200, json={"posts": list(entries)})


def x_answer(request: httpx.Request, text: str = SENTENCE) -> httpx.Response:
    link = request.url.params["url"]
    user = link.split("/")[3]
    return httpx.Response(
        200,
        json={
            "url": link,
            "author_url": f"https://twitter.com/{user}",
            "html": f'<blockquote><p lang="en">{text}</p>&mdash; {user} '
            f'<a href="{link}">November 8, 2024</a></blockquote>',
        },
    )


def post(platform="bluesky", author="@a", text=SENTENCE, url=None, at="2026-11-14T10:00:00Z"):
    url = url or f"https://bsky.app/profile/{author.strip('@')}/post/3kabc2defgh2x"
    return Post(platform=platform, url=url, author=author, text=text, published_at=at)


def find(server, phrases=(PHRASE,), own_url=None, cache=None):
    async def go():
        async with server.client() as client:
            web = server.web()
            web.client = client
            return await social.find_posts(web, cache or NoCache(), list(phrases), own_url)

    return asyncio.run(go())


# --- parsing ---------------------------------------------------------------------------------


def test_bluesky_search_answers():
    body = json.dumps({"posts": [bsky(SENTENCE, "alice.example"), {"uri": "broken"}, 7]}).encode()
    found = social.parse_bluesky_search(body)
    assert [(p.author, p.text) for p in found] == [("@alice.example", SENTENCE)]
    for bad in (b"not json", b"[]", b"{}", b'{"posts": 3}'):
        assert social.parse_bluesky_search(bad) == []


def test_web_search_answers_keep_only_posts_once_each():
    data = [
        {"url": "https://x.com/alice/status/1855000000000000000"},
        {"url": "https://twitter.com/alice/status/1855000000000000000?s=20"},  # the same post
        {"url": "https://www.reddit.com/r/news/comments/1abc2d/title/"},
        {"url": "https://www.reddit.com/r/news/"},  # a community, not a post
        {"url": "https://www.google.com/goto?url=CAES"},  # an opaque redirect
        {"url": "https://paper.example/harbour"},
        {"url": None},
        "junk",
    ]
    refs = social.parse_web_search(json.dumps({"data": data}).encode())
    assert [r.url for r in refs] == [
        "https://x.com/alice/status/1855000000000000000",
        "https://www.reddit.com/comments/1abc2d",
    ]
    for bad in (b"x", b"[]", b'{"data": 1}'):
        assert social.parse_web_search(bad) == []


# --- select ----------------------------------------------------------------------------------


def test_only_posts_that_repeat_a_phrase_are_kept():
    found = [
        post(author="@copy", text=SENTENCE.upper()),  # case does not matter
        post(author="@topic", text="The harbour sale is all anyone at the council talks about."),
        post(author="@short", text="secretly sold"),
    ]
    assert [p.author for p in social.select(found, [PHRASE], None)] == ["@copy"]
    assert social.select(found, [], None) == []


def test_a_reddit_title_counts_as_the_authors_words():
    found = [post("reddit", "u/a", text="", url="https://www.reddit.com/comments/1abc2d")]
    found[0].title = SENTENCE
    assert social.select(found, [PHRASE], None) == found


def test_the_document_itself_is_not_its_own_copy():
    mine = "https://bsky.app/profile/me.example/post/3kabc2defgh2x"
    found = [post(author="@me.example", url=mine), post(author="@other.example")]
    kept = social.select(found, [PHRASE], "https://bsky.app/profile/ME.example/post/3kabc2defgh2x")
    assert [p.author for p in kept] == ["@other.example"]


def test_one_post_per_account_and_the_earliest_first():
    found = [
        post(author="@b", at="2026-11-14T12:00:00Z"),
        post(
            author="@a",
            at="2026-11-14T11:00:00Z",
            url="https://bsky.app/profile/a/post/3kaaaaaaaaa2a",
        ),
        post(
            author="@A",
            at="2026-11-14T09:00:00Z",
            url="https://bsky.app/profile/a/post/3kbbbbbbbbb2b",
        ),
        post(author="@undated", at=None),
    ]
    kept = social.select(found, [PHRASE], None)
    assert [(p.author, p.published_at) for p in kept] == [
        ("@A", "2026-11-14T09:00:00Z"),
        ("@b", "2026-11-14T12:00:00Z"),
        ("@undated", None),
    ]


def test_the_same_post_found_twice_is_kept_once():
    link = "https://bsky.app/profile/a/post/3kabc2defgh2x"
    found = [post(author="@a", url=link), post(author=None, url=link), post(author="@a2", url=link)]
    assert [p.author for p in social.select(found, [PHRASE], None)] == ["@a"]


def test_caps_per_platform_and_overall():
    def many(platform, host, n):
        return [
            post(
                platform, f"@{platform}{i}", url=f"https://{host}/u{i}/status/185500000000000000{i}"
            )
            for i in range(n)
        ]

    found = many("x", "x.com", social.PER_PLATFORM + 3)
    kept = social.select(found, [PHRASE], None)
    assert len(kept) == social.PER_PLATFORM
    everything = [
        post(name, f"@{name}{i}", url=f"https://{name}.example/@u{i}/1234567{i}")
        for name in ("mastodon", "telegram", "reddit", "x", "bluesky")
        for i in range(social.PER_PLATFORM)
    ]
    assert len(social.select(everything, [PHRASE], None)) == social.MAX_POSTS


# --- find_posts ------------------------------------------------------------------------------


def test_bluesky_is_searched_for_the_quoted_phrase(server):
    server.routes[BSKY_ROUTE] = lambda request: bsky_answer(
        bsky(f"Wow. {SENTENCE}", "alice.example"),
        bsky("Something about the harbour.", "bob.example", "3kzzz2defgh2x"),
    )
    found = find(server)
    assert [(p.platform, p.author) for p in found] == [("bluesky", "@alice.example")]
    (request,) = server.requests
    assert request.url.params["q"] == f'"{PHRASE}"'
    assert request.url.params["limit"] == str(social.BLUESKY_RESULTS)


def test_without_the_oxylabs_key_only_bluesky_is_searched(server):
    server.routes[BSKY_ROUTE] = lambda request: bsky_answer()
    assert find(server, phrases=("one phrase", "another phrase", "a third")) == []
    hosts = [request.url.host for request in server.requests]
    assert hosts == ["api.bsky.app"] * social.SEARCH_PHRASES  # not the third phrase


@pytest.fixture
def oxylabs(server, monkeypatch):
    """The Oxylabs search is on and answers with two X posts, a Reddit community and an article."""
    monkeypatch.setenv(scraper.TOKEN_ENV, "test-key-not-real")
    monkeypatch.setattr(scraper, "enabled", lambda: True)
    data = [
        {"url": "https://x.com/alice/status/1855000000000000001"},
        {"url": "https://twitter.com/bob/status/1855000000000000002"},
        {"url": "https://www.reddit.com/r/news/"},
        {"url": "https://paper.example/harbour"},
    ]
    server.routes[OXY_ROUTE] = lambda request: httpx.Response(200, json={"data": data})
    server.routes[BSKY_ROUTE] = lambda request: bsky_answer()
    server.routes[X_ROUTE] = x_answer
    return server


def test_web_search_results_are_read_from_the_platform(oxylabs):
    found = find(oxylabs)
    assert [(p.platform, p.author, p.text) for p in found] == [
        ("x", "@alice", SENTENCE),
        ("x", "@bob", SENTENCE),
    ]
    (search,) = [r for r in oxylabs.requests if r.url.host == "api-aistudio.oxylabs.io"]
    sent = json.loads(search.content)
    assert sent["query"].startswith(f'"{PHRASE}" (site:x.com OR site:twitter.com OR site:reddit')
    assert sent["limit"] == social.WEB_RESULTS
    # The key travels in a header, never in the address.
    assert search.headers["x-api-key"] == "test-key-not-real"
    assert "test-key-not-real" not in str(search.url)
    # Each post was read from X's public endpoint; the article and the community were not.
    read = [r.url.params["url"] for r in oxylabs.requests if r.url.host == "publish.twitter.com"]
    assert sorted(read) == [
        "https://x.com/alice/status/1855000000000000001",
        "https://x.com/bob/status/1855000000000000002",
    ]
    assert not any(r.url.host in ("paper.example", "www.reddit.com") for r in oxylabs.requests)


def test_reads_are_capped_per_platform(oxylabs):
    data = [{"url": f"https://x.com/user{i}/status/185500000000000000{i}"} for i in range(9)]
    oxylabs.routes[OXY_ROUTE] = lambda request: httpx.Response(200, json={"data": data})
    assert len(find(oxylabs)) == social.PER_PLATFORM
    read = [r for r in oxylabs.requests if r.url.host == "publish.twitter.com"]
    assert len(read) == social.READS_PER_PLATFORM


def test_a_found_post_that_does_not_repeat_the_phrase_is_dropped(oxylabs):
    oxylabs.routes[X_ROUTE] = lambda request: x_answer(request, "A post on the harbour sale.")
    assert find(oxylabs) == []


@pytest.mark.parametrize("status", [401, 402, 429, 500])
def test_search_errors_give_no_posts(oxylabs, status):
    oxylabs.routes[OXY_ROUTE] = lambda request: httpx.Response(status)
    oxylabs.routes[BSKY_ROUTE] = lambda request: httpx.Response(status)
    assert find(oxylabs) == []


def test_unreachable_searches_and_unreadable_posts_are_skipped(oxylabs):
    def down(request):
        raise httpx.ConnectError("no route")

    oxylabs.routes[BSKY_ROUTE] = down
    oxylabs.routes[X_ROUTE] = lambda request: (
        httpx.Response(404) if "alice" in request.url.params["url"] else x_answer(request)
    )
    assert [p.author for p in find(oxylabs)] == ["@bob"]
    oxylabs.routes[OXY_ROUTE] = down
    assert find(oxylabs) == []


def test_searches_and_posts_are_cached(oxylabs, tmp_path):
    cache = Cache(tmp_path / "retrieval.sqlite")
    oxylabs.routes[X_ROUTE] = lambda request: (
        httpx.Response(404) if "alice" in request.url.params["url"] else x_answer(request)
    )
    first = find(oxylabs, cache=cache)
    asked = len(oxylabs.requests)
    assert find(oxylabs, cache=cache) == first and [p.author for p in first] == ["@bob"]
    # Nothing was asked again: not the searches, not the post, not the deleted post.
    assert len(oxylabs.requests) == asked


def test_a_refused_post_is_tried_again_next_time(oxylabs, tmp_path):
    cache = Cache(tmp_path / "retrieval.sqlite")
    oxylabs.routes[X_ROUTE] = lambda request: httpx.Response(503)
    assert find(oxylabs, cache=cache) == []
    oxylabs.routes[X_ROUTE] = x_answer
    assert len(find(oxylabs, cache=cache)) == 2


def test_switched_off_or_without_phrases_nothing_is_asked(oxylabs, monkeypatch):
    assert find(oxylabs, phrases=()) == []
    monkeypatch.setenv("SOCIAL_SEARCH", "0")
    assert not social.enabled() and find(oxylabs) == []
    assert oxylabs.requests == []


def test_the_lane_gives_up_at_its_budget_and_survives_a_crash(oxylabs, monkeypatch):
    async def slow(*args, **kwargs):
        await asyncio.sleep(5)

    monkeypatch.setattr(social, "_find", slow)
    monkeypatch.setattr(social, "TIMEOUT_S", 0.05)
    assert find(oxylabs) == []

    async def crash(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(social, "_find", crash)
    assert find(oxylabs) == []


# --- the context item ------------------------------------------------------------------------


def test_a_post_as_a_context_item():
    found = post("reddit", "u/alice", url="https://www.reddit.com/r/news/comments/1abc2d/title/")
    found.title, found.community, found.language = "Harbour sold?", "r/news", "en"
    item = social.post_item("ctx7", found)
    assert item.id == "ctx7" and item.retrieved_by == "reddit" and item.outlet == "reddit.com"
    assert item.title == "Post by u/alice on Reddit in r/news"
    assert item.author == "u/alice"  # copies are counted per account
    assert item.text == f"Harbour sold?\n\n{SENTENCE}"  # quotes in evidence are cut from this
    assert item.published_at.isoformat() == "2026-11-14T10:00:00+00:00"
    assert item.language == "en" and item.tracking_ids == [] and item.fact_check is None
    assert item.in_story is None  # story's job
    anonymous = social.post_item("ctx1", post("telegram", None, url="https://t.me/chan_nel/7"))
    assert anonymous.title == "Post on Telegram" and anonymous.outlet == "t.me"
    assert anonymous.author is None


def test_adapter_names_are_the_platforms():
    assert (
        social.ADAPTERS
        == set(posts.PLATFORMS)
        == {"x", "reddit", "bluesky", "mastodon", "telegram"}
    )


# --- the stage -------------------------------------------------------------------------------


def analysis(paragraphs=(SENTENCE,), url=None):
    a = example_analysis()
    a.language = Language(code="en", confidence=0.99, support=LanguageSupport.evaluated)
    a.document = Document(url=url, paragraphs=list(paragraphs), outbound_links=[], tracking_ids=[])
    a.queries, a.claims, a.context, a.sources = [], [], [], []
    return a


def run(a) -> RetrievePatch:
    return asyncio.run(retrieve.run(a))


def test_posts_join_the_context_after_the_reports(stage):
    stage.routes[BSKY_ROUTE] = lambda request: bsky_answer(
        bsky(SENTENCE, "alice.example"), bsky(f"RT {SENTENCE}", "bob.example", "3kzzz2defgh2x")
    )
    patch = run(analysis())
    assert [(c.id, c.retrieved_by, c.outlet) for c in patch.context] == [
        ("ctx1", "bluesky", "bsky.app"),
        ("ctx2", "bluesky", "bsky.app"),
    ]
    assert patch.context[0].title == "Post by @alice.example on Bluesky"
    assert all(c.in_story is None and c.similarity is None for c in patch.context)
    # One profile for the platform, untyped: a platform is not an outlet type.
    assert [(s.domain, s.outlet_type) for s in patch.sources] == [("bsky.app", None)]
    assert patch.detail.startswith(
        "0 related reports from 0 outlets, 2 social media posts repeating its wording"
    )


def test_a_post_as_the_document_does_not_find_itself(stage):
    mine = "https://bsky.app/profile/alice.example/post/3kabc2defgh2x"
    stage.routes[BSKY_ROUTE] = lambda request: bsky_answer(
        bsky(SENTENCE, "alice.example"), bsky(SENTENCE, "bob.example", "3kzzz2defgh2x")
    )
    patch = run(analysis(url=mine))
    assert [c.title for c in patch.context] == ["Post by @bob.example on Bluesky"]


def test_a_short_document_has_no_phrase_so_nothing_is_searched(stage):
    patch = run(analysis(paragraphs=("Harbour sold to a fund.",)))
    assert patch.context == []
    assert not any(r.url.host == "api.bsky.app" for r in stage.requests)


def test_a_failing_social_lane_does_not_fail_the_stage(stage, monkeypatch):
    async def crash(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(retrieve.social, "_find", crash)
    patch = run(analysis())
    assert patch.context == [] and "social" not in patch.detail
