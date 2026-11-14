"""Pasted text (the MVP input) to clean paragraphs."""

import re
import unicodedata


def paragraphs_from_text(text: str) -> list[str]:
    """Split pasted text into paragraphs with normalised whitespace.

    Blank lines separate paragraphs, and line breaks inside a paragraph are soft wraps. Text without
    any blank line (a social-media post, a chat message) is split on single line breaks instead.
    """
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ")
    blocks = re.split(r"\n[ \t]*\n", text)
    if len(blocks) == 1:
        blocks = text.split("\n")
    paragraphs = (" ".join(block.split()) for block in blocks)
    return [p for p in paragraphs if p]
