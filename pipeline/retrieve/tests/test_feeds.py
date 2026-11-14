"""The feeds adapter and the shared web layer, against the fake web."""

import asyncio
from datetime import timedelta

from pipeline.retrieve.cache import Cache, NoCache
from pipeline.retrieve.feeds import FeedItem, parse_feed, read_feeds
from pipeline.retrieve.registry import Feed, parse
from pipeline.retrieve.tests.conftest import rss

A = "https://a.example/rss"
B = "https://b.example/rss"
REGISTRY = parse(
    {
        "national": [
            {"domain": "a.example", "feeds": [{"url": A, "language": "it"}]},
            {"domain": "b.example", "feeds": [{"url": B, "language": "en"}]},
        ]
    }
)


def read(server, cache=None, timeout_s=5.0):
    async def go():
        async with server.client() as client:
            from pipeline.retrieve.web import Web

            return await read_feeds(
                Web(client, guard=lambda url: None), cache or NoCache(), REGISTRY, timeout_s
            )

    return asyncio.run(go())


def test_items_of_every_feed_with_their_language(server):
    server.pages[A] = (200, rss(("Uno", "https://a.example/1"), ("Due", "https://a.example/2")))
    server.pages[B] = (200, rss(("One", "https://www.b.example/1")))
    items, answered = read(server)
    assert answered == 2
    assert {(i.title, i.language, i.outlet) for i in items} == {
        ("Uno", "it", "a.example"),
        ("Due", "it", "a.example"),
        ("One", "en", "b.example"),
    }


def test_a_failing_or_slow_feed_is_skipped(server):
    server.pages[A] = (500, "")
    server.pages[B] = (200, rss(("One", "https://b.example/1")))
    items, answered = read(server)
    assert answered == 1 and [i.title for i in items] == ["One"]

    server.pages[A] = (200, rss(("Uno", "https://a.example/1")))
    server.delays[A] = 5
    items, answered = read(server, timeout_s=0.5)
    assert answered == 1 and [i.title for i in items] == ["One"]


def test_an_unreachable_feed_is_skipped(server, monkeypatch):
    from pipeline.common import net
    from pipeline.common.errors import StageError

    def guard(url):
        if "a.example" in url:
            raise StageError("The link does not point to a public website")

    monkeypatch.setattr(net, "assert_public_url", guard)
    server.pages[B] = (200, rss(("One", "https://b.example/1")))

    async def go():
        from pipeline.retrieve.web import Web

        async with server.client() as client:
            return await read_feeds(Web(client), NoCache(), REGISTRY, 5.0)

    _, answered = asyncio.run(go())
    assert answered == 1
    assert A not in server.seen  # refused by the guard before any request


def test_feeds_are_cached_for_ten_minutes(server, tmp_path):
    cache = Cache(tmp_path / "r.sqlite")
    server.pages[A] = (200, rss(("Uno", "https://a.example/1")))
    server.pages[B] = (200, rss(("One", "https://b.example/1")))
    first, _ = read(server, cache)
    server.seen.clear()
    second, _ = read(server, cache)
    assert server.seen == []
    assert sorted(first, key=lambda i: i.url) == sorted(second, key=lambda i: i.url)
    assert all(isinstance(i, FeedItem) for i in second)
    assert cache.get("feeds", A, timedelta(minutes=10)) is not None


def test_garbage_and_relative_links_give_no_items():
    assert parse_feed(b"not a feed at all", Feed(A, "it")) == []
    body = rss(("Relative", "/news/1"), ("", "https://a.example/2")).encode()
    assert parse_feed(body, Feed(A, "it")) == []


def test_atom_feeds_work_too():
    atom = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom item</title><link href="https://a.example/atom-1"/>
<updated>2026-11-14T08:00:00Z</updated><summary>Lead</summary></entry></feed>"""
    [item] = parse_feed(atom, Feed(A, "en"))
    assert (item.title, item.url, item.summary) == ("Atom item", "https://a.example/atom-1", "Lead")
    assert item.published_at == "2026-11-14T08:00:00+00:00"


def test_at_most_two_requests_per_host_at_once(server):
    from pipeline.retrieve.web import Web

    urls = [f"https://a.example/p{i}" for i in range(6)] + ["https://b.example/p"]
    for url in urls:
        server.pages[url] = (200, "<html></html>")
        server.delays[url] = 0.05

    async def go():
        async with server.client() as client:
            web = Web(client, guard=lambda url: None)
            await asyncio.gather(*(web.get(u) for u in urls))

    asyncio.run(go())
    assert server.peak["a.example"] == 2
    assert server.peak["b.example"] == 1
