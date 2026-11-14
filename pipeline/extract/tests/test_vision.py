"""Tests for multimodal meme/screenshot extraction and companion `context_url` merging."""

import asyncio
from datetime import UTC, datetime

import pytest

from pipeline import extract, score, understand
from pipeline.common.contracts import Document, Input, InputKind
from pipeline.common.errors import StageError
from pipeline.common.fixtures import example_analysis
from pipeline.extract import vision
from pipeline.extract.vision import VisionReading, build_image_document, parse_data_uri

TINY_PNG_URI = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def test_parse_data_uri_accepts_valid_images_and_rejects_bad_inputs() -> None:
    mime, b64 = parse_data_uri(TINY_PNG_URI)
    assert mime == "image/png"
    assert len(b64) > 20
    with pytest.raises(StageError):
        parse_data_uri("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=")
    with pytest.raises(StageError):
        parse_data_uri("not-a-data-uri")


def test_build_image_document_merges_companion_and_never_trusts_forged_banner_outlet() -> None:
    reading = VisionReading(
        kind="news_screenshot",
        title="BREAKING: Private wells banned nationwide",
        claimed_outlet="bbc.com",
        claimed_author="@breaking_alert",
        language="en",
        ocr_paragraphs=["BREAKING: The government will ban private wells by January."],
        visual_context="Screenshot styled like a TV breaking-news banner.",
        pure_humour_or_satire=False,
    )
    # Without a companion URL, `outlet` stays None so a forged screenshot gets no trust.
    forged = build_image_document(reading)
    assert forged.outlet is None
    assert forged.paragraphs[0] == "BREAKING: The government will ban private wells by January."
    assert forged.paragraphs[1].startswith("[Visual context] Publisher shown in image: bbc.com.")

    # With a companion post URL, real post metadata + paragraphs are merged into the document.
    companion = Document(
        url="https://x.com/hoaxposter/status/999",
        outlet="x.com",
        published_at=datetime(2026, 11, 14, 20, 0, tzinfo=UTC),
        title="Post by @hoaxposter",
        author="@hoaxposter",
        paragraphs=["Share before they delete this! Total ban starting January."],
        outbound_links=["https://patriot-voice.example/wells"],
        tracking_ids=[],
    )
    merged = build_image_document(
        reading, companion=companion, companion_url="https://x.com/hoaxposter/status/999"
    )
    assert (merged.outlet, merged.author) == ("x.com", "@hoaxposter")
    assert merged.outbound_links == ["https://patriot-voice.example/wells"]
    assert merged.paragraphs[:2] == [
        "BREAKING: The government will ban private wells by January.",
        "Share before they delete this! Total ban starting January.",
    ]


def test_pure_humour_meme_abstains_in_score_and_synthetic_notes_yield_no_claims() -> None:
    reading = VisionReading(
        kind="meme",
        language="en",
        ocr_paragraphs=["Me explaining to my cat why dinner is 5 minutes late"],
        visual_context="Two-panel reaction meme of a woman yelling and a cat at a dinner table.",
        pure_humour_or_satire=True,
    )
    doc = build_image_document(reading)
    patch = understand.build_patch(
        doc,
        understand.Understanding(
            language="en",
            summary="A joke meme about feeding a cat.",
            claims=[doc.paragraphs[-1]],  # attempted claim inside synthetic note must be dropped
            queries=[],
        ),
        "en",
    )
    assert patch.claims == []

    analysis = example_analysis()
    analysis.input = Input(kind=InputKind.image, value=TINY_PNG_URI)
    analysis.document = doc
    scored = score.run(analysis)
    assert scored.scores.single.abstained is True
    assert "humour or satire" in (scored.scores.single.reason or "")


def test_extract_run_handles_image_with_companion_url(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_read(mime: str, b64: str) -> VisionReading:
        assert mime == "image/png"
        return VisionReading(
            kind="meme",
            language="it",
            ocr_paragraphs=["Il governo vieterà tutti i pozzi privati entro gennaio!"],
            visual_context="Meme con testo bianco su sfondo rosso.",
            pure_humour_or_satire=False,
        )

    async def fake_doc_from_url(url: str) -> Document:
        return Document(
            url=url,
            outlet="reddit.com",
            paragraphs=["Ecco il post che sta girando stamattina nei gruppi locali."],
            outbound_links=[],
            tracking_ids=[],
        )

    monkeypatch.setattr(vision, "read_image", fake_read)
    monkeypatch.setattr(extract, "document_from_url", fake_doc_from_url)

    analysis = example_analysis()
    analysis.input = Input(
        kind=InputKind.image,
        value=TINY_PNG_URI,
        context_url="https://www.reddit.com/r/italy/comments/abc123/pozzi/",
    )
    patch = asyncio.run(extract.run(analysis))
    assert patch.document.outlet == "reddit.com"
    assert len(patch.document.paragraphs) == 3
    assert patch.language is not None and patch.language.code == "it"
