import json

from pipeline.extract.meta import page_meta, tracking_ids

# Synthetic pages written for these tests; no scraped content is committed (repo goes public).
_CLAIM_REVIEW = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebPage", "name": "Fact check"},
        {
            "@type": "ClaimReview",
            "claimReviewed": "The moon is made of cheese.",
            "datePublished": "2026-11-10",
            "url": "https://checker.example/fact-check/moon",
            "author": {"@type": "Organization", "name": "Example Checker"},
            "itemReviewed": {
                "@type": "Claim",
                "author": {"@type": "Person", "name": "A. Blogger"},
            },
            "reviewRating": {
                "@type": "Rating",
                "ratingValue": "1",
                "bestRating": "5",
                "worstRating": "1",
                "alternateName": "False",
            },
            "inLanguage": "en",
        },
    ],
}

PAGE = f"""<!doctype html>
<html lang="it-IT"><head>
<link rel="canonical" href="https://news.example/2026/11/story">
<meta property="og:site_name" content="Example News">
<meta property="og:title" content="Council approves tram line">
<meta property="article:published_time" content="2026-11-12T09:30:00+01:00">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-AB12CD34EF"></script>
<script>gtag('config', 'G-AB12CD34EF'); ga('create', 'UA-1234567-2');</script>
<script>(function(w,d,s,l,i){{}})(window,document,'script','dataLayer','GTM-K9X2ZQ');</script>
<script data-ad-client="ca-pub-1234567890123456"></script>
<script type="application/ld+json">{json.dumps(_CLAIM_REVIEW)}</script>
<script type="application/ld+json">{{ this is not json </script>
</head><body>
<a href="https://other-site.example/source">source</a>
<a href="https://news.example/related">same site</a>
<a href="/relative">relative</a>
<a href="https://other-site.example/source">duplicate</a>
</body></html>"""


def test_tracking_ids():
    assert tracking_ids(PAGE) == {
        "ga_ua": ["UA-1234567-2"],
        "ga4": ["G-AB12CD34EF"],
        "gtm": ["GTM-K9X2ZQ"],
        "adsense": ["pub-1234567890123456"],
    }


def test_no_false_ga4_from_plain_text():
    assert tracking_ids("<p>Model G-ABCDEFGHIJ is a car, GTM is a word.</p>") == {}


def test_page_fields():
    meta = page_meta(PAGE, "https://news.example/2026/11/story?utm_source=x")
    assert meta.canonical_url == "https://news.example/2026/11/story"
    assert meta.site_name == "Example News"
    assert meta.og_title == "Council approves tram line"
    assert meta.html_lang == "it-IT"
    assert meta.published_time == "2026-11-12T09:30:00+01:00"
    assert meta.outbound_links == [
        "https://other-site.example/source"
    ]  # own host and relative dropped
    assert "ClaimReview" in meta.jsonld_types


def test_claim_review_from_jsonld_graph():
    (review,) = page_meta(PAGE).claim_reviews
    assert review.claim_reviewed == "The moon is made of cheese."
    assert review.rating == "False"
    assert (review.rating_value, review.best_rating, review.worst_rating) == (
        1.0,
        5.0,
        1.0,
    )
    assert review.reviewer == "Example Checker"
    assert review.claimant == "A. Blogger"
    assert review.language == "en"


def test_malformed_html_does_not_raise():
    meta = page_meta("")
    assert meta.claim_reviews == [] and meta.tracking_ids == {}
