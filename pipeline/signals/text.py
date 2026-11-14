"""Language-independent text helpers for the signals: exact-substring passages and word sets."""

import re
import unicodedata

from pipeline.common.contracts import (
    Analysis,
    ContextItem,
    ContextRef,
    DocumentRef,
    OutletType,
    Span,
)

# A sentence: text up to and including its closing punctuation, or up to a line break.
_SENTENCE = re.compile(r"[^\n.!?…。！？]+[.!?…。！？]*[\"'”’»)\]]*")
_WORD = re.compile(r"\w+")
# Document sentences at least this long count when deciding whether a peer copies the document.
_COPY_MIN_CHARS = 40
# Quoted passages: double quotes, curly quotes (both directions), low-9 and guillemets (both
# directions), curly single quotes. Straight single quotes are left alone: they double as
# apostrophes.
_QUOTATION = re.compile(
    r'"[^"\n]+"|“[^“”\n]+”|”[^“”\n]+”|„[^„“”\n]+[“”]|«[^«»\n]+»|»[^«»\n]+«|‘[^‘’\n]+’'
)


def mask_quotations(text: str) -> str:
    """`text` with every quoted passage replaced by an ellipsis inside its quote marks.

    What a text quotes is not what it says: a fact-check quoting a hoax or a report quoting a
    politician's insults would otherwise be scored as the author's own words and as a copy of
    the quoted source. Language-independent; scare quotes around one word are masked too.
    """
    return _QUOTATION.sub(lambda m: f"{m.group()[0]}…{m.group()[-1]}", text)


def own_words(paragraphs: list[str]) -> list[str]:
    """The paragraphs with quotations masked, unless quotations make up most of the text: then
    the quote is the content itself (a pasted post wrapped in quote marks) and stays."""
    masked = [mask_quotations(p) for p in paragraphs]
    kept = sum(len(p) for p in masked)
    total = sum(len(p) for p in paragraphs)
    return masked if total and kept >= 0.3 * total else list(paragraphs)


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


def normalize_domain(value: str | None) -> str | None:
    """`https://www.Example.com/x` and `www.example.com` both become `example.com`."""
    if not value:
        return None
    host = value.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
    return host.removeprefix("www.") or None


def story_peers(analysis: Analysis, limit: int) -> list[ContextItem]:
    """Independent coverage of the same event, most similar first, at most one item per outlet
    domain: kept by `story` (or not judged yet), not fact-checks, not satire sites, not from the
    document's outlet, and not copies of the document (half or more of its sentences verbatim).
    Copies are the coordinated dimension's evidence; counted here they would confirm the
    document with its own words."""
    document = analysis.document
    own_domain = normalize_domain(document.outlet) if document else None
    satire = {
        normalize_domain(s.domain) or s.domain
        for s in analysis.sources
        if s.outlet_type == OutletType.satire
    }
    own = [
        _fold(paragraph[s:e])
        for paragraph in (document.paragraphs if document else [])
        for s, e in sentence_spans(paragraph)
        if e - s >= _COPY_MIN_CHARS
    ]
    candidates = []
    for item in analysis.context:
        if item.in_story is False or item.fact_check is not None or not item.text.strip():
            continue
        peer_domain = normalize_domain(item.outlet) or normalize_domain(item.url)
        if peer_domain in satire or (own_domain is not None and peer_domain == own_domain):
            continue
        text = _fold(item.text)
        if own and 2 * sum(sentence in text for sentence in own) >= len(own):
            continue
        candidates.append((peer_domain, item))
    candidates.sort(
        key=lambda pair: pair[1].similarity if pair[1].similarity is not None else 0.0,
        reverse=True,
    )
    peers: list[ContextItem] = []
    seen_domains: set[str] = set()
    for peer_domain, item in candidates:
        if peer_domain is not None:
            if peer_domain in seen_domains:
                continue
            seen_domains.add(peer_domain)
        peers.append(item)
        if len(peers) == limit:
            break
    return peers


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
