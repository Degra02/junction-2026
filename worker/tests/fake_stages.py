"""Stage functions used by the worker tests."""

import asyncio

from pipeline.common.contracts import (
    Analysis,
    Document,
    DocumentRef,
    Evidence,
    ExtractPatch,
    SignalsPatch,
    Span,
)


def extract(analysis: Analysis) -> ExtractPatch:
    return ExtractPatch(
        document=Document(
            paragraphs=[analysis.input.value],
            outbound_links=[],
            tracking_ids=[],
        ),
        language=None,
    )


async def signals_async(analysis: Analysis) -> SignalsPatch:
    await asyncio.sleep(0)
    return SignalsPatch(
        evidence=[
            Evidence(
                id="s1",
                family="tone",
                signal="loaded_language",
                value=0.9,
                detail="Charged wording",
                source_refs=[DocumentRef(kind="document", span=Span(paragraph=0, start=0, end=3))],
            )
        ]
    )


def as_dict(analysis: Analysis) -> dict:
    return {"evidence": []}


def wrong_shape(analysis: Analysis) -> dict:
    return {"evidence": [], "unexpected": True}


def raises(analysis: Analysis) -> SignalsPatch:
    raise RuntimeError("model crashed")
