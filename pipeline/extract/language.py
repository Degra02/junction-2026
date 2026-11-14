"""Language of the content and how well the pipeline supports it (D2 support tiers).

lingua runs locally (no web service), covers 75 languages and reports a confidence, which is
honest on short texts: a five-word post gets a low confidence instead of a confident guess.
"""

from lingua import LanguageDetectorBuilder

from pipeline.common.contracts import Language, LanguageSupport

# Loaded once at import (the worker imports every stage at startup).
_DETECTOR = LanguageDetectorBuilder.from_all_languages().with_preloaded_language_models().build()

# Detection is stable long before this; more text only costs time.
MAX_CHARS = 5_000

# Languages the pipeline's text models were pretrained on: the XLM-RoBERTa set (CC-100), shared
# by the technique classifier, the multilingual NLI and the e5 embeddings. "Supported" = covered by
# the models, not measured by us.
# fmt: off
MODEL_LANGUAGES = frozenset({
    "af", "am", "ar", "as", "az", "be", "bg", "bn", "br", "bs", "ca", "cs", "cy", "da", "de", "el",
    "en", "eo", "es", "et", "eu", "fa", "fi", "fr", "fy", "ga", "gd", "gl", "gu", "ha", "he", "hi",
    "hr", "hu", "hy", "id", "is", "it", "ja", "jv", "ka", "kk", "km", "kn", "ko", "ku", "ky", "la",
    "lo", "lt", "lv", "mg", "mk", "ml", "mn", "mr", "ms", "my", "ne", "nl", "no", "om", "or", "pa",
    "pl", "ps", "pt", "ro", "ru", "sa", "sd", "si", "sk", "sl", "so", "sq", "sr", "su", "sv", "sw",
    "ta", "te", "th", "tl", "tr", "ug", "uk", "ur", "uz", "vi", "xh", "yi", "zh",
})
# fmt: on

# Languages with labelled evaluation data in `evals/` (D2): the score stage does not cap their
# confidence, and the UI shows them as evaluated. These six are the languages with real items in
# `evals/labelled.jsonl` (Sat 16:30: en 57, de 48, fr 41, es 41, it 37, nl 17; ru, pl, pt, ro, cs
# and sv have under 6 each, too few to evaluate). Set on Sat 14.11 at the request of the
# teammate overseeing the pipeline, before the metrics were published and the combiner fitted;
# until then the explanation calls the confidences estimates. Add a language only when the
# labelled set holds enough real items in it.
EVALUATED_LANGUAGES: frozenset[str] = frozenset({"en", "de", "fr", "it", "es", "nl"})


def support_for(code: str) -> LanguageSupport:
    if code in EVALUATED_LANGUAGES:
        return LanguageSupport.evaluated
    if code in MODEL_LANGUAGES:
        return LanguageSupport.supported
    return LanguageSupport.unsupported


def detect_language(paragraphs: list[str]) -> Language | None:
    """Most likely language of the paragraphs, or None when the text has no detectable language.

    CPU-bound: call it from a thread in async code.
    """
    text = "\n".join(paragraphs)[:MAX_CHARS]
    values = _DETECTOR.compute_language_confidence_values(text)
    if not values or values[0].value <= 0:
        return None
    top = values[0]
    code = top.language.iso_code_639_1.name.lower()
    return Language(code=code, confidence=round(top.value, 3), support=support_for(code))


def language_from_code(raw: str | None) -> Language | None:
    """Fallback `Language` from a model-supplied ISO 639-1 tag when text is too short for lingua."""
    if not raw or not raw.strip():
        return None
    code = raw.strip().replace("_", "-").split("-", 1)[0].lower()
    if not (2 <= len(code) <= 3 and code.isalpha()):
        return None
    return Language(code=code, confidence=0.7, support=support_for(code))
