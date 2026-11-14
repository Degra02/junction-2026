"""Fetched HTML page to a clean article: title, paragraphs, date, author, plus page metadata."""

from dataclasses import dataclass, field

import trafilatura

from pipeline.extract.meta import PageMeta, page_meta

# Below this many characters of body text the page is a menu, a paywall stub or an error page.
MIN_BODY_CHARS = 200


def _same_text(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


@dataclass
class Article:
    url: str | None
    title: str | None
    author: str | None
    # Precise page time if present, otherwise the date trafilatura finds.
    published_at: str | None
    site_name: str | None
    # From the page's `lang` attribute; None when the page does not say.
    language: str | None
    paragraphs: list[str] = field(default_factory=list)
    meta: PageMeta = field(default_factory=PageMeta)

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)


def extract_article(html: str, url: str | None = None) -> Article | None:
    """Main text and metadata of a news page; None when no article body is found.

    trafilatura strips menus, ads, related links and comments. `favor_precision` drops
    borderline blocks: for comparing wording across outlets, a missing paragraph is cheaper
    than boilerplate counted as shared text.
    """
    doc = trafilatura.bare_extraction(
        html,
        url=url,
        with_metadata=True,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
    if doc is None or not doc.text:
        return None
    paragraphs = [p for p in (" ".join(line.split()) for line in doc.text.split("\n")) if p]
    # trafilatura keeps the headline as the first line; it is the title, not body text, and
    # counting it as a paragraph would make every outlet "share" a paragraph.
    if paragraphs and doc.title and _same_text(paragraphs[0], doc.title):
        paragraphs = paragraphs[1:]
    if sum(len(p) for p in paragraphs) < MIN_BODY_CHARS:
        return None
    meta = page_meta(html, url)
    language = meta.html_lang.split("-")[0].lower() if meta.html_lang else None
    return Article(
        url=url,
        title=meta.og_title or doc.title or None,
        author=doc.author or None,
        published_at=meta.published_time or doc.date or None,
        site_name=meta.site_name or doc.sitename or None,
        language=language,
        paragraphs=paragraphs,
        meta=meta,
    )
