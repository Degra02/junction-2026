"""Language-independent text helpers for the signals: exact-substring passages and word sets."""

import re
import unicodedata

from pipeline.common.contracts import Analysis, ContextItem, ContextRef, DocumentRef, Span

# A sentence: text up to and including its closing punctuation, or up to a line break.
_SENTENCE = re.compile(r"[^\n.!?…。！？]+[.!?…。！？]*[\"'”’»)\]]*")
_WORD = re.compile(r"\w+")
# Document sentences at least this long count when deciding whether a peer copies the document.
_COPY_MIN_CHARS = 40


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """`(start, end)` of each non-blank sentence, without surrounding whitespace."""
    spans = []
    for match in _SENTENCE.finditer(text):
        sentence = match.group()
        if not sentence.strip():
            continue
        start = match.start() + len(sentence) - len(sentence.lstrip())
        spans.append((start, match.start() + len(sentence.rstrip())))
    return spans


def chunks(text: str, max_chars: int = 400) -> list[str]:
    """`text` cut into consecutive sentence groups of at most about `max_chars` characters;
    line breaks always end a group, a sentence longer than `max_chars` stays whole.

    Every chunk is an exact substring of `text`, so it can be quoted in a `ContextRef`.
    """
    pieces: list[str] = []
    start = end = None
    for s, e in sentence_spans(text):
        if start is not None and end is not None and (e - start > max_chars or "\n" in text[end:s]):
            pieces.append(text[start:end])
            start = None
        if start is None:
            start = s
        end = e
    if start is not None and end is not None:
        pieces.append(text[start:end])
    return pieces


def sentence_windows(text: str, size: int = 2) -> list[str]:
    """Every run of `size` consecutive sentences (all of `text` when it has fewer), as exact
    substrings. NLI needs the neighbouring sentence: "The draft does not ban private wells"
    only contradicts "The government will ban wells" next to "The ministry said ...".
    """
    spans = sentence_spans(text)
    if not spans:
        return []
    if len(spans) <= size:
        return [text[spans[0][0] : spans[-1][1]]]
    return [text[spans[i][0] : spans[i + size - 1][1]] for i in range(len(spans) - size + 1)]


def words(text: str) -> set[str]:
    """Case-, accent- and punctuation-insensitive word set."""
    return set(_WORD.findall(_fold(text)))


def tokens(text: str) -> list[str]:
    """Case-, accent- and punctuation-insensitive words, in order."""
    return _WORD.findall(_fold(text))


def overlap(a: str, b: str) -> float:
    """Share of the words of `a` that also appear in `b`."""
    wa = words(a)
    return len(wa & words(b)) / len(wa) if wa else 0.0


def contains(haystack: str, needle: str) -> bool:
    """Whether `needle` appears in `haystack`, ignoring case, accents and spacing."""
    return _fold(needle) in _fold(haystack)


def story_peers(analysis: Analysis, limit: int) -> list[ContextItem]:
    """Independent coverage of the same event, most similar first: kept by `story` (or not
    judged yet), not fact-checks, not from the document's outlet, and not copies of the
    document (half or more of its sentences verbatim). Copies are the coordinated dimension's
    evidence; counted here they would confirm the document with its own words."""
    document = analysis.document
    outlet = document.outlet if document else None
    own = [
        _fold(paragraph[s:e])
        for paragraph in (document.paragraphs if document else [])
        for s, e in sentence_spans(paragraph)
        if e - s >= _COPY_MIN_CHARS
    ]
    peers = []
    for item in analysis.context:
        if item.in_story is False or item.fact_check is not None or not item.text.strip():
            continue
        if outlet is not None and item.outlet == outlet:
            continue
        text = _fold(item.text)
        if own and 2 * sum(sentence in text for sentence in own) >= len(own):
            continue
        peers.append(item)
    peers.sort(key=lambda c: c.similarity if c.similarity is not None else 0.0, reverse=True)
    return peers[:limit]


def paragraph_ref(paragraphs: list[str], index: int) -> DocumentRef:
    """A reference to a whole document paragraph, without surrounding whitespace."""
    paragraph = paragraphs[index]
    start = len(paragraph) - len(paragraph.lstrip())
    end = len(paragraph.rstrip())
    return DocumentRef(kind="document", span=Span(paragraph=index, start=start, end=end))


def context_ref(item: ContextItem, quote: str | None = None) -> ContextRef:
    return ContextRef(kind="context", id=item.id, quote=quote)


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())
