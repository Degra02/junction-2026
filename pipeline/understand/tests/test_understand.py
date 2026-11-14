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
        "implied_claims": [],
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


def test_run_sends_the_document_as_user_content_and_drops_what_triage_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, str]] = []
    opinion = "Only a traitor would defend this shameful plan"
    fact = "The ministry said on Tuesday that the draft law requires well owners to register"

    async def fake_ask(schema: type, *, system: str, user: str, **_: object) -> object:
        sent.append((system, user))
        if schema is Understanding:
            return answer(claims=[opinion, fact])
        return schema.model_validate(
            {"claims": [{"claim": 1, "kind": "opinion"}, {"claim": 2, "kind": "fact"}]}
        )

    monkeypatch.setattr(understand.llm, "ask_json_async", fake_ask)
    analysis = example_analysis()
    patch = asyncio.run(understand.run(analysis))
    assert analysis.document is not None
    for system, user in sent:
        assert analysis.document.paragraphs[1] in user
        assert analysis.document.paragraphs[1] not in system
    assert opinion in sent[1][1]  # the triage call sees the claims with the content
    assert [(c.id, c.text) for c in patch.claims] == [("cl1", fact)]


def test_claims_triage_could_not_label_are_kept() -> None:
    document = example_analysis().document
    assert document is not None
    claims = build_patch(
        document,
        answer(
            claims=[
                "The government will ban private wells by January",
                "The ministry said on Tuesday that the draft law requires well owners to register",
            ]
        ),
        "en",
    ).claims
    kept = understand.keep_facts(claims, [None, "attributed"])
    assert [(c.id, c.text) for c in kept] == [("cl1", claims[0].text)]


def test_run_without_text_is_a_stage_error() -> None:
    analysis = example_analysis()
    analysis.document = None
    with pytest.raises(StageError):
        asyncio.run(understand.run(analysis))


def test_implied_claims_strip_quotes_cap_at_three_and_clear_on_satire_memes() -> None:
    document = example_analysis().document
    assert document is not None
    u = answer(
        implied_claims=[
            ' "Politicians promised lower grocery prices while focusing on Trump investigations." ',
            "politicians promised lower grocery prices while focusing on trump investigations.",
            "Is this really about groceries?",
            "short",
            "Second implied claim about the cartoon.",
            "Third implied claim about the cartoon.",
            "Fourth implied claim beyond the cap.",
        ]
    )
    cleaned = understand.clean_implied_claims(document, u.implied_claims)
    assert cleaned == [
        "Politicians promised lower grocery prices while focusing on Trump investigations.",
        "Second implied claim about the cartoon.",
        "Third implied claim about the cartoon.",
    ]
    assert all('"' not in c for c in cleaned)
    patch = build_patch(document, u, "en")
    if hasattr(patch.topic, "implied_claims"):
        assert patch.topic.implied_claims == cleaned

    satire_doc = document.model_copy(
        update={"paragraphs": ["Joke caption", "[Satire/humour meme] Everyday reaction joke."]}
    )
    assert understand.clean_implied_claims(satire_doc, u.implied_claims) == []
