import pytest

from pipeline.extract.urls import canonical_url, outlet_host


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://www.Example.com/news/story/", "https://example.com/news/story"),
        (
            "https://example.com/a?utm_source=x&id=7&fbclid=abc#top",
            "https://example.com/a?id=7",
        ),
        ("https://example.com/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com:443//double//slash", "https://example.com/double/slash"),
        ("https://example.com:8080/x", "https://example.com:8080/x"),
        (
            "https://fr.news-site.com/x",
            "https://fr.news-site.com/x",
        ),  # subdomains are kept
    ],
)
def test_canonical_url(raw, expected):
    assert canonical_url(raw) == expected


def test_same_article_two_spellings_collapse():
    a = canonical_url("http://www.example.com/story/?utm_campaign=rss")
    b = canonical_url("https://example.com/story#comments")
    assert a == b


@pytest.mark.parametrize("bad", ["mailto:x@example.com", "ftp://example.com/f", "not a url"])
def test_canonical_url_rejects_non_http(bad):
    with pytest.raises(ValueError):
        canonical_url(bad)


def test_outlet_host():
    assert outlet_host("https://WWW.Example.co.uk/path") == "example.co.uk"
    assert outlet_host("https://fr.news-site.com/x") == "fr.news-site.com"
