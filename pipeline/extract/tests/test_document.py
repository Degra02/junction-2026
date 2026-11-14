from datetime import UTC, datetime

import pytest

from pipeline.extract.article import Article
from pipeline.extract.document import document_from_article, document_from_text, published_utc
from pipeline.extract.meta import PageMeta

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-11-13T18:57:00+0100", datetime(2026, 11, 13, 17, 57, tzinfo=UTC)),
        ("2026-11-11T17:36:21-05:00", datetime(2026, 11, 11, 22, 36, 21, tzinfo=UTC)),
        ("2026-11-10T18:05:00Z", datetime(2026, 11, 10, 18, 5, tzinfo=UTC)),
        ("2026-11-12T10:00:00", datetime(2026, 11, 12, 10, 0, tzinfo=UTC)),  # no offset: UTC
        ("2026-11-12", datetime(2026, 11, 12, tzinfo=UTC)),  # bare date: midnight UTC
        ("Fri, 13 Nov 2026 20:21:00 GMT", datetime(2026, 11, 13, 20, 21, tzinfo=UTC)),  # RSS
    ],
)
def test_published_utc_parses_page_formats(raw, expected):
    assert published_utc(raw, now=NOW) == expected


@pytest.mark.parametrize(
    "raw", [None, "", "  ", "yesterday", "2027-06-01T00:00:00Z", "1970-01-01T00:00:00Z"]
)
def test_published_utc_drops_missing_or_implausible_dates(raw):
    assert published_utc(raw, now=NOW) is None


def test_document_from_text():
    doc = document_from_text("First paragraph.\n\nSecond paragraph.")
    assert doc.paragraphs == ["First paragraph.", "Second paragraph."]
    assert (doc.url, doc.outlet, doc.published_at, doc.title) == (None, None, None, None)
    assert doc.outbound_links == [] and doc.tracking_ids == []


def test_document_from_article_maps_to_the_contract():
    article = Article(
        url="https://www.news.example/story",
        title="Headline",
        author="Jane Doe",
        published_at="2026-11-13T18:57:00+0100",
        site_name="News",
        language="it",
        paragraphs=["One.", "Two."],
        meta=PageMeta(
            tracking_ids={"gtm": ["GTM-K9X2ZQ"], "ga4": ["G-AB12CD34EF"]},
            outbound_links=["https://other.example/x"],
        ),
    )
    doc = document_from_article(article, "https://www.news.example/story")
    assert doc.url == "https://www.news.example/story"
    assert doc.outlet == "news.example"
    assert doc.published_at == datetime(2026, 11, 13, 17, 57, tzinfo=UTC)
    assert (doc.title, doc.author, doc.paragraphs) == ("Headline", "Jane Doe", ["One.", "Two."])
    assert doc.tracking_ids == ["G-AB12CD34EF", "GTM-K9X2ZQ"]  # flat, sorted
    assert doc.outbound_links == ["https://other.example/x"]
