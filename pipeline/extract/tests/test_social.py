"""Social media posts: recognising their addresses, parsing each platform's public answer, and
reading one through a fake `get`. The payloads are hand-written in each platform's real shape."""

import asyncio
import json

import pytest

from pipeline.extract import scraper, social
from pipeline.extract.fetch import FetchFailed, Page
from pipeline.extract.social import PostRef, post_ref

SENTENCE = "The council secretly sold the harbour to a foreign fund last night, insiders say."


@pytest.mark.parametrize(
    ("url", "platform", "normalised"),
    [
        ("https://twitter.com/jack/status/20?s=20&t=abc", "x", "https://x.com/jack/status/20"),
        ("https://mobile.twitter.com/jack/status/20/photo/1", "x", "https://x.com/jack/status/20"),
        ("https://x.com/i/web/status/1855", "x", "https://x.com/i/status/1855"),
        ("http://www.x.com/Some_User/statuses/1855", "x", "https://x.com/Some_User/status/1855"),
        (
            "https://www.reddit.com/r/worldnews/comments/1abc2d/some_title_here/",
            "reddit",
            "https://www.reddit.com/comments/1abc2d",
        ),
        (
            "https://old.reddit.com/r/worldnews/comments/1abc2d/some_title/k9zz1x/?context=3",
            "reddit",
            "https://www.reddit.com/comments/1abc2d/_/k9zz1x",
        ),
        ("https://redd.it/1abc2d", "reddit", "https://www.reddit.com/comments/1abc2d"),
        ("https://reddit.com/comments/1abc2d", "reddit", "https://www.reddit.com/comments/1abc2d"),
        (
            "https://bsky.app/profile/Alice.bsky.social/post/3kabc2defgh2x",
            "bluesky",
            "https://bsky.app/profile/alice.bsky.social/post/3kabc2defgh2x",
        ),
        (
            "https://bsky.app/profile/did:plc:abc123/post/3kabc2defgh2x",
            "bluesky",
            "https://bsky.app/profile/did:plc:abc123/post/3kabc2defgh2x",
        ),
        ("https://t.me/s/some_channel/342", "telegram", "https://t.me/some_channel/342"),
        ("https://telegram.me/some_channel/342", "telegram", "https://t.me/some_channel/342"),
        (
            "https://mastodon.social/@alice/117616784931828866",
            "mastodon",
            "https://mastodon.social/@alice/117616784931828866",
        ),
        (
            "https://fosstodon.org/@bob@mastodon.social/117616784931828866",
            "mastodon",
            "https://fosstodon.org/@bob@mastodon.social/117616784931828866",
        ),
        (
            "https://example.social/users/bob/statuses/117616784931828866",
            "mastodon",
            "https://example.social/users/bob/statuses/117616784931828866",
        ),
    ],
)
def test_post_addresses_are_recognised_and_normalised(url, platform, normalised):
    ref = post_ref(url)
    assert ref is not None
    assert (ref.platform, ref.url) == (platform, normalised)
    # Only Mastodon is a guess from the shape of the address.
    assert ref.certain == (platform != "mastodon")


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/jack",  # a profile
        "https://x.com/search?q=status",
        "https://www.reddit.com/r/worldnews/",  # a community
        "https://www.reddit.com/r/worldnews/s/AbCdEf",  # a share link: needs a redirect
        "https://t.me/durov",  # a channel
        "https://t.me/joinchat/abcdef",
        "https://bsky.app/profile/alice.bsky.social",
        "https://medium.com/@someone/a-story-of-2026-12345",  # not digits only
        "https://paper.example/news/2026/11/14/harbour-sold",
        "ftp://x.com/jack/status/20",
        "not a url",
        "https://[broken/status/20",
        "",
    ],
)
def test_other_addresses_are_not_posts(url):
    assert post_ref(url) is None


def test_endpoints_are_the_public_ones():
    assert post_ref("https://x.com/jack/status/20").endpoint == (
        "https://publish.twitter.com/oembed?url=https%3A%2F%2Fx.com%2Fjack%2Fstatus%2F20"
        "&omit_script=1&dnt=1&lang=en"
    )
    assert post_ref("https://redd.it/1abc2d").endpoint == (
        "https://www.reddit.com/comments/1abc2d/.rss?limit=1"
    )
    assert post_ref("https://bsky.app/profile/a.example/post/3kabc2defgh2x").endpoint == (
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"
        "?uri=at%3A%2F%2Fa.example%2Fapp.bsky.feed.post%2F3kabc2defgh2x&depth=0&parentHeight=0"
    )
    assert (
        post_ref("https://t.me/s/chan_nel/7").endpoint == "https://t.me/chan_nel/7?embed=1&mode=tme"
    )
    assert post_ref("https://m.example/@a/1234567").endpoint == (
        "https://m.example/api/v1/statuses/1234567"
    )


def test_is_post():
    assert social.is_post("https://x.com/jack/status/20")
    assert social.is_post("https://paper.example/a", retrieved_by="reddit")
    assert not social.is_post("https://paper.example/a", retrieved_by="feeds")
    # A Mastodon-shaped address alone is not proof.
    assert not social.is_post("https://paper.example/@desk/1234567")
    assert social.is_post("https://m.example/@a/1234567", retrieved_by="mastodon")


# --- X ---------------------------------------------------------------------------------------


def x_oembed(text_html: str, post_id: str = "1855000000000000000", lang: str = "en") -> bytes:
    return json.dumps(
        {
            "url": f"https://twitter.com/Some_User/status/{post_id}",
            "author_name": "Some User",
            "author_url": "https://twitter.com/Some_User",
            "html": f'<blockquote class="twitter-tweet"><p lang="{lang}" dir="ltr">{text_html}</p>'
            f'&mdash; Some User (@Some_User) <a href="https://twitter.com/Some_User/status/'
            f'{post_id}?ref_src=twsrc%5Etfw">November 9, 2024</a></blockquote>\n',
        }
    ).encode()


def test_x_post():
    ref = post_ref("https://x.com/i/status/1855000000000000000")
    body = x_oembed(
        f'{SENTENCE}<br><br>Second &amp; last line <a href="https://t.co/AbC123">'
        'https://t.co/AbC123</a> <a href="https://t.co/pic1">pic.twitter.com/pic1</a>'
    )
    post = social.parse_x(body, ref)
    assert post.platform == "x" and post.author == "@Some_User"
    assert post.url == "https://x.com/Some_User/status/1855000000000000000"
    # The author line after the text and the shortened links are not the author's words.
    assert post.text == f"{SENTENCE}\n\nSecond & last line"
    assert post.links == ["https://t.co/AbC123", "https://t.co/pic1"]
    assert post.language == "en"
    # The ID carries the millisecond the post was made.
    assert post.published_at == "2024-11-08T21:30:38.890000+00:00"


def test_x_post_before_snowflake_ids_takes_the_printed_date():
    ref = post_ref("https://x.com/jack/status/20")
    body = x_oembed("just setting up", "20").replace(b"November 9, 2024", b"March 21, 2006")
    assert social.parse_x(body, ref).published_at == "2006-03-21T00:00:00+00:00"
    assert (
        social.parse_x(body.replace(b"March 21, 2006", b"21 mars 2006"), ref).published_at is None
    )


def test_x_post_without_a_language():
    ref = post_ref("https://x.com/a/status/1855000000000000000")
    assert social.parse_x(x_oembed("🙂🙂🙂", lang="und"), ref).language is None
    assert social.parse_x(x_oembed("Olá", lang="pt-BR"), ref).language == "pt"


def test_x_answer_without_text_is_an_error():
    ref = post_ref("https://x.com/a/status/1855000000000000000")
    with pytest.raises(ValueError):
        social.parse_x(json.dumps({"html": "<blockquote></blockquote>"}).encode(), ref)


# --- Bluesky ---------------------------------------------------------------------------------


def bluesky_post(text: str, handle: str = "alice.bsky.social", rkey: str = "3kabc2defgh2x") -> dict:
    return {
        "uri": f"at://did:plc:abc123/app.bsky.feed.post/{rkey}",
        "author": {"did": "did:plc:abc123", "handle": handle},
        "record": {
            "$type": "app.bsky.feed.post",
            "createdAt": "2026-11-14T13:00:27.133Z",
            "langs": ["en"],
            "text": text,
            "facets": [
                {
                    "features": [
                        {"$type": "app.bsky.richtext.facet#link", "uri": "https://a.example/x"}
                    ]
                },
                {"features": [{"$type": "app.bsky.richtext.facet#tag", "tag": "news"}]},
            ],
            "embed": {"external": {"uri": "https://paper.example/harbour", "title": "Harbour"}},
        },
    }


def test_bluesky_post():
    ref = post_ref("https://bsky.app/profile/alice.bsky.social/post/3kabc2defgh2x")
    body = json.dumps({"thread": {"post": bluesky_post(f"{SENTENCE}\r\n\r\nMore.")}}).encode()
    post = social.parse_bluesky(body, ref)
    assert post.url == ref.url and post.author == "@alice.bsky.social"
    assert post.text == f"{SENTENCE}\n\nMore."
    assert post.published_at == "2026-11-14T13:00:27.133Z" and post.language == "en"
    assert post.links == ["https://a.example/x", "https://paper.example/harbour"]


def test_bluesky_missing_post_is_an_error():
    ref = post_ref("https://bsky.app/profile/alice.bsky.social/post/3kabc2defgh2x")
    not_found = {"thread": {"$type": "app.bsky.feed.defs#notFoundPost", "notFound": True}}
    with pytest.raises(KeyError):
        social.parse_bluesky(json.dumps(not_found).encode(), ref)


# --- Mastodon --------------------------------------------------------------------------------


def mastodon_status(content: str, acct: str = "alice", **extra) -> dict:
    return {
        "id": "117616784931828866",
        "url": "https://m.example/@alice/117616784931828866",
        "created_at": "2026-11-14T20:55:11.491Z",
        "language": "en",
        "content": content,
        "account": {"acct": acct},
        "reblog": None,
        "card": {"url": "https://paper.example/harbour"},
        **extra,
    }


def test_mastodon_status():
    ref = post_ref("https://m.example/@alice/117616784931828866")
    content = (
        f"<p>{SENTENCE}</p><p>Line one<br />line two "
        '<a href="https://m.example/tags/news" class="mention hashtag">#<span>news</span></a></p>'
    )
    post = social.parse_mastodon(json.dumps(mastodon_status(content)).encode(), ref)
    assert post.author == "@alice@m.example"  # a local account gets its instance
    assert post.text == f"{SENTENCE}\n\nLine one\nline two #news"
    assert post.links == ["https://m.example/tags/news", "https://paper.example/harbour"]
    assert post.language == "en" and post.published_at.startswith("2026-11-14T20:55")


def test_mastodon_boost_is_the_boosted_post():
    ref = post_ref("https://m.example/@alice/117616784931828866")
    boosted = mastodon_status("<p>Original words.</p>", acct="bob@other.example")
    boosted["url"] = "https://other.example/@bob/1234567"
    body = json.dumps(mastodon_status("", reblog=boosted)).encode()
    post = social.parse_mastodon(body, ref)
    assert (post.author, post.text, post.url) == (
        "@bob@other.example",
        "Original words.",
        "https://other.example/@bob/1234567",
    )


# --- Telegram --------------------------------------------------------------------------------

TELEGRAM = f"""<html><body><div class="tgme_widget_message js-widget_message">
<a class="tgme_widget_message_owner_name" href="https://t.me/chan_nel"><span dir="auto">The
Channel</span></a>
<div class="tgme_widget_message_text js-message_text" dir="auto"><b>Breaking.</b> {SENTENCE}
<br/><br/>Read <a href="https://paper.example/harbour">more</a>.</div>
<a class="tgme_widget_message_date" href="https://t.me/chan_nel/7">
<time datetime="2026-11-14T08:00:00+00:00" class="datetime">08:00</time></a>
</div></body></html>"""


def test_telegram_post():
    ref = post_ref("https://t.me/s/chan_nel/7")
    post = social.parse_telegram(TELEGRAM.encode(), ref)
    assert post.url == "https://t.me/chan_nel/7"
    assert post.author == "The Channel" and post.community == "chan_nel"
    assert post.text == f"Breaking. {SENTENCE}\n\nRead more."
    assert post.published_at == "2026-11-14T08:00:00+00:00"
    assert post.links == ["https://paper.example/harbour"]


@pytest.mark.parametrize(
    "page",
    [
        '<div class="tgme_widget_message_error">Post not found</div>',
        "<html><body><div class='tgme_page'>Join channel</div></body></html>",
    ],
)
def test_telegram_missing_post(page):
    with pytest.raises(FetchFailed, match="private, deleted"):
        social.parse_telegram(page.encode(), post_ref("https://t.me/chan_nel/7"))


# --- Reddit ----------------------------------------------------------------------------------


def reddit_feed(*entries: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
        "<title>A post : reddit.com</title>" + "".join(entries) + "</feed>"
    ).encode()


def reddit_entry(entry_id: str, title: str, content_html: str, author: str = "/u/alice") -> str:
    from html import escape

    link = "https://www.reddit.com/r/worldnews/comments/1abc2d/the_title/"
    if entry_id.startswith("t1_"):
        link += entry_id[3:] + "/"
    return (
        f"<entry><author><name>{author}</name></author>"
        '<category term="worldnews" label="r/worldnews"/>'
        f'<content type="html">{escape(content_html)}</content><id>{entry_id}</id>'
        f'<link href="{link}"/><updated>2026-11-14T09:07:12+00:00</updated>'
        f"<published>2026-11-14T09:07:12+00:00</published><title>{escape(title)}</title></entry>"
    )


SELF_POST = reddit_entry(
    "t3_1abc2d",
    "Harbour   sold?",
    f'<!-- SC_OFF --><div class="md"><p>{SENTENCE}</p><blockquote><p>Quoted line.</p>'
    '</blockquote><p>See <a href="https://paper.example/harbour">this</a>.</p></div>'
    '<!-- SC_ON --> submitted by <a href="https://www.reddit.com/user/alice">/u/alice</a>'
    ' <a href="https://www.reddit.com/r/worldnews/comments/1abc2d/the_title/">[link]</a>'
    ' <a href="https://www.reddit.com/r/worldnews/comments/1abc2d/the_title/">[comments]</a>',
)
LINK_POST = reddit_entry(
    "t3_1abc2d",
    "Council sells the harbour to a foreign fund",
    '<table><tr><td><a href="https://www.reddit.com/r/worldnews/comments/1abc2d/the_title/">'
    '<img src="https://preview.example/x.jpg"/></a></td><td> submitted by '
    '<a href="https://www.reddit.com/user/alice">/u/alice</a> '
    '<a href="https://paper.example/harbour">[link]</a> '
    '<a href="https://www.reddit.com/r/worldnews/comments/1abc2d/the_title/">[comments]</a>'
    "</td></tr></table>",
)
COMMENT = reddit_entry(
    "t1_k9zz1x",
    "/u/bob on Harbour sold?",
    '<div class="md"><p>I doubt it.</p></div>',
    author="/u/bob",
)


def test_reddit_self_post():
    post = social.parse_reddit(reddit_feed(SELF_POST, COMMENT), post_ref("https://redd.it/1abc2d"))
    assert post.title == "Harbour sold?" and post.author == "u/alice"
    assert post.community == "r/worldnews"
    assert post.text == f"{SENTENCE}\n\nQuoted line.\n\nSee this."
    assert post.url == "https://www.reddit.com/r/worldnews/comments/1abc2d/the_title/"
    assert post.published_at == "2026-11-14T09:07:12+00:00"
    assert post.links == ["https://paper.example/harbour"]  # not Reddit's own [link]/[comments]


def test_reddit_link_post_has_a_title_and_the_linked_address_only():
    post = social.parse_reddit(reddit_feed(LINK_POST), post_ref("https://redd.it/1abc2d"))
    assert post.text == "" and post.title == "Council sells the harbour to a foreign fund"
    assert post.links == ["https://paper.example/harbour"]
    document = social.document_from_post(post)
    # The title is all the author wrote: it is the text, not a headline above an empty body.
    assert document.paragraphs == [post.title] and document.title is None


def test_reddit_comment_link_reads_the_comment():
    ref = post_ref("https://www.reddit.com/r/worldnews/comments/1abc2d/the_title/k9zz1x/")
    post = social.parse_reddit(reddit_feed(SELF_POST, COMMENT), ref)
    assert (post.author, post.text, post.title) == ("u/bob", "I doubt it.", None)
    assert post.url.endswith("/k9zz1x/")


@pytest.mark.parametrize(
    "feed",
    [
        reddit_feed(),
        reddit_feed(reddit_entry("t3_1abc2d", "Gone", '<div class="md"><p>[removed]</p></div>')),
        reddit_feed(SELF_POST),  # the comment asked for is not in the feed
    ],
)
def test_reddit_missing_post_or_comment(feed):
    ref = post_ref("https://www.reddit.com/comments/1abc2d/_/zzzzzz")
    if b"[removed]" in feed or feed == reddit_feed():
        ref = post_ref("https://redd.it/1abc2d")
    with pytest.raises(FetchFailed, match="private, deleted"):
        social.parse_reddit(feed, ref)


# --- read_post -------------------------------------------------------------------------------


def getter(status: int, body: bytes | str = b"", seen: list | None = None):
    async def get(url: str) -> Page:
        if seen is not None:
            seen.append(url)
        data = body.encode() if isinstance(body, str) else body
        return Page(url=url, status=status, content_type="", body=data, truncated=False)

    return get


def read(ref: PostRef, get) -> social.Post:
    return asyncio.run(social.read_post(ref, get))


X_REF = post_ref("https://x.com/Some_User/status/1855000000000000000")


def test_read_post_fetches_the_endpoint():
    seen: list[str] = []
    post = read(X_REF, getter(200, x_oembed(SENTENCE), seen))
    assert post.text == SENTENCE and seen == [X_REF.endpoint]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410])
def test_a_private_or_deleted_post(status):
    with pytest.raises(FetchFailed) as e:
        read(X_REF, getter(status, "{}"))
    assert e.value.reason == social.NOT_AVAILABLE


def test_a_platform_error_names_the_platform_not_the_address():
    with pytest.raises(FetchFailed) as e:
        read(X_REF, getter(503))
    assert e.value.reason == "X did not answer (HTTP 503)"


@pytest.mark.parametrize("body", ["<html>not json</html>", "[]", '{"html": 5}', "{}"])
def test_an_unexpected_answer_is_unreadable(body):
    with pytest.raises(FetchFailed) as e:
        read(X_REF, getter(200, body))
    assert e.value.reason == social.NOT_READABLE


def test_a_post_without_text():
    ref = post_ref("https://bsky.app/profile/alice.bsky.social/post/3kabc2defgh2x")
    body = json.dumps({"thread": {"post": bluesky_post("  ")}})
    with pytest.raises(FetchFailed) as e:
        read(ref, getter(200, body))
    assert e.value.reason == social.NO_TEXT


def test_reddit_refusal_goes_through_the_scraper_when_there_is_a_key(monkeypatch):
    ref = post_ref("https://redd.it/1abc2d")
    asked: list[str] = []

    async def scrape_raw(url, *, client=None):
        asked.append(url)
        return Page(
            url=url, status=200, content_type="", body=reddit_feed(SELF_POST), truncated=False
        )

    monkeypatch.setattr(scraper, "enabled", lambda: True)
    monkeypatch.setattr(scraper, "scrape_raw", scrape_raw)
    assert read(ref, getter(429)).title == "Harbour sold?"
    assert asked == [ref.endpoint]
    # Only Reddit, and only on a refusal.
    asked.clear()
    read(ref, getter(200, reddit_feed(SELF_POST)))
    with pytest.raises(FetchFailed):
        read(X_REF, getter(429))
    assert asked == []


def test_reddit_refusal_without_a_key(monkeypatch):
    monkeypatch.setattr(scraper, "enabled", lambda: False)
    with pytest.raises(FetchFailed) as e:
        read(post_ref("https://redd.it/1abc2d"), getter(429))
    assert e.value.reason == "Reddit did not answer (HTTP 429)"
    with pytest.raises(FetchFailed) as e:
        read(post_ref("https://redd.it/1abc2d"), getter(403))
    assert e.value.reason == social.NOT_AVAILABLE


# --- the post as a document ------------------------------------------------------------------


def test_document_from_a_post():
    post = social.Post(
        platform="x",
        url="https://x.com/Some_User/status/1855000000000000000",
        author="@Some_User",
        text=f"{SENTENCE}\n\nSecond paragraph.",
        published_at="2024-11-09T10:00:00+00:00",
        links=["https://paper.example/harbour"],
    )
    document = social.document_from_post(post)
    assert document.url == post.url and document.author == "@Some_User"
    # The platform is not the publisher: other posts on it must be able to count as copies.
    assert document.outlet is None
    assert document.paragraphs == [SENTENCE, "Second paragraph."]
    assert document.published_at.isoformat() == "2024-11-09T10:00:00+00:00"
    assert document.outbound_links == ["https://paper.example/harbour"]
    assert document.tracking_ids == [] and document.title is None


def test_document_keeps_a_reddit_title_above_a_body():
    post = social.Post("reddit", "https://www.reddit.com/comments/1abc2d", "u/a", SENTENCE, None)
    post.title = "Harbour sold?"
    document = social.document_from_post(post)
    assert document.title == "Harbour sold?" and document.paragraphs == [SENTENCE]
    assert social.post_text(post) == f"Harbour sold?\n\n{SENTENCE}"


# --- the picture of a post -------------------------------------------------------------------

IMAGE_POST = reddit_entry(
    "t3_1abc2d",
    "They said it was about the harbour",
    '<table><tr><td><a href="https://www.reddit.com/r/worldnews/comments/1abc2d/the_title/">'
    '<img src="https://preview.redd.it/meme1.jpeg?width=640&amp;s=abc"/></a></td><td> submitted '
    'by <a href="https://www.reddit.com/user/alice">/u/alice</a> '
    '<a href="https://i.redd.it/meme1.jpeg">[link]</a> '
    '<a href="https://www.reddit.com/r/worldnews/comments/1abc2d/the_title/">[comments]</a>'
    "</td></tr></table>",
)


def image_address(post: social.Post, get=None) -> str | None:
    return asyncio.run(social.image_address(post, get or getter(500)))


def test_a_reddit_image_post_names_its_picture():
    post = social.parse_reddit(reddit_feed(IMAGE_POST), post_ref("https://redd.it/1abc2d"))
    assert post.text == "" and post.links == ["https://i.redd.it/meme1.jpeg"]
    assert image_address(post) == "https://i.redd.it/meme1.jpeg"


def test_a_post_without_a_picture_has_no_image_address():
    seen: list = []
    link = social.parse_reddit(reddit_feed(LINK_POST), post_ref("https://redd.it/1abc2d"))
    assert image_address(link, getter(200, b"{}", seen)) is None
    words = social.parse_x(x_oembed(SENTENCE), X_REF)
    assert words.has_media is False and image_address(words, getter(200, b"{}", seen)) is None
    assert seen == []  # nothing is asked when the post has no picture


def x_result(*media: dict) -> bytes:
    return json.dumps(
        {"__typename": "Tweet", "id_str": "1855", "mediaDetails": list(media)}
    ).encode()


def test_an_x_post_with_a_picture_asks_the_embed_endpoint_for_it():
    post = social.parse_x(
        x_oembed(f'{SENTENCE} <a href="https://t.co/pic1">pic.twitter.com/pic1</a>'), X_REF
    )
    assert post.has_media is True and post.links == ["https://t.co/pic1"]
    seen: list = []
    answer = x_result(
        {"type": "video", "media_url_https": "https://pbs.twimg.com/thumb/v.jpg"},
        {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/Gabc.jpg"},
        {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/Gdef.jpg"},
    )
    assert image_address(post, getter(200, answer, seen)) == "https://pbs.twimg.com/media/Gabc.jpg"
    assert seen == [
        "https://cdn.syndication.twimg.com/tweet-result?id=1855000000000000000&token=a&lang=en"
    ]
    assert post.links == ["https://t.co/pic1"]  # the post itself is left as the platform gave it


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (404, b"{}"),
        (200, b"not json"),
        (200, b"[]"),
        (200, x_result()),
        (200, x_result({"type": "photo", "media_url_https": "https://elsewhere.example/a.jpg"})),
        (200, x_result({"type": "photo"})),
    ],
)
def test_an_x_picture_that_cannot_be_found_is_no_error(status, body):
    post = social.parse_x(
        x_oembed(f'{SENTENCE} <a href="https://t.co/pic1">pic.x.com/pic1</a>'), X_REF
    )
    assert post.has_media is True
    assert image_address(post, getter(status, body)) is None


def test_an_unreachable_embed_endpoint_is_no_error():
    async def get(url: str) -> Page:
        raise FetchFailed("The site could not be reached")

    post = social.parse_x(
        x_oembed(f'{SENTENCE} <a href="https://t.co/pic1">pic.twitter.com/pic1</a>'), X_REF
    )
    assert image_address(post, get) is None
