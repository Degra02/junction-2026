"""Ties and clusters on the example analysis, and the false ties found in the eval records
(plans/source-graph.md, section 3): platform and placeholder IDs, agency copy, one shared story.
No model: the embedding and the language detector are stand-ins."""

import numpy as np

from pipeline.common.contracts import OutletType
from pipeline.common.fixtures import example_analysis
from pipeline.graph.build import AD_ACCOUNT, ANALYTICS_ID, COPY, TRANSLATION, clusters, ties
from pipeline.graph.corpus import Article, Corpus, Outlet, collect, operator


def unrelated(texts: list[str]) -> np.ndarray:
    """Embeddings under which no two texts are alike."""
    return np.eye(len(texts), dtype=np.float32)


def identical(texts: list[str]) -> np.ndarray:
    return np.ones((len(texts), 1), dtype=np.float32)


def story(n: int) -> str:
    return " ".join(f"story{n}word{i}" for i in range(40))


def article(outlet: str, text: str, n: int = 1, ids: tuple[str, ...] = ()) -> Article:
    return Article(
        url=f"https://{outlet}/{n}",
        outlet=outlet,
        title=None,
        text=text,
        published_at=None,
        tracking_ids=set(ids),
        analyses={f"analysis{n}"},
    )


def corpus_of(articles: list[Article], types: dict[str, OutletType] | None = None) -> Corpus:
    outlets = {a.outlet: Outlet(a.outlet, (types or {}).get(a.outlet)) for a in articles}
    return Corpus(articles=articles, outlets=outlets, links={}, analyses=1)


def found(corpus: Corpus, embed=unrelated):
    edges = ties(corpus, embed, lambda text: text[:2])
    return edges, clusters(corpus, edges)


def test_example_sites_sharing_an_analytics_id_form_one_cluster() -> None:
    corpus = collect([example_analysis()])
    assert set(corpus.outlets) == {
        "daily-truth.example",
        "newswire.example",
        "patriot-voice.example",
        "free-nation-news.example",
        "factcheck.example",
        "sports.example",
    }
    edges, groups = found(corpus)
    assert edges[("daily-truth.example", "free-nation-news.example")][ANALYTICS_ID].count == 2
    assert groups == [["daily-truth.example", "free-nation-news.example", "patriot-voice.example"]]


def test_platform_and_placeholder_ids_tie_nothing() -> None:
    blogger = "pub-1556223355139109"
    corpus = corpus_of(
        [
            article("one.blogspot.com", story(1), ids=(blogger,)),
            article("two.blogspot.com", story(2), ids=(blogger,)),
            # A site on Blogger under its own domain carries the platform's ID too.
            article("own-domain.de", story(3), ids=(blogger, "pub-1234567890123456")),
            article("template.de", story(4), ids=("pub-1234567890123456",)),
        ]
    )
    assert found(corpus) == ({}, [])


def test_a_shared_ad_account_alone_makes_no_cluster() -> None:
    reseller = "pub-2644536267352236"
    corpus = corpus_of(
        [
            article("a.example", story(1), ids=(reseller,)),
            article("b.example", story(2), ids=(reseller,)),
        ]
    )
    edges, groups = found(corpus)
    assert list(edges[("a.example", "b.example")]) == [AD_ACCOUNT]
    assert groups == []


def test_one_copied_story_is_a_weak_tie_and_two_make_a_cluster() -> None:
    once = [article("a.example", story(1)), article("b.example", story(1))]
    edges, groups = found(corpus_of(once))
    assert edges[("a.example", "b.example")][COPY].count == 1
    assert groups == []
    twice = [*once, article("a.example", story(2), n=2), article("b.example", story(2), n=2)]
    edges, groups = found(corpus_of(twice))
    assert edges[("a.example", "b.example")][COPY].count == 2
    assert groups == [["a.example", "b.example"]]


def test_agency_copy_and_newsrooms_are_not_copies() -> None:
    sites = ["a.example", "b.example"]
    with_agency = [article(d, story(n), n) for n in (1, 2) for d in [*sites, "wire.example"]]
    edges, _ = found(corpus_of(with_agency, {"wire.example": OutletType.wire_service}))
    assert ("a.example", "b.example") not in edges
    newsrooms = [article(d, story(n), n) for n in (1, 2) for d in sites]
    assert found(corpus_of(newsrooms, dict.fromkeys(sites, OutletType.national))) == ({}, [])
    # Official statements are republished like agency copy.
    official = [article(d, story(n), n) for n in (1, 2) for d in ("pm.gc.ca", "site.gouv.fr")]
    assert found(corpus_of(official)) == ({}, [])


def test_a_translation_is_the_same_text_in_another_language() -> None:
    # The stand-in detector reads the language from the first two letters.
    german, english = article("a.example", "de " + story(1)), article("b.example", "en " + story(2))
    edges, groups = found(corpus_of([german, english]), identical)
    assert list(edges[("a.example", "b.example")]) == [TRANSLATION]
    assert groups == []  # one translated story is a weak tie
    second = [
        article("a.example", "de " + story(3), n=2),
        article("b.example", "en " + story(4), n=2),
    ]
    assert found(corpus_of([german, english, *second]), identical)[1] == [
        ["a.example", "b.example"]
    ]
    same_language = [german, article("b.example", "de " + story(2))]
    assert found(corpus_of(same_language), identical) == ({}, [])


def test_editions_of_one_operator_cluster_but_blogs_on_a_platform_do_not() -> None:
    assert operator("deutsch.news-pravda.com") == operator("france.news-pravda.com")
    domains = ["deutsch.news-pravda.com", "france.news-pravda.com", "x.wordpress.com"]
    corpus = corpus_of(
        [article(d, story(n), n) for n, d in enumerate([*domains, "y.wordpress.com"])]
    )
    assert found(corpus)[1] == [["deutsch.news-pravda.com", "france.news-pravda.com"]]


def test_one_analytics_id_alone_is_a_weak_tie_until_corroborated() -> None:
    single_tag = [
        article("a.example", story(1), ids=("G-CMSVENDOR1",)),
        article("b.example", story(2), ids=("G-CMSVENDOR1",)),
    ]
    edges, groups = found(corpus_of(single_tag))
    assert edges[("a.example", "b.example")][ANALYTICS_ID].count == 1
    assert groups == []
    # Corroborated by a second analytics ID or by copied text -> clusters.
    two_tags = [
        article("a.example", story(1), ids=("G-ONE11111", "GTM-TWO2222")),
        article("b.example", story(2), ids=("G-ONE11111", "GTM-TWO2222")),
    ]
    assert found(corpus_of(two_tags))[1] == [["a.example", "b.example"]]
