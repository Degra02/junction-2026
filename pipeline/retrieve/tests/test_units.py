"""The pure parts of retrieve: registry, VIGINUM list, matching, feed parsing, records, RDAP."""

import json
from datetime import UTC, datetime

import pytest

from pipeline.common.contracts import OutletType
from pipeline.extract.article import Article
from pipeline.extract.meta import ClaimReview, PageMeta
from pipeline.retrieve import registry as registry_module
from pipeline.retrieve.articles import record_from
from pipeline.retrieve.feeds import FeedItem, parse_feed
from pipeline.retrieve.match import Query, rank, terms
from pipeline.retrieve.registry import Feed, load_registry, parse
from pipeline.retrieve.sources import first_certificate, rdap_registration, registrable
from pipeline.retrieve.viginum import parse as parse_viginum


def test_lookup_takes_the_longest_listed_domain():
    reg = parse(
        {
            "wire_service": [{"domain": "afp.com", "country": "FR"}],
            "fact_checker": [{"domain": "factcheck.afp.com", "country": "FR"}],
            "national": [{"domain": "repubblica.it", "country": "IT"}],
        }
    )
    assert reg.lookup("factcheck.afp.com").outlet_type == OutletType.fact_checker
    assert reg.lookup("www.afp.com").outlet_type == OutletType.wire_service
    assert reg.lookup("bologna.repubblica.it").domain == "repubblica.it"
    assert reg.lookup("notrepubblica.it") is None
    assert reg.lookup(None) is None


def test_the_shipped_registry_is_well_formed():
    reg = load_registry()
    assert len(reg) > 100
    assert reg.feeds(), "the feeds adapter needs feeds"
    for outlet, feed in reg.feeds():
        assert feed.url.startswith("https://"), outlet.domain
        assert len(feed.language) == 2, outlet.domain
    data = json.loads(registry_module.DATA.read_text(encoding="utf-8"))
    assert "partisan" not in data, "D9: no political-bias ratings"
    for entries in data.values():
        for entry in entries:
            assert "/" not in entry["domain"] and entry["domain"] == entry["domain"].lower()
            assert entry["country"] is None or len(entry["country"]) == 2
    # Lyreplus's syndication guard and the state-agency ruling depend on these.
    assert reg.lookup("ansa.it").outlet_type == OutletType.wire_service
    assert reg.lookup("tass.ru").outlet_type == OutletType.state_affiliated
    assert reg.lookup("fullfact.org").outlet_type == OutletType.fact_checker
    # RT's mirror domains serve RT's own editions (checked Sun 15.11: same pages, same analytics
    # ID as rt.com, actualidad.rt.com and de.rt.com, "© ANO TV-Novosti" in the footer).
    for mirror in (
        "rtrunews.com",
        "rt-english.com",
        "actualidad-rt.com",
        "esrt.press",
        "de-rt.com",
        "www.rtrunews.com",
    ):
        profile = reg.lookup(mirror)
        assert profile.outlet_type == OutletType.state_affiliated, mirror
        assert profile.country == "RU", mirror
    # Reported untyped on the VPS (they counted as possible copiers).
    assert reg.lookup("www.rte.ie").outlet_type == OutletType.national
    assert reg.lookup("wtop.com").outlet_type == OutletType.local
    assert reg.lookup("corrieredelmezzogiorno.corriere.it").outlet_type == OutletType.local


def test_a_domain_listed_twice_is_an_error():
    with pytest.raises(ValueError, match="twice"):
        parse({"national": [{"domain": "a.it"}], "local": [{"domain": "a.it"}]})


def test_viginum_list_is_read_defanged():
    listing = parse_viginum(
        "﻿domain,create date,first seen,type\n"
        "pravda-de[.]com,22/02/2023,,domain\n"
        "news[.]example[.]org,31/02/2023,,subdomain\n"
    )
    assert listing.match("pravda-de.com") == "pravda-de.com"
    assert listing.match("www.pravda-de.com") == "pravda-de.com"
    assert listing.match("sub.news.example.org") == "news.example.org"
    assert listing.match("example.org") is None
    assert listing.created["pravda-de.com"] == datetime(2023, 2, 22, tzinfo=UTC)
    assert listing.created["news.example.org"] is None  # 31 February: unreadable, not guessed


def test_terms_fold_case_accents_and_stems():
    assert terms("Perché i MIGRANTI arrivano") == {"arriva", "migran"}
    assert terms("Migrants in 2026") == {"migran", "2026"}


def _item(title: str, language: str, url: str = "https://paper.example/a") -> FeedItem:
    return FeedItem(url, title, "", "2026-11-14T10:00:00+00:00", "paper.example", language)


def test_rank_compares_a_query_only_with_items_in_its_language():
    items = [
        _item("Garante privacy, multa da 805 milioni a Meta", "it", "https://a.example/1"),
        # Spanish "garantías" and "multa": false friends of the Italian query.
        _item("Garantías y multa por el DNI digital", "es", "https://b.example/2"),
        # Italian "fine" is "end", not a penalty.
        _item("La fine della guerra in Italia", "it", "https://c.example/3"),
    ]
    queries = [Query("Garante privacy multa", "it"), Query("Italian privacy watchdog fine", "en")]
    assert [h.item.url for h in rank(items, queries)] == ["https://a.example/1"]


def test_rank_needs_two_shared_words():
    items = [_item("Meta multata", "it")]
    assert rank(items, [Query("Garante privacy multa", "it")]) == []


RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Paper</title>
<item><title>Tram line &amp; bus</title><link>https://www.paper.example/tram?utm_source=rss</link>
<description>&lt;p&gt;The council &lt;b&gt;approved&lt;/b&gt; it.&lt;/p&gt;</description>
<pubDate>Tue, 10 Nov 2026 17:05:00 +0100</pubDate></item>
<item><title>No link</title></item>
</channel></rss>"""


def test_parse_feed():
    [item] = parse_feed(RSS, Feed("https://paper.example/rss", "en"))
    assert item.title == "Tram line & bus"
    assert item.summary == "The council approved it."
    assert item.outlet == "paper.example"
    assert item.published_at == "2026-11-10T16:05:00+00:00"
    assert item.language == "en"


def _article(**meta) -> Article:
    return Article(
        url="https://checker.example/a",
        title="Did the government ban wells?",
        author=None,
        published_at="2026-11-12T08:00:00+01:00",
        site_name=None,
        language="en",
        paragraphs=["We looked at the draft law.", "It registers wells; it bans none."],
        meta=PageMeta(**meta),
    )


def test_a_claimreview_page_becomes_a_fact_check_item():
    review = ClaimReview(
        claim_reviewed="The government will ban private wells",
        rating="False",
        rating_value=1,
        best_rating=5,
        worst_rating=1,
        reviewer="Checker",
        claimant=None,
        url=None,
        date_published=None,
        language="en",
    )
    record = record_from(
        _article(claim_reviews=[review], tracking_ids={"ga4": ["G-X1"]}),
        "https://c.example/a",
        None,
    )
    assert record is not None
    assert record.fact_check == {
        "claim": "The government will ban private wells",
        "rating": "False",
        "publisher": "Checker",
    }
    assert record.text.startswith("The government will ban private wells\n\nWe looked at")
    assert record.tracking_ids == ["G-X1"]
    assert record.published_at == "2026-11-12T07:00:00+00:00"


def test_a_paywalled_page_never_enters_the_context():
    assert record_from(_article(paywalled=True), "https://c.example/a", None) is None


def test_feed_date_is_the_fallback_publication_time():
    article = _article()
    article.published_at = None
    record = record_from(article, "https://c.example/a", "2026-11-13T09:00:00+00:00")
    assert record.published_at == "2026-11-13T09:00:00+00:00"
    assert record.fact_check is None
    assert record.text == "We looked at the draft law.\n\nIt registers wells; it bans none."


def test_rdap_and_certificate_dates():
    rdap = {
        "events": [
            {"eventAction": "last changed"},
            {"eventAction": "registration", "eventDate": "2025-10-01T12:00:00Z"},
        ]
    }
    assert rdap_registration(json.dumps(rdap).encode()) == datetime(2025, 10, 1, 12, tzinfo=UTC)
    assert rdap_registration(b"not json") is None
    certs = [{"not_before": "2025-10-03T00:00:00"}, {"not_before": "2025-10-02T05:00:00"}, {}]
    assert first_certificate(json.dumps(certs).encode()) == datetime(2025, 10, 2, 5, tzinfo=UTC)
    assert first_certificate(b"[]") is None


def test_registrable_domain():
    assert registrable("bologna.repubblica.it") == "repubblica.it"
    assert registrable("news.bbc.co.uk") == "bbc.co.uk"
    assert registrable("localhost") is None


def test_rare_words_weigh_more_than_common_ones():
    # "italia" is in every item, so sharing it and one more common word is not enough...
    items = [_item(f"Italia notizie {i} oggi", "it", f"https://x.example/{i}") for i in range(20)]
    items.append(_item("Italia notizie Garante multa", "it", "https://x.example/hit"))
    items.append(_item("Italia notizie varie", "it", "https://x.example/common"))
    hits = rank(items, [Query("Italia notizie Garante multa", "it")])
    assert [h.item.url for h in hits] == ["https://x.example/hit"]


def test_only_the_lead_of_a_long_summary_is_matched():
    lead = "Calcio, vince la Roma. " * 20  # 460 characters about something else
    item = FeedItem("https://x.example/1", "Sport", lead + "Garante privacy multa", None, "x", "it")
    assert rank([item], [Query("Garante privacy multa", "it")]) == []


def test_a_query_without_language_matches_every_language():
    items = [
        _item("Garante privacy multa", "it", "https://a.example/1"),
        _item("Garante privacy multa", "es", "https://b.example/2"),
    ]
    assert len(rank(items, [Query("Garante privacy multa", None)])) == 2


def test_one_word_queries_are_ignored():
    assert rank([_item("Meta", "it")], [Query("Meta", "it")]) == []


def test_lookup_ignores_case_and_trailing_dot():
    reg = parse({"national": [{"domain": "paper.example", "country": None}]})
    assert reg.lookup("WWW.Paper.Example.").domain == "paper.example"


def test_viginum_list_comes_from_the_env_path(tmp_path, monkeypatch):
    from pipeline.retrieve.viginum import load_listing

    csv_path = tmp_path / "pk.csv"
    csv_path.write_text("domain,create date,first seen,type\npravda-fr[.]com,01/01/2024,,domain\n")
    load_listing.cache_clear()
    try:
        monkeypatch.setenv("VIGINUM_CSV", str(csv_path))
        assert load_listing().match("pravda-fr.com") == "pravda-fr.com"
        load_listing.cache_clear()
        monkeypatch.setenv("VIGINUM_CSV", str(tmp_path / "missing.csv"))
        assert len(load_listing()) == 0  # missing file: no known networks, no crash
    finally:
        load_listing.cache_clear()


def test_the_real_viginum_list_parses_when_present():
    from pipeline.retrieve.viginum import DEFAULT_PATH

    if not DEFAULT_PATH.exists():
        pytest.skip("run `bash evals/download_data.sh` to fetch the VIGINUM list")
    listing = parse_viginum(DEFAULT_PATH.read_text(encoding="utf-8"))
    assert len(listing) > 300
    assert listing.match("pravda-de.com") == "pravda-de.com"
    for host in ("deutsch.news-pravda.com", "francais.news-pravda.com", "news-pravda.com"):
        assert listing.match(host), host  # where the Pravda domains redirect now


def _fetch(server, cache):
    import asyncio

    from pipeline.retrieve.viginum import fetch_listing

    async def go():
        async with server.client() as client:
            from pipeline.retrieve.web import Web

            return await fetch_listing(Web(client, guard=lambda u: None), cache)

    return asyncio.run(go())


def test_downloaded_viginum_list_is_cached_and_empty_answers_are_not(server, tmp_path):
    from pipeline.retrieve.cache import Cache
    from pipeline.retrieve.viginum import SOURCE_URL

    cache = Cache(tmp_path / "r.sqlite")
    server.pages[SOURCE_URL] = (200, "<html>Rate limited</html>")
    assert len(_fetch(server, cache)) == 0
    server.pages[SOURCE_URL] = (
        200,
        "domain,create date,first seen,type\npravda-de[.]com,,,domain\n",
    )
    assert _fetch(server, cache).match("pravda-de.com") == "pravda-de.com"
    server.seen.clear()
    assert _fetch(server, cache).match("pravda-de.com") == "pravda-de.com"
    assert server.seen == []  # from the cache


def test_unreachable_viginum_source_gives_an_empty_list(server, monkeypatch):
    from pipeline.common import net
    from pipeline.common.errors import StageError
    from pipeline.retrieve.cache import NoCache

    def refuse(url):
        raise StageError("The link's site could not be found")

    monkeypatch.setattr(net, "assert_public_url", refuse)

    import asyncio

    from pipeline.retrieve.viginum import fetch_listing
    from pipeline.retrieve.web import Web

    async def go():
        async with server.client() as client:
            return await fetch_listing(Web(client), NoCache())

    assert len(asyncio.run(go())) == 0


def test_news_pravda_subdomains_match_the_listed_domain():
    # Since Nov 2026 pravda-de.com redirects to deutsch.news-pravda.com: the list's
    # `news-pravda.com` domain row covers every language subdomain, listed or not.
    listing = parse_viginum(
        "domain,create date,first seen,type\n"
        "pravda-de[.]com,22/02/2023,,domain\n"
        "news-pravda[.]com,01/06/2024,,domain\n"
        "deutsch.news-pravda[.]com,01/06/2024,,subdomain\n"
    )
    assert listing.match("deutsch.news-pravda.com") == "deutsch.news-pravda.com"
    assert listing.match("italiano.news-pravda.com") == "news-pravda.com"
    assert listing.match("news-pravda.com") == "news-pravda.com"
    assert listing.match("pravda-news.com") is None
