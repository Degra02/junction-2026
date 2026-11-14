"""Find a quoted passage in the analysed document and return its exact span.

The API drops every claim whose `text` is not the document text at its `span`, counted in
Unicode code points. Language models cannot count offsets and rewrite what they quote (straight
quotes for curly ones, single spaces for line breaks, a capital first letter), so never ask a
model for offsets: ask it for the passage and locate it here.

    claim = spans.claim(analysis.document, "cl1", passage_from_the_model)
    if claim is not None:
        claims.append(claim)
"""

import unicodedata

from pipeline.common.contracts import Claim, Document, Span

# Characters models swap freely for their plain equivalents.
_PLAIN = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "‘": "'",
        "’": "'",
        "‚": "'",
        "–": "-",
        "—": "-",
        "‑": "-",
    }
)
_EDGE_QUOTES = "\"' "
_EDGE_PUNCTUATION = _EDGE_QUOTES + ".,;:!?…"


def locate(document: Document, passage: str) -> Span | None:
    """The span of `passage` in the document, or None when the document does not contain it.

    Matching ignores case, accents, runs of whitespace and the kind of quote marks and dashes;
    when the passage is not found as given, it is tried without the quote marks and then
    without the punctuation around it. The span always covers the text as the document writes
    it; read it back with `text_at`.
    """
    wanted, _ = _fold(passage)
    for needle in (wanted.strip(), wanted.strip(_EDGE_QUOTES), wanted.strip(_EDGE_PUNCTUATION)):
        if not needle:
            continue
        for index, paragraph in enumerate(document.paragraphs):
            folded, origin = _fold(paragraph)
            at = folded.find(needle)
            if at < 0:
                continue
            start = origin[at]
            end = origin[at + len(needle) - 1] + 1
            # Keep combining marks with the letter they belong to.
            while end < len(paragraph) and unicodedata.combining(paragraph[end]):
                end += 1
            return Span(paragraph=index, start=start, end=end)
    return None


def text_at(document: Document, span: Span) -> str:
    """The document text a span covers."""
    return document.paragraphs[span.paragraph][span.start : span.end]


def claim(document: Document, claim_id: str, passage: str) -> Claim | None:
    """A claim the API accepts as verbatim: `passage` as the document writes it, with its span."""
    span = locate(document, passage)
    if span is None:
        return None
    return Claim(id=claim_id, text=text_at(document, span), span=span)


def _fold(text: str) -> tuple[str, list[int]]:
    """`text` reduced to what must match, and for each folded character the index of the
    original character it came from."""
    folded: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        for part in unicodedata.normalize("NFKD", char).translate(_PLAIN).casefold():
            if unicodedata.combining(part):
                continue
            if part.isspace():
                if folded and folded[-1] == " ":
                    continue
                part = " "
            folded.append(part)
            origin.append(index)
    return "".join(folded), origin
