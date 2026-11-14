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

# Languages with labelled evaluation data in `evals/` (calibrated scores). Empty until the
# labelled sets land; add a code here only when its set exists.
EVALUATED_LANGUAGES: frozenset[str] = frozenset()


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
