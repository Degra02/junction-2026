"""The understand stage turns the model's answer into a patch the API accepts."""

import asyncio

import pytest

from pipeline import understand
from pipeline.common import spans
from pipeline.common.errors import StageError
from pipeline.common.fixtures import example_analysis
from pipeline.understand import Understanding, build_patch


def answer(**overrides: object) -> Understanding:
    fields: dict[str, object] = {
        "language": "en",
        "summary": " A draft law on registering private wells ",
        "entities": ["government", "Government", " ministry ", ""],
        "date": "null",
        "place": " ",
        "claims": [],
        "queries": [],
    }
    fields.update(overrides)
    return Understanding.model_validate(fields)


def test_claims_are_verbatim_spans_and_paraphrases_are_dropped() -> None:
    document = example_analysis().document
    assert document is not None
    patch = build_patch(
        document,
        answer(
            claims=[
                "The government is going to ban private wells by January",  # paraphrase
                "“the government will ban private wells by January.”",  # quotes, case, period
                "The government will ban private wells by January",  # same span again
                "The ministry said on Tuesday that the draft law requires well owners to "
                "register their wells by 2028.",
            ]
        ),
        "en",
    )
    assert [c.id for c in patch.claims] == ["cl1", "cl2"]
    for claim in patch.claims:
        assert spans.text_at(document, claim.span) == claim.text
    assert patch.claims[0].text == "The government will ban private wells by January"
    assert patch.claims[1].span.paragraph == 2


def test_queries_keep_document_language_and_english_only() -> None:
    document = example_analysis().document
    assert document is not None
    queries = [
        {"text": "divieto pozzi privati", "language": "it-IT"},
        {"text": '"pozzi privati" registrazione', "language": "IT"},
        {"text": "Divieto  pozzi privati", "language": "it"},  # duplicate after cleaning
        {"text": "privatbrunnen verbot", "language": "de"},  # neither it nor en
        {"text": "private wells ban", "language": "en"},
        {"text": "a", "language": "en"},
        {"text": "b", "language": "en"},
        {"text": "c", "language": "en"},  # fourth English query
    ]
    patch = build_patch(document, answer(queries=queries), "it")
    assert [(q.text, q.language) for q in patch.queries] == [
        ("divieto pozzi privati", "it"),
        ("pozzi privati registrazione", "it"),
        ("private wells ban", "en"),
        ("a", "en"),
        ("b", "en"),
    ]


def test_topic_is_cleaned() -> None:
    document = example_analysis().document
    assert document is not None
    topic = build_patch(document, answer(), "en").topic
    assert topic.summary == "A draft law on registering private wells"
    assert topic.entities == ["government", "ministry"]
    assert topic.date is None
    assert topic.place is None


def test_run_sends_the_document_as_user_content(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, str] = {}

    async def fake_ask(schema: type, *, system: str, user: str, **_: object) -> Understanding:
        sent["system"], sent["user"] = system, user
        return answer(claims=["Only a traitor would defend this shameful plan"])

    monkeypatch.setattr(understand.llm, "ask_json_async", fake_ask)
    analysis = example_analysis()
    patch = asyncio.run(understand.run(analysis))
    assert analysis.document is not None
    assert analysis.document.paragraphs[1] in sent["user"]
    assert analysis.document.paragraphs[1] not in sent["system"]
    assert [c.text for c in patch.claims] == ["Only a traitor would defend this shameful plan"]


def test_run_without_text_is_a_stage_error() -> None:
    analysis = example_analysis()
    analysis.document = None
    with pytest.raises(StageError):
        asyncio.run(understand.run(analysis))
