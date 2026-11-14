"""Stage 2, extract: turn the input (pasted text, an article/post URL, or a meme/screenshot
image with an optional companion post/article `context_url`) into the `Document`.

`run` is the stage function the worker calls. The helper modules (`urls`, `text`, `meta`,
`article`) are pure; `fetch` (plain HTTP) and `scraper` (the Oxylabs fallback for sites that turn
away a plain client) do the network I/O and are shared with `retrieve`. `social` reads one post
on X, Reddit, Bluesky, Mastodon or Telegram from the platform's public endpoint; `vision` reads
memes and screenshots via `gemini-4-hydrogen` (with AI Router fallback).
"""

import asyncio
import logging

from pipeline.common import progress
from pipeline.common.contracts import Analysis, Document, ExtractPatch, InputKind
from pipeline.common.errors import StageError
from pipeline.extract import scraper, social, vision
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
from pipeline.extract.language import detect_language, language_from_code
from pipeline.extract.urls import outlet_host

log = logging.getLogger(__name__)
NO_ARTICLE = (
    "We could not find an article on that page. If it opens in your browser, paste its text instead"
)
PAYWALLED = (
    "This article is for subscribers, so we can only read its first lines. "
    "Paste its full text instead"
)


async def run(analysis: Analysis) -> ExtractPatch:
    inp = analysis.input
    vision_lang: str | None = None
    if inp.kind == InputKind.image:
        document, vision_lang = await _extract_image_input(inp.value, inp.context_url)
    elif inp.kind == InputKind.url:
        progress.report("Reading the page")
        document, vision_lang = await _extract_url_input(inp.value)
    else:
        document = document_from_text(inp.value)
        if inp.context_url:
            companion = await _optional_companion(inp.context_url)
            document = _merge_text_with_companion(document, companion, inp.context_url)
    if not document.paragraphs:
        raise StageError("There is no text to analyse")
    progress.report("Detecting the language")
    own_paragraphs = [p for p in document.paragraphs if not vision.is_synthetic_vision_paragraph(p)]
    language = (
        await asyncio.to_thread(detect_language, own_paragraphs) if own_paragraphs else None
    ) or language_from_code(vision_lang)
    return ExtractPatch(document=document, language=language)


async def _extract_image_input(value: str, context_url: str | None) -> tuple[Document, str | None]:
    progress.report(
        "Reading the image and attached context" if context_url else "Reading the image"
    )
    image_url: str | None = None
    if value.startswith("data:image/"):
        mime, b64 = vision.parse_data_uri(value)
    else:
        image_url = value
        try:
            async with new_client() as client:
                page = await fetch_page(value, client)
        except FetchFailed as e:
            raise StageError(e.reason) from e
        if page.status != 200:
            raise StageError(f"Could not download the image (HTTP {page.status})")
        mime, b64 = vision.encode_image_bytes(page.body, page.content_type)
        image_url = page.url

    reading, companion = await asyncio.gather(
        vision.read_image(mime, b64),
        _optional_companion(context_url),
    )
    document = vision.build_image_document(
        reading, image_url=image_url, companion=companion, companion_url=context_url
    )
    if not document.paragraphs:
        raise StageError("We could not find any text or identifiable scene in that image")
    return document, reading.language


async def _extract_url_input(url: str) -> tuple[Document, str | None]:
    ref = social.post_ref(url)
    if ref is not None:
        document = await _post_document(ref)
        if document is not None:
            return document, None
    try:
        async with new_client() as client:
            page = await fetch_page(url, client)
        if page.status == 200 and vision.is_image_content_type(page.content_type):
            progress.report("Reading the image")
            mime, b64 = vision.encode_image_bytes(page.body, page.content_type)
            reading = await vision.read_image(mime, b64)
            doc = vision.build_image_document(reading, image_url=page.url)
            return doc, reading.language
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
    return document_from_article(article, page.url), None


async def _optional_companion(context_url: str | None) -> Document | None:
    if not context_url:
        return None
    try:
        return await document_from_url(context_url)
    except StageError as e:
        log.warning("companion context_url could not be read (%s), keeping domain metadata", e)
        return None


def _merge_text_with_companion(
    base: Document, companion: Document | None, context_url: str
) -> Document:
    seen = {p.casefold() for p in base.paragraphs}
    merged = list(base.paragraphs)
    if companion is not None:
        for para in companion.paragraphs[:10]:
            cleaned = para.strip()
            if cleaned and cleaned.casefold() not in seen:
                seen.add(cleaned.casefold())
                merged.append(cleaned)
    return Document(
        url=(companion.url if companion and companion.url else None) or context_url,
        outlet=(companion.outlet if companion and companion.outlet else None)
        or outlet_host(context_url)
        or None,
        published_at=companion.published_at if companion else None,
        title=base.title or (companion.title if companion else None),
        author=companion.author if companion else None,
        paragraphs=merged,
        outbound_links=list(companion.outbound_links) if companion else [],
        tracking_ids=list(companion.tracking_ids) if companion else [],
    )


async def document_from_url(url: str) -> Document:
    """Fetch, check and extract one article. Raises `StageError` with a plain reason.

    Plain HTTP first. When the site turns that away (bot check), the page is fetched through
    Oxylabs (`scraper`), rendered if the plain copy holds no article; when the site answers but
    builds the article with JavaScript, it is fetched rendered. Without the Oxylabs key the
    plain-HTTP reason is shown. The address of a social media post is read as a post instead.
    """
    ref = social.post_ref(url)
    if ref is not None:
        document = await _post_document(ref)
        if document is not None:
            return document
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


async def _post_document(ref: social.PostRef) -> Document | None:
    """The post as a document; None when the address only looked like a post (`ref.certain`)."""
    progress.report(f"Reading the post on {social.PLATFORMS[ref.platform]}")
    try:
        async with new_client() as client:
            post = await social.read_post(ref, lambda u: fetch_page(u, client), client=client)
    except FetchFailed as e:
        if not ref.certain:
            return None
        if "public website" in e.reason:
            raise StageError(e.reason) from e
        raise StageError(f"{e.reason}. Paste its text instead") from e
    return social.document_from_post(post)


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
