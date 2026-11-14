"""Stage functions used by the worker tests."""

import asyncio
import threading

from pipeline.common import progress
from pipeline.common.contracts import (
    Analysis,
    Document,
    DocumentRef,
    Evidence,
    ExtractPatch,
    SignalsPatch,
    Span,
)
from pipeline.common.errors import StageError

# How often `broken_stage` was imported.
BROKEN_IMPORTS: list[int] = []
# `reports_progress` sets STARTED after its first note and returns once RELEASE is set.
STARTED = threading.Event()
RELEASE = threading.Event()


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
    return {"evidence": [{"id": "s1", "note": "SECRET-VALUE"}], "unexpected": True}


def raises(analysis: Analysis) -> SignalsPatch:
    raise RuntimeError("GET https://api.example/search?key=SECRET-KEY failed")


def gives_up(analysis: Analysis) -> SignalsPatch:
    raise StageError("The text is too short to analyse")


def reports_progress(analysis: Analysis) -> dict:
    progress.report("3 sources so far")
    STARTED.set()
    RELEASE.wait(timeout=5)
    return {"evidence": []}
