"""Build the contract's `Document` from pasted text or from an extracted article."""

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from pipeline.common.contracts import Document
from pipeline.extract.article import Article
from pipeline.extract.text import paragraphs_from_text
from pipeline.extract.urls import outlet_host

# Dates outside this range are broken page metadata, not publication dates.
_EARLIEST = datetime(1990, 1, 1, tzinfo=UTC)
_FUTURE_SLACK = timedelta(days=1)


def published_utc(value: str | None, now: datetime | None = None) -> datetime | None:
    """A page's publication time as UTC, or None when missing or implausible.

    Accepts ISO 8601 (with or without time and offset) and RFC 2822 (`Tue, 12 Nov 2026 ...`, as
    in RSS). A time without an offset is taken as UTC; a bare date becomes midnight UTC.
    """
    if not value or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except TypeError, ValueError, IndexError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    now = now or datetime.now(UTC)
    if not _EARLIEST <= parsed <= now + _FUTURE_SLACK:
        return None
    return parsed


def document_from_text(text: str) -> Document:
    """Pasted text: paragraphs only; there is no URL, outlet, date or page metadata."""
    return Document(paragraphs=paragraphs_from_text(text), outbound_links=[], tracking_ids=[])


def document_from_article(article: Article, url: str) -> Document:
    """A fetched page: `url` is the final address after redirects."""
    tracking = sorted({tid for ids in article.meta.tracking_ids.values() for tid in ids})
    return Document(
        url=url,
        outlet=outlet_host(url) or None,
        published_at=published_utc(article.published_at),
        title=article.title,
        author=article.author,
        paragraphs=article.paragraphs,
        outbound_links=article.meta.outbound_links,
        tracking_ids=tracking,
    )
