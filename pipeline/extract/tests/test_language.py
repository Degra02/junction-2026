import pytest

from pipeline.common.contracts import LanguageSupport
from pipeline.extract import language
from pipeline.extract.language import detect_language, support_for


@pytest.mark.parametrize(
    ("text", "code"),
    [
        (
            "Il governo ha approvato ieri sera la nuova legge sul clima dopo un lungo dibattito.",
            "it",
        ),
        ("Правительство одобрило новый закон о климате после долгих дебатов в парламенте.", "ru"),
        ("Die Regierung hat das neue Klimagesetz nach einer langen Debatte verabschiedet.", "de"),
        ("وافقت الحكومة على قانون المناخ الجديد بعد نقاش طويل في البرلمان.", "ar"),
        ("Rząd przyjął nową ustawę klimatyczną po długiej debacie w parlamencie.", "pl"),
    ],
)
def test_detects_the_language_with_high_confidence(text, code):
    result = detect_language([text])
    assert result is not None
    assert result.code == code
    assert result.confidence > 0.9
    assert result.support == support_for(code)
    expected = "evaluated" if code in {"en", "de", "fr", "it", "es", "nl"} else "supported"
    assert result.support == LanguageSupport(expected)


def test_language_outside_the_models_is_unsupported():
    # Māori: lingua knows it, the XLM-R model family was not pretrained on it.
    result = detect_language(
        ["Ko te reo Māori te reo taketake o Aotearoa, he taonga nui ki ngā iwi."]
    )
    assert result is not None
    assert result.code == "mi"
    assert result.support == LanguageSupport.unsupported


def test_text_without_letters_has_no_language():
    assert detect_language(["12345 678 90", "%%% ???"]) is None


def test_short_text_gets_a_lower_confidence():
    long = detect_language(["The government approved the new climate law after a long debate."])
    short = detect_language(["they lied to you"])
    assert long is not None and short is not None
    assert short.confidence < long.confidence


def test_evaluated_languages():
    for code in ("en", "de", "fr", "it", "es", "nl"):
        assert support_for(code) == LanguageSupport.evaluated, code
    for code in ("pl", "pt", "ru", "uk", "ar"):  # covered by the models, no labelled set
        assert support_for(code) == LanguageSupport.supported, code


def test_evaluated_tier(monkeypatch):
    monkeypatch.setattr(language, "EVALUATED_LANGUAGES", frozenset({"it"}))
    assert support_for("it") == LanguageSupport.evaluated
    assert support_for("de") == LanguageSupport.supported
    assert support_for("mi") == LanguageSupport.unsupported
