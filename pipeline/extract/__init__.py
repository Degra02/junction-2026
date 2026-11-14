"""Stage 2, extract: turn the input (pasted text or an article URL) into the `Document`.

`run` is the stage function the worker calls. The helper modules (`urls`, `text`, `meta`,
`article`) are pure; `fetch` (plain HTTP) and `scraper` (the Oxylabs fallback for sites that turn
away a plain client) do the network I/O and are shared with `retrieve`.
"""

import asyncio

from pipeline.common import progress
from pipeline.common.contracts import Analysis, Document, ExtractPatch, InputKind
from pipeline.common.errors import StageError
from pipeline.extract import scraper
from pipeline.extract.article import Article, extract_article
from pipeline.extract.document import document_from_article, document_from_text
from pipeline.extract.fetch import (
    FetchFailed,
    Page,
    ensure_html,
    fetch_page,
    html_text,
    new_client,
)
from pipeline.extract.language import detect_language

NO_ARTICLE = (
    "We could not find an article on that page. If it opens in your browser, paste its text instead"
)
PAYWALLED = (
    "This article is for subscribers, so we can only read its first lines. "
    "Paste its full text instead"
)


async def run(analysis: Analysis) -> ExtractPatch:
    if analysis.input.kind == InputKind.url:
        progress.report("Reading the page")
        document = await document_from_url(analysis.input.value)
    else:
        document = document_from_text(analysis.input.value)
    if not document.paragraphs:
        raise StageError("There is no text to analyse")
    progress.report("Detecting the language")
    language = await asyncio.to_thread(detect_language, document.paragraphs)
    return ExtractPatch(document=document, language=language)


async def document_from_url(url: str) -> Document:
    """Fetch, check and extract one article. Raises `StageError` with a plain reason.

    Plain HTTP first. When the site turns that away (bot check), the page is fetched through
    Oxylabs (`scraper`), rendered if the plain copy holds no article; when the site answers but
    builds the article with JavaScript, it is fetched rendered. Without the Oxylabs key the
    plain-HTTP reason is shown.
    """
    try:
        async with new_client() as client:
            page = await fetch_page(url, client)
        ensure_html(page)
    except FetchFailed as e:
        if not (e.fallback_may_help and scraper.enabled()):
            raise StageError(e.reason) from e
        page, article = await _scraped(url, e.reason, render=False)
    else:
        article = await _extract(page)
        if article is None:
            if not scraper.enabled():
                raise StageError(NO_ARTICLE)
            page, article = await _scraped(page.url, NO_ARTICLE, render=True)
    if article.meta.paywalled:
        raise StageError(PAYWALLED)
    return document_from_article(article, page.url)


async def _extract(page: Page) -> Article | None:
    return await asyncio.to_thread(extract_article, html_text(page), page.url)


async def _scraped(url: str, plain_reason: str, *, render: bool) -> tuple[Page, Article]:
    """The page as Oxylabs reads it; unrendered first unless `render`, then rendered if that
    copy holds no article. If both fail, the most useful reason wins."""
    progress.report("Reading the page through our scraping service")
    attempts = (True,) if render else (False, True)
    for attempt in attempts:
        try:
            page = await scraper.scrape_page(url, render=attempt)
            ensure_html(page)
        except FetchFailed as e:
            if "public website" in e.reason:  # a refused private address is the real story
                raise StageError(e.reason) from e
            if attempt is attempts[-1]:
                raise StageError(plain_reason) from e
            continue
        article = await _extract(page)
        if article is not None:
            return page, article
    raise StageError(NO_ARTICLE)
