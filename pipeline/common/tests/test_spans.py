"""`spans.locate` must return spans the API's verbatim check accepts (code-point offsets)."""

import pytest

from pipeline.common import spans
from pipeline.common.contracts import Document
from pipeline.common.fixtures import example_analysis


def document(*paragraphs: str) -> Document:
    return Document(paragraphs=list(paragraphs), outbound_links=[], tracking_ids=[])


@pytest.mark.parametrize(
    ("paragraph", "passage", "found"),
    [
        # Straight quotes and single spaces where the page has curly quotes and a line break.
        (
            "He said “we will\nnever  pay” and left.",
            'said "we will never pay"',
            "said “we will\nnever  pay”",
        ),
        # Capitalised and wrapped in quotes the page does not have.
        ("In fact the minister lied.", '"The minister lied."', "the minister lied."),
        # Offsets after an emoji count code points, not UTF-16 units or bytes.
        ("😀😀 Perché il governo mente?", "il governo mente", "il governo mente"),
        # Decomposed accents in the page, composed in the passage.
        ("Le pre\u0301sident a menti hier.", "président a menti", "pre\u0301sident a menti"),
        ("Typographic dash — and ‘single’ quotes.", "dash - and 'single'", "dash — and ‘single’"),
    ],
)
def test_locate_finds_the_text_as_the_document_writes_it(
    paragraph: str, passage: str, found: str
) -> None:
    doc = document("An unrelated first paragraph.", paragraph)
    span = spans.locate(doc, passage)
    assert span is not None
    assert span.paragraph == 1
    assert spans.text_at(doc, span) == found


def test_a_passage_the_document_does_not_contain_is_not_located() -> None:
    doc = document("The minister spoke about the budget.")
    assert spans.locate(doc, "The minister lied about the budget") is None
    assert spans.locate(doc, ' "" ') is None
    assert spans.claim(doc, "cl1", "invented quote") is None


def test_claims_carry_the_document_text_not_the_model_s_version() -> None:
    doc = document("Critics say “the budget is a lie”, again.")
    claim = spans.claim(doc, "cl1", 'The budget is a lie."')
    assert claim is not None
    assert claim.text == "the budget is a lie"
    assert doc.paragraphs[0][claim.span.start : claim.span.end] == claim.text


def test_locate_agrees_with_the_spans_the_api_validated() -> None:
    analysis = example_analysis()
    assert analysis.document is not None
    for claim in analysis.claims:
        assert spans.locate(analysis.document, claim.text) == claim.span
