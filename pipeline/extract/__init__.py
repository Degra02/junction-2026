"""Stage 2, extract: turn the input (pasted text or an article URL) into the `Document`.

`run` is the stage function the worker calls. The helper modules (`urls`, `text`, `meta`,
`article`) are pure; `fetch` (plain HTTP) and `browser` (headless Chromium fallback) do the network
I/O and are shared with `retrieve`.
"""

import asyncio

from pipeline.common import progress
from pipeline.common.contracts import Analysis, Document, ExtractPatch, InputKind
from pipeline.common.errors import StageError
from pipeline.extract import browser
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

    Plain HTTP first; when the site turns that away (bot check) or serves no article, the page
    is rendered once in headless Chromium (`browser`), unless BROWSER_FALLBACK=0.
    """
    try:
        async with new_client() as client:
            page = await fetch_page(url, client)
        ensure_html(page)
    except FetchFailed as e:
        if not (e.browser_may_help and browser.enabled()):
            raise StageError(e.reason) from e
        page, article = await _rendered(url, e.reason)
    else:
        article = await _extract(page)
        if article is None:
            if not browser.enabled():
                raise StageError(NO_ARTICLE)
            page, article = await _rendered(page.url, NO_ARTICLE)
    if article.meta.paywalled:
        raise StageError(PAYWALLED)
    return document_from_article(article, page.url)


async def _extract(page: Page) -> Article | None:
    return await asyncio.to_thread(extract_article, html_text(page), page.url)


async def _rendered(url: str, plain_reason: str) -> tuple[Page, Article]:
    """The page as a browser sees it; if that fails too, the most useful reason wins."""
    progress.report("Opening the page in a browser")
    try:
        page = await browser.render_page(url)
        ensure_html(page)
    except FetchFailed as e:
        # A refused private address is the real story; otherwise keep the plain-HTTP reason.
        reason = e.reason if "public website" in e.reason else plain_reason
        raise StageError(reason) from e
    article = await _extract(page)
    if article is None:
        raise StageError(NO_ARTICLE)
    return page, article
