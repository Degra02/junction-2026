"""Stage 2, extract: turn the input (pasted text or an article URL) into the `Document`.

`run` is the stage function the worker calls. The helper modules (`urls`, `text`, `meta`,
`article`) are pure; `fetch` does the network I/O and is shared with `retrieve`.
"""

import asyncio

from pipeline.common import progress
from pipeline.common.contracts import Analysis, Document, ExtractPatch, InputKind
from pipeline.common.errors import StageError
from pipeline.extract.article import extract_article
from pipeline.extract.document import document_from_article, document_from_text
from pipeline.extract.fetch import FetchFailed, ensure_html, fetch_page, html_text, new_client
from pipeline.extract.language import detect_language


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
    """Fetch, check and extract one article. Raises `StageError` with a plain reason."""
    try:
        async with new_client() as client:
            page = await fetch_page(url, client)
        ensure_html(page)
    except FetchFailed as e:
        raise StageError(e.reason) from e
    html = html_text(page)
    article = await asyncio.to_thread(extract_article, html, page.url)
    if article is None:
        # Section fronts, video pages and sites that only show articles to a full browser
        # (JavaScript bot checks) all end here.
        raise StageError(
            "We could not find an article on that page. If it opens in your browser, "
            "paste its text instead"
        )
    if article.meta.paywalled:
        raise StageError(
            "This article is for subscribers, so we can only read its first lines. "
            "Paste its full text instead"
        )
    return document_from_article(article, page.url)
