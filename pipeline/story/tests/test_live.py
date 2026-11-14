"""Story with the real model. Skipped unless RUN_LIVE=1 (downloads ~470 MB on first run).

    RUN_LIVE=1 uv run pytest pipeline/story/tests/test_live.py -v

The texts are short paraphrases written for this test, not copied articles.
"""

import os
import time
from datetime import UTC, datetime

import pytest

from pipeline.common.contracts import ContextItem, Document, Language, LanguageSupport
from pipeline.common.fixtures import example_analysis

pytestmark = pytest.mark.skipif(not os.environ.get("RUN_LIVE"), reason="set RUN_LIVE=1")

DAY = datetime(2026, 11, 14, 9, 0, tzinfo=UTC)
DOCUMENT = (
    "Garante privacy, multa da 805 milioni a Meta",
    "L'autorità italiana per la protezione dei dati ha sanzionato Meta con 805 milioni di euro "
    "per aver usato le foto degli utenti di Facebook senza un consenso valido per addestrare "
    "i propri sistemi di intelligenza artificiale. La società ha annunciato ricorso.",
)
SAME = [
    (
        "Italy's privacy watchdog fines Meta 805 million euros",
        "Italy's data protection authority imposed an 805 million euro fine on Meta over the use "
        "of Facebook users' photos to train artificial intelligence without valid consent. Meta "
        "said it would appeal the decision.",
    ),
    (
        "Datenschutz: Italien verhängt 805 Millionen Euro Strafe gegen Meta",
        "Die italienische Datenschutzbehörde hat gegen Meta eine Strafe von 805 Millionen Euro "
        "verhängt, weil Fotos von Facebook-Nutzern ohne Einwilligung für KI-Training "
        "genutzt wurden.",
    ),
]
OTHER = [
    (
        "La Roma vince il derby contro la Lazio",
        "Nel derby della capitale la Roma ha battuto la Lazio per due a uno con una rete nel "
        "finale. I tifosi hanno festeggiato a lungo fuori dallo stadio Olimpico.",
    ),
    (
        "Alluvione in Emilia-Romagna, evacuate centinaia di famiglie",
        "Le piogge torrenziali hanno fatto esondare diversi fiumi in Emilia-Romagna. La protezione "
        "civile ha evacuato centinaia di famiglie e chiuso le scuole in molti comuni.",
    ),
]


def _item(i: int, title: str, text: str, language: str) -> ContextItem:
    return ContextItem(
        id=f"ctx{i}",
        url=f"https://outlet{i}.example/a",
        outlet=f"outlet{i}.example",
        published_at=DAY,
        title=title,
        text=text,
        language=language,
        retrieved_by="feeds",
        tracking_ids=[],
    )


def test_same_event_across_languages_is_in_and_other_news_is_out():
    import pipeline.story as story

    a = example_analysis()
    a.document = Document(
        published_at=DAY,
        title=DOCUMENT[0],
        paragraphs=[DOCUMENT[1]],
        outbound_links=[],
        tracking_ids=[],
    )
    a.language = Language(code="it", confidence=0.99, support=LanguageSupport.evaluated)
    languages = ["en", "de", "it", "it"]
    a.context = [
        _item(i, t, x, lang)
        for i, ((t, x), lang) in enumerate(zip(SAME + OTHER, languages, strict=True), start=1)
    ]
    start = time.monotonic()
    patch = story.run(a)
    elapsed = time.monotonic() - start
    assert [x.in_story for x in patch.assignments] == [True, True, False, False], [
        (x.context_id, x.similarity) for x in patch.assignments
    ]
    assert elapsed < 10, f"story took {elapsed:.1f} s for 4 items"
