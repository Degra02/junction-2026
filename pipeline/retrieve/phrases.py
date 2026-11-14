"""Exact phrases from the document, for searches that find its copies and its earlier versions.

A copy keeps the wording, so a verbatim run of words finds it where a topic query would not: on
sister sites of a network, or months earlier. Each phrase is a window of `WORDS` consecutive
words from the middle of a sentence (copy sites often rewrite the opening), from the sentences
with the most distinctive words (long words, figures).

Sentences in the author's own words come first; quoted speech is used only when nothing else
is left, because officials' quotes legitimately appear in every report of an event. Results are
never filtered for quotations: the signals tell quoting apart from copying.
"""

import re

from pipeline.common.contracts import Document

WORDS = 10
MAX_PHRASES = 3
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_QUOTES = '"«»“”„‟'
# Keep letters, digits, apostrophes and hyphens inside a word ("l'Ucraina", "pre-1997").
_PUNCT = re.compile(r"[^\w'’-]+")


def _words(sentence: str) -> list[str]:
    return [w for w in (_PUNCT.sub("", token) for token in sentence.split()) if w]


def _distinctive(word: str) -> bool:
    return len(word) >= 7 or any(c.isdigit() for c in word)


def distinctive_phrases(document: Document | None) -> list[str]:
    """Up to MAX_PHRASES verbatim windows of WORDS words, most useful first."""
    if document is None:
        return []
    candidates: list[tuple[bool, int, int, str]] = []
    order = 0
    for paragraph in document.paragraphs:
        for sentence in _SENTENCE_END.split(paragraph):
            words = _words(sentence)
            if len(words) < WORDS:
                continue
            start = (len(words) - WORDS) // 2
            window = words[start : start + WORDS]
            quoted = any(q in sentence for q in _QUOTES)
            score = sum(_distinctive(w) for w in window)
            candidates.append((quoted, -score, order, " ".join(window)))
            order += 1
    phrases: list[str] = []
    for *_, phrase in sorted(candidates):
        if phrase.casefold() not in {p.casefold() for p in phrases}:
            phrases.append(phrase)
        if len(phrases) == MAX_PHRASES:
            break
    return phrases


def contains(text: str, phrase: str) -> bool:
    """Whether `text` holds `phrase` verbatim, ignoring case, spacing and punctuation."""
    flat = " " + " ".join(_words(text)).casefold() + " "
    return " " + " ".join(_words(phrase)).casefold() + " " in flat
